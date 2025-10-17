/**
 * Cloudflare Worker - Remote MCP with OAuth and Project Authorization
 *
 * This worker provides:
 * - GitHub OAuth authentication
 * - Per-user/per-project authorization via KV
 * - SSE/Streamable HTTP transport for Remote MCP
 * - Proxying to Python backend with identity headers
 */

interface Env {
  BACKEND_URL: string;
  DEFAULT_AGENT: string;
  KV_PROJECTS: KVNamespace;
  GITHUB_CLIENT_ID: string;
  GITHUB_CLIENT_SECRET: string;
  INTERNAL_AUTH_SECRET: string;
}

interface ProjectACL {
  user_id: string;
  default: string;
  projects: string[];
}

/**
 * Main request handler
 */
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // CORS headers for all responses
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    };

    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    // OAuth callback handler (GitHub OAuth flow)
    if (url.pathname === '/auth/callback') {
      return handleOAuthCallback(request, env, corsHeaders);
    }

    // SSE endpoint for Remote MCP
    if (url.pathname === '/sse') {
      return handleSSE(request, env, corsHeaders);
    }

    // Health check
    if (url.pathname === '/health') {
      return new Response(JSON.stringify({
        status: 'ok',
        service: 'mharmless-remote-mcp',
        backend: env.BACKEND_URL
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    return new Response('Not Found', { status: 404, headers: corsHeaders });
  }
};

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

  if (!code) {
    return new Response('Missing code parameter', {
      status: 400,
      headers: corsHeaders
    });
  }

  try {
    // Exchange code for access token
    const tokenResponse = await fetch('https://github.com/login/oauth/access_token', {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        client_id: env.GITHUB_CLIENT_ID,
        client_secret: env.GITHUB_CLIENT_SECRET,
        code,
      }),
    });

    const tokenData = await tokenResponse.json() as { access_token?: string; error?: string };

    if (tokenData.error || !tokenData.access_token) {
      throw new Error(tokenData.error || 'Failed to get access token');
    }

    // Get user info from GitHub
    const userResponse = await fetch('https://api.github.com/user', {
      headers: {
        'Authorization': `Bearer ${tokenData.access_token}`,
        'Accept': 'application/json',
      },
    });

    const userData = await userResponse.json() as { login?: string; id?: number };

    // Store session (simplified - in production use encrypted cookies or session store)
    const sessionToken = crypto.randomUUID();

    // TODO: Store session in KV with expiry
    // await env.KV_PROJECTS.put(`session:${sessionToken}`, JSON.stringify({
    //   github_login: userData.login,
    //   github_id: userData.id,
    //   access_token: tokenData.access_token,
    // }), { expirationTtl: 86400 }); // 24 hours

    return new Response('OAuth successful! You can close this window.', {
      headers: {
        ...corsHeaders,
        'Set-Cookie': `session=${sessionToken}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=86400`,
      },
    });
  } catch (error) {
    return new Response(`OAuth error: ${error}`, {
      status: 500,
      headers: corsHeaders
    });
  }
}

/**
 * Handle SSE endpoint for Remote MCP
 */
async function handleSSE(
  request: Request,
  env: Env,
  corsHeaders: Record<string, string>
): Promise<Response> {
  const url = new URL(request.url);
  const projectId = url.searchParams.get('project');

  // Extract session from cookie or Authorization header
  const sessionToken = extractSessionToken(request);

  if (!sessionToken) {
    return new Response('Unauthorized - No session', {
      status: 401,
      headers: corsHeaders
    });
  }

  // TODO: Validate session and get user identity from KV
  // For now, use placeholder identity
  const userId = 'gh:placeholder'; // Should come from session validation
  const agentName = env.DEFAULT_AGENT; // Should be derived from GitHub login

  // Get user's project ACL from KV
  let userACL: ProjectACL | null = null;
  try {
    const aclData = await env.KV_PROJECTS.get(userId);
    if (aclData) {
      userACL = JSON.parse(aclData);
    }
  } catch (error) {
    console.error('Error reading KV_PROJECTS:', error);
  }

  // Determine project to use
  let selectedProject = projectId;
  if (!selectedProject && userACL) {
    selectedProject = userACL.default;
  }

  // Validate project access
  if (!selectedProject) {
    return new Response('Error: No project specified and no default project configured', {
      status: 400,
      headers: corsHeaders,
    });
  }

  if (userACL && !userACL.projects.includes(selectedProject)) {
    return new Response(`Error: Access denied to project '${selectedProject}'`, {
      status: 403,
      headers: corsHeaders,
    });
  }

  // Forward request to Python backend with identity headers
  const backendUrl = `${env.BACKEND_URL}/mcp/sse`;

  const backendHeaders = new Headers(request.headers);
  backendHeaders.set('X-User-Id', userId);
  backendHeaders.set('X-Agent-Name', agentName);
  backendHeaders.set('X-Project-Id', selectedProject);
  backendHeaders.set('X-Internal-Auth', env.INTERNAL_AUTH_SECRET);

  try {
    const backendResponse = await fetch(backendUrl, {
      method: request.method,
      headers: backendHeaders,
      body: request.method === 'POST' ? request.body : undefined,
    });

    // Stream response from backend
    return new Response(backendResponse.body, {
      status: backendResponse.status,
      headers: {
        ...corsHeaders,
        'Content-Type': backendResponse.headers.get('Content-Type') || 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });
  } catch (error) {
    return new Response(`Backend error: ${error}`, {
      status: 502,
      headers: corsHeaders,
    });
  }
}

/**
 * Extract session token from cookie or Authorization header
 */
function extractSessionToken(request: Request): string | null {
  // Try cookie first
  const cookieHeader = request.headers.get('Cookie');
  if (cookieHeader) {
    const cookies = cookieHeader.split(';').map(c => c.trim());
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
