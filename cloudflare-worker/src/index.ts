/**
 * Cloudflare Worker - Remote MCP with OAuth and Project Authorization
 *
 * Worker-native Remote MCP transport.
 * - GET /sse opens an SSE stream and emits an `endpoint` event with POST target
 *   `/messages?sessionId=...`.
 * - POST /messages accepts JSON-RPC requests and streams responses over the SSE.
 * Tools map to backend JSON endpoints with identity headers.
 */


interface Env {
  BACKEND_URL: string;
  DEFAULT_AGENT: string;
  KV_PROJECTS: KVNamespace;
  GITHUB_CLIENT_ID: string;
  GITHUB_CLIENT_SECRET: string;
  INTERNAL_AUTH_SECRET: string;
  ALLOW_DEV_SESSION?: string; // "true" to enable dev mode
}

interface ProjectACL {
  user_id: string;
  default: string;
  projects: string[];
}

interface SessionData {
  github_login: string;
  github_id: number;
}

/**
 * Main request handler
 */
// (consolidated default export with both scheduled and fetch is defined below)

// Scheduled cron: trigger backend git sync if configured
export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    try {
      if (!env.BACKEND_URL) return;
      await fetch(`${env.BACKEND_URL}/admin/sync`, {
        method: 'POST',
        headers: {
          'X-Internal-Auth': env.INTERNAL_AUTH_SECRET,
        },
      });
    } catch (e) {
      // best-effort; ignore errors
    }
  },
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    };
    if (request.method === 'OPTIONS') return new Response(null, { headers: corsHeaders });
    if (url.pathname === '/auth/login') return handleAuthLogin(request, env, corsHeaders);
    if (url.pathname === '/auth/callback') return handleOAuthCallback(request, env, corsHeaders);
    if (url.pathname === '/sse') return handleMCP(request, env, corsHeaders);
    if (url.pathname === '/messages') return handleMessages(request, env, corsHeaders);
    if (url.pathname === '/health') {
      return new Response(JSON.stringify({ status: 'ok', service: 'mharmless-remote-mcp', backend: env.BACKEND_URL }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    return new Response('Not Found', { status: 404, headers: corsHeaders });
  },
};

/**
 * Generate unique ULID-like ID (simplified version)
 */
function generateStateId(): string {
  return `${Date.now()}_${crypto.randomUUID()}`;
}

/**
 * Rate limiting helper using KV
 */
async function checkRateLimit(
  env: Env,
  key: string,
  maxAttempts: number,
  windowSeconds: number
): Promise<boolean> {
  const rateLimitKey = `ratelimit:${key}`;
  const current = await env.KV_PROJECTS.get(rateLimitKey);

  if (!current) {
    await env.KV_PROJECTS.put(rateLimitKey, '1', { expirationTtl: windowSeconds });
    return true;
  }

  const count = parseInt(current, 10);
  if (count >= maxAttempts) {
    return false;
  }

  await env.KV_PROJECTS.put(rateLimitKey, String(count + 1), { expirationTtl: windowSeconds });
  return true;
}

/**
 * Handle OAuth login initiation - generates state and redirects to GitHub
 */
async function handleAuthLogin(
  request: Request,
  env: Env,
  corsHeaders: Record<string, string>
): Promise<Response> {
  const url = new URL(request.url);
  const state = generateStateId();

  // Store state in KV with 10-minute TTL
  await env.KV_PROJECTS.put(`oauth:state:${state}`, '1', { expirationTtl: 600 });

  // Build GitHub authorization URL
  const redirectUri = `${url.origin}/auth/callback`;
  const githubAuthUrl = `https://github.com/login/oauth/authorize?` +
    `client_id=${encodeURIComponent(env.GITHUB_CLIENT_ID)}&` +
    `redirect_uri=${encodeURIComponent(redirectUri)}&` +
    `scope=read:user&` +
    `state=${encodeURIComponent(state)}`;

  // Log security event
  console.log(JSON.stringify({
    event: 'oauth_login_initiated',
    timestamp: new Date().toISOString(),
    state_id: state.substring(0, 16),
  }));

  // Redirect to GitHub with state in cookie for double verification
  return new Response(null, {
    status: 302,
    headers: {
      ...corsHeaders,
      'Location': githubAuthUrl,
      'Set-Cookie': `oauth_state=${state}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=600`,
    },
  });
}

/**
 * Handle OAuth callback from GitHub
 */
async function handleOAuthCallback(
  request: Request,
  env: Env,
  corsHeaders: Record<string, string>
): Promise<Response> {
  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const clientIP = request.headers.get('CF-Connecting-IP') || 'unknown';

  // C3: Rate limiting - 10 attempts per 5 minutes per IP
  const rateLimitAllowed = await checkRateLimit(env, `oauth:cb:${clientIP}`, 10, 300);
  if (!rateLimitAllowed) {
    console.log(JSON.stringify({
      event: 'rate_limit_exceeded',
      endpoint: '/auth/callback',
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));
    return new Response('Too many authentication attempts. Try again later.', {
      status: 429,
      headers: { ...corsHeaders, 'Retry-After': '300' }
    });
  }

  if (!code) {
    console.log(JSON.stringify({
      event: 'auth_failed',
      reason: 'missing_code',
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));
    return new Response('Missing code parameter', {
      status: 400,
      headers: corsHeaders
    });
  }

  // C1: CSRF Protection - Validate state parameter
  if (!state) {
    console.log(JSON.stringify({
      event: 'auth_failed',
      reason: 'missing_state',
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));
    return new Response('Missing state parameter', {
      status: 400,
      headers: corsHeaders
    });
  }

  // Verify state exists in KV
  const stateValid = await env.KV_PROJECTS.get(`oauth:state:${state}`);
  if (!stateValid) {
    console.log(JSON.stringify({
      event: 'auth_failed',
      reason: 'invalid_state',
      state_id: state.substring(0, 16),
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));
    return new Response('Invalid or expired state', {
      status: 400,
      headers: corsHeaders
    });
  }

  // Verify state matches cookie (double verification)
  const cookieHeader = request.headers.get('Cookie');
  let cookieState: string | null = null;
  if (cookieHeader) {
    const cookies = cookieHeader.split(';').map((c) => c.trim());
    for (const cookie of cookies) {
      if (cookie.startsWith('oauth_state=')) {
        cookieState = cookie.substring('oauth_state='.length);
        break;
      }
    }
  }

  if (cookieState !== state) {
    console.log(JSON.stringify({
      event: 'auth_failed',
      reason: 'state_cookie_mismatch',
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));
    return new Response('State verification failed', {
      status: 400,
      headers: corsHeaders
    });
  }

  // Delete state (one-time use)
  await env.KV_PROJECTS.delete(`oauth:state:${state}`);

  try {
    // Exchange code for access token - FIX: Use URLSearchParams and request JSON
    const redirectUri = `${url.origin}/auth/callback`;
    const tokenResponse = await fetch('https://github.com/login/oauth/access_token', {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        client_id: env.GITHUB_CLIENT_ID,
        client_secret: env.GITHUB_CLIENT_SECRET,
        code,
        redirect_uri: redirectUri,
      }),
    });

    if (!tokenResponse.ok) {
      const contentType = tokenResponse.headers.get('content-type') || '';
      const body = contentType.includes('application/json')
        ? await tokenResponse.json()
        : await tokenResponse.text();
      console.log(JSON.stringify({
        event: 'oauth_token_error',
        status: tokenResponse.status,
        body: String(body).slice(0, 200),
        ip: clientIP,
        timestamp: new Date().toISOString(),
      }));
      return new Response('OAuth token exchange failed', {
        status: 502,
        headers: corsHeaders
      });
    }

    // Log that we're about to process the response
    console.log(JSON.stringify({
      event: 'oauth_processing_token_response',
      status: tokenResponse.status,
      contentType: tokenResponse.headers.get('content-type'),
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));

    // Get response text first so we can log it if parsing fails
    const responseText = await tokenResponse.text();

    console.log(JSON.stringify({
      event: 'oauth_got_response_text',
      textLength: responseText.length,
      textPreview: responseText.slice(0, 100),
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));

    let tokenData: { access_token?: string; error?: string };
    try {
      tokenData = JSON.parse(responseText);
      console.log(JSON.stringify({
        event: 'oauth_json_parse_success',
        hasAccessToken: !!tokenData.access_token,
        hasError: !!tokenData.error,
        ip: clientIP,
        timestamp: new Date().toISOString(),
      }));
    } catch (parseError) {
      // Log the raw response if JSON parsing fails
      console.log(JSON.stringify({
        event: 'oauth_json_parse_error',
        error: String(parseError),
        status: tokenResponse.status,
        contentType: tokenResponse.headers.get('content-type'),
        bodyPreview: responseText.slice(0, 500),
        ip: clientIP,
        timestamp: new Date().toISOString(),
      }));
      throw new Error(`GitHub returned non-JSON response: ${responseText.slice(0, 200)}`);
    }

    if (tokenData.error || !tokenData.access_token) {
      console.log(JSON.stringify({
        event: 'oauth_token_error',
        error: tokenData.error || 'no_access_token',
        ip: clientIP,
        timestamp: new Date().toISOString(),
      }));
      throw new Error(tokenData.error || 'Failed to get access token');
    }

    // Get user info from GitHub
    const userResponse = await fetch('https://api.github.com/user', {
      headers: {
        'Authorization': `Bearer ${tokenData.access_token}`,
        'Accept': 'application/json',
        'User-Agent': 'Watercooler-Remote-MCP/1.0',
      },
    });

    console.log(JSON.stringify({
      event: 'oauth_fetched_user_info',
      status: userResponse.status,
      contentType: userResponse.headers.get('content-type'),
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));

    const userResponseText = await userResponse.text();
    console.log(JSON.stringify({
      event: 'oauth_user_response_text',
      textLength: userResponseText.length,
      textPreview: userResponseText.slice(0, 200),
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));

    let userData: { login?: string; id?: number };
    try {
      userData = JSON.parse(userResponseText);
    } catch (parseError) {
      console.log(JSON.stringify({
        event: 'oauth_user_json_parse_error',
        error: String(parseError),
        status: userResponse.status,
        contentType: userResponse.headers.get('content-type'),
        bodyPreview: userResponseText.slice(0, 500),
        ip: clientIP,
        timestamp: new Date().toISOString(),
      }));
      throw new Error(`GitHub /user API returned non-JSON: ${userResponseText.slice(0, 200)}`);
    }

    if (!userData.login || !userData.id) {
      console.log(JSON.stringify({
        event: 'auth_failed',
        reason: 'missing_user_data',
        ip: clientIP,
        timestamp: new Date().toISOString(),
      }));
      throw new Error('Failed to get user info from GitHub');
    }

    // Store session in KV with 24-hour expiry
    const sessionToken = crypto.randomUUID();
    const sessionData: SessionData = {
      github_login: userData.login,
      github_id: userData.id,
    };

    await env.KV_PROJECTS.put(
      `session:${sessionToken}`,
      JSON.stringify(sessionData),
      { expirationTtl: 86400 } // 24 hours
    );

    // H4: Log successful authentication
    console.log(JSON.stringify({
      event: 'auth_success',
      user: userData.login,
      user_id: userData.id,
      ip: clientIP,
      session_id: sessionToken.substring(0, 16),
      timestamp: new Date().toISOString(),
    }));

    return new Response('OAuth successful! You can close this window.', {
      headers: {
        ...corsHeaders,
        'Set-Cookie': `session=${sessionToken}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=86400`,
      },
    });
  } catch (error) {
    console.log(JSON.stringify({
      event: 'auth_failed',
      reason: 'exception',
      error: String(error),
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));
    return new Response(`OAuth error: ${error}`, {
      status: 500,
      headers: corsHeaders
    });
  }
}

// Simple in-memory session registry (sufficient for dev/local)
const sessionRegistry: Record<string, {
  controller: ReadableStreamDefaultController<Uint8Array>;
  identity: { userId: string; agentName: string };
  projectId: string;
}> = {};

// Handle POSTed JSON-RPC messages and stream responses via SSE
async function handleMessages(
  request: Request,
  env: Env,
  corsHeaders: Record<string, string>
): Promise<Response> {
  const url = new URL(request.url);
  const sessionId = url.searchParams.get('sessionId') || '';
  const session = sessionRegistry[sessionId];
  if (!session) return new Response('Invalid session', { status: 400, headers: corsHeaders });

  let payload: any;
  try {
    payload = await request.json();
  } catch {
    return new Response('Invalid JSON', { status: 400, headers: corsHeaders });
  }

  const messages = Array.isArray(payload) ? payload : [payload];
  for (const msg of messages) {
    await handleJsonRpc(msg, session, env);
  }
  return new Response('Accepted', { status: 202, headers: corsHeaders });
}

async function handleJsonRpc(
  message: any,
  session: { controller: ReadableStreamDefaultController<Uint8Array>; identity: { userId: string; agentName: string }; projectId: string },
  env: Env
) {
  const encoder = new TextEncoder();
  const send = (obj: any) => {
    const chunk = `event: message\ndata: ${JSON.stringify(obj)}\n\n`;
    session.controller.enqueue(encoder.encode(chunk));
  };

  const id = message.id;
  const method = message.method;
  const params = message.params || {};

  if (method === 'initialize') {
    return send({
      jsonrpc: '2.0',
      id,
      result: {
        protocolVersion: '2025-03-26',
        capabilities: { tools: {} },
        serverInfo: { name: 'watercooler-remote', version: '0.1.0' },
      },
    });
  }

  if (method === 'tools/list') {
    return send({ jsonrpc: '2.0', id, result: { tools: TOOL_DEFS } });
  }

  if (method === 'tools/call') {
    const name = params.name as string;
    const args = (params.arguments as Record<string, unknown>) || {};
    try {
      const resp = await fetch(`${env.BACKEND_URL}/mcp/${name}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Id': session.identity.userId,
          'X-Agent-Name': session.identity.agentName,
          'X-Project-Id': session.projectId,
          'X-Internal-Auth': env.INTERNAL_AUTH_SECRET,
        },
        body: JSON.stringify(args),
      });
      if (!resp.ok) {
        const text = await resp.text();
        return send({ jsonrpc: '2.0', id, error: { code: -32000, message: `Backend error ${resp.status}`, data: text } });
      }
      const data = await resp.json();
      const text = typeof data?.content === 'string' ? data.content : JSON.stringify(data);
      return send({ jsonrpc: '2.0', id, result: { content: [{ type: 'text', text }] } });
    } catch (e: any) {
      return send({ jsonrpc: '2.0', id, error: { code: -32000, message: String(e?.message || e) } });
    }
  }

  if (method === 'ping') {
    return send({ jsonrpc: '2.0', id, result: {} });
  }

  return send({ jsonrpc: '2.0', id, error: { code: -32601, message: `Method not found: ${method}` } });
}

// Tool definitions used by tools/list
const TOOL_DEFS = [
  { name: 'watercooler_v1_health', description: 'Check server health and configuration', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'watercooler_v1_whoami', description: 'Get your resolved agent identity', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'watercooler_v1_list_threads', description: 'List all watercooler threads', inputSchema: { type: 'object', properties: { open_only: { type: 'boolean' }, limit: { type: 'number' }, cursor: { type: 'string' }, format: { type: 'string', enum: ['markdown'] } }, additionalProperties: false } },
  { name: 'watercooler_v1_read_thread', description: 'Read full thread content', inputSchema: { type: 'object', properties: { topic: { type: 'string' }, from_entry: { type: 'number' }, limit: { type: 'number' }, format: { type: 'string', enum: ['markdown'] } }, required: ['topic'], additionalProperties: false } },
  { name: 'watercooler_v1_say', description: 'Add entry and flip ball', inputSchema: { type: 'object', properties: { topic: { type: 'string' }, title: { type: 'string' }, body: { type: 'string' }, role: { type: 'string' }, entry_type: { type: 'string' } }, required: ['topic', 'title', 'body'], additionalProperties: false } },
  { name: 'watercooler_v1_ack', description: 'Acknowledge thread', inputSchema: { type: 'object', properties: { topic: { type: 'string' }, title: { type: 'string' }, body: { type: 'string' } }, required: ['topic'], additionalProperties: false } },
  { name: 'watercooler_v1_handoff', description: 'Hand off ball to another agent', inputSchema: { type: 'object', properties: { topic: { type: 'string' }, note: { type: 'string' }, target_agent: { type: 'string' } }, required: ['topic'], additionalProperties: false } },
  { name: 'watercooler_v1_set_status', description: 'Update thread status', inputSchema: { type: 'object', properties: { topic: { type: 'string' }, status: { type: 'string' } }, required: ['topic', 'status'], additionalProperties: false } },
  { name: 'watercooler_v1_reindex', description: 'Generate and return the index content', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
];

/**
 * Handle MCP requests via SSE transport
 */
async function handleMCP(
  request: Request,
  env: Env,
  corsHeaders: Record<string, string>
): Promise<Response> {
  const url = new URL(request.url);
  const projectId = url.searchParams.get('project');
  const clientIP = request.headers.get('CF-Connecting-IP') || 'unknown';

  // Require proper SSE accept header to avoid browser preview hangs
  const accept = request.headers.get('Accept') || '';
  if (!accept.includes('text/event-stream')) {
    return new Response(
      'SSE endpoint. Use an MCP client or set Accept: text/event-stream',
      { status: 406, headers: { ...corsHeaders, 'Content-Type': 'text/plain' } }
    );
  }

  // C2: Extract session from cookie only (no query param except dev mode)
  let sessionToken = extractSessionToken(request);

  // H1: Allow dev session ONLY when explicitly enabled
  const sessionParam = url.searchParams.get('session');
  if (!sessionToken && sessionParam === 'dev') {
    if (env.ALLOW_DEV_SESSION === 'true') {
      console.log(JSON.stringify({
        event: 'dev_session_used',
        ip: clientIP,
        timestamp: new Date().toISOString(),
        warning: 'Dev mode enabled - not for production',
      }));
      sessionToken = 'dev';
    } else {
      console.log(JSON.stringify({
        event: 'dev_session_rejected',
        ip: clientIP,
        timestamp: new Date().toISOString(),
        reason: 'ALLOW_DEV_SESSION not enabled',
      }));
      return new Response('Unauthorized - Dev session not allowed', {
        status: 401,
        headers: corsHeaders
      });
    }
  }

  if (!sessionToken) {
    console.log(JSON.stringify({
      event: 'auth_failed',
      reason: 'no_session',
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));
    return new Response('Unauthorized - No session cookie', {
      status: 401,
      headers: corsHeaders
    });
  }

  // Resolve identity from session (with dev mode support)
  const identity = await resolveIdentity(sessionToken, env);
  if (!identity) {
    console.log(JSON.stringify({
      event: 'auth_failed',
      reason: 'invalid_session',
      session_id: sessionToken.substring(0, 16),
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));
    return new Response('Unauthorized - Invalid session', {
      status: 401,
      headers: corsHeaders
    });
  }

  // H2: ACL Default-Deny - Require explicit ACL entry
  let userACL: ProjectACL | null = null;
  try {
    const aclKey = `user:${identity.userId}`;
    const aclData = await env.KV_PROJECTS.get(aclKey);
    if (aclData) {
      userACL = JSON.parse(aclData);
    }
  } catch (error) {
    console.log(JSON.stringify({
      event: 'acl_error',
      user: identity.userId,
      error: String(error),
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));
    return new Response('Error: Unable to load user permissions', {
      status: 500,
      headers: corsHeaders,
    });
  }

  // Require ACL entry (default deny)
  if (!userACL) {
    console.log(JSON.stringify({
      event: 'acl_denied',
      reason: 'no_acl_entry',
      user: identity.userId,
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));
    return new Response('Access denied - No project permissions configured. Contact administrator.', {
      status: 403,
      headers: corsHeaders,
    });
  }

  // Determine project to use
  let selectedProject = projectId;
  if (!selectedProject) {
    selectedProject = userACL.default;
  }

  if (!selectedProject) {
    return new Response('Error: No project specified and no default project configured', {
      status: 400,
      headers: corsHeaders,
    });
  }

  // Validate project access
  if (!userACL.projects.includes(selectedProject)) {
    console.log(JSON.stringify({
      event: 'acl_denied',
      reason: 'project_not_in_allowlist',
      user: identity.userId,
      project: selectedProject,
      allowed_projects: userACL.projects,
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));
    return new Response('Access denied', {
      status: 403,
      headers: corsHeaders,
    });
  }

  // H4: Log successful session validation
  console.log(JSON.stringify({
    event: 'session_validated',
    user: identity.userId,
    project: selectedProject,
    ip: clientIP,
    timestamp: new Date().toISOString(),
  }));

  // Worker-native SSE stream + session registration
  const encoder = new TextEncoder();
  const sessionId = crypto.randomUUID();

  let hb: number | undefined;
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      // store identity & project for this session
      sessionRegistry[sessionId] = { controller, identity, projectId: selectedProject };
      // emit endpoint event immediately
      controller.enqueue(encoder.encode(`event: endpoint\ndata: /messages?sessionId=${sessionId}\n\n`));
      // heartbeat to keep SSE open under dev
      hb = setInterval(() => {
        try { controller.enqueue(encoder.encode(`: keep-alive\n\n`)); } catch {}
      }, 15000) as unknown as number;
    },
    cancel() {
      if (hb !== undefined) clearInterval(hb as unknown as number);
      delete sessionRegistry[sessionId];
    }
  });

  return new Response(stream, {
    headers: {
      ...corsHeaders,
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
    },
  });
}

/**
 * Resolve identity from session token
 */
async function resolveIdentity(
  sessionToken: string,
  env: Env
): Promise<{ userId: string; agentName: string } | null> {
  // H1: Dev mode - only allow when explicitly enabled
  if (sessionToken === 'dev') {
    if (env.ALLOW_DEV_SESSION === 'true') {
      return {
        userId: 'gh:dev',
        agentName: 'Dev',
      };
    }
    return null;
  }

  // Look up session in KV
  try {
    const sessionData = await env.KV_PROJECTS.get(`session:${sessionToken}`);
    if (!sessionData) {
      return null;
    }

    const session: SessionData = JSON.parse(sessionData);
    return {
      userId: `gh:${session.github_login}`,
      agentName: session.github_login,
    };
  } catch (error) {
    console.error('Error resolving identity:', error);
    return null;
  }
}

/**
 * Extract session token from cookie or Authorization header
 */
function extractSessionToken(request: Request): string | null {
  // Try cookie first
  const cookieHeader = request.headers.get('Cookie');
  if (cookieHeader) {
    const cookies = cookieHeader.split(';').map((c) => c.trim());
    for (const cookie of cookies) {
      if (cookie.startsWith('session=')) {
        return cookie.substring('session='.length);
      }
    }
  }

  // Try Authorization header
  const authHeader = request.headers.get('Authorization');
  if (authHeader?.startsWith('Bearer ')) {
    return authHeader.substring('Bearer '.length);
  }

  return null;
}
