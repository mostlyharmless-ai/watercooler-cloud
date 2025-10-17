/**
 * Cloudflare Worker - Remote MCP with OAuth and Project Authorization
 *
 * Implements Remote MCP server using @modelcontextprotocol/sdk
 * Maps each MCP tool to backend JSON endpoints with identity headers
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { SSEServerTransport } from '@modelcontextprotocol/sdk/server/sse.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';

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

interface SessionData {
  github_login: string;
  github_id: number;
}

/**
 * Main request handler
 */
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // CORS headers
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    // OAuth callback
    if (url.pathname === '/auth/callback') {
      return handleOAuthCallback(request, env, corsHeaders);
    }

    // SSE endpoint for Remote MCP
    if (url.pathname === '/sse') {
      return handleMCP(request, env, corsHeaders);
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

    if (!userData.login || !userData.id) {
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
 * Handle MCP requests via SSE transport
 */
async function handleMCP(
  request: Request,
  env: Env,
  corsHeaders: Record<string, string>
): Promise<Response> {
  const url = new URL(request.url);
  const projectId = url.searchParams.get('project');

  // Extract and validate session
  const sessionToken = extractSessionToken(request);
  if (!sessionToken) {
    return new Response('Unauthorized - No session', {
      status: 401,
      headers: corsHeaders
    });
  }

  // Resolve identity from session (with dev mode support)
  const identity = await resolveIdentity(sessionToken, env);
  if (!identity) {
    return new Response('Unauthorized - Invalid session', {
      status: 401,
      headers: corsHeaders
    });
  }

  // Get user's project ACL
  let userACL: ProjectACL | null = null;
  try {
    const aclData = await env.KV_PROJECTS.get(identity.userId);
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

  if (!selectedProject) {
    return new Response('Error: No project specified and no default project configured', {
      status: 400,
      headers: corsHeaders,
    });
  }

  // Validate project access
  if (userACL && !userACL.projects.includes(selectedProject)) {
    return new Response(`Error: Access denied to project '${selectedProject}'`, {
      status: 403,
      headers: corsHeaders,
    });
  }

  // Create MCP server
  const server = new Server(
    {
      name: 'watercooler-remote',
      version: '0.1.0',
    },
    {
      capabilities: {
        tools: {},
      },
    }
  );

  // Tool definitions
  const TOOLS = [
    {
      name: 'watercooler_v1_health',
      description: 'Check server health and configuration',
      inputSchema: { type: 'object', properties: {}, additionalProperties: false },
    },
    {
      name: 'watercooler_v1_whoami',
      description: 'Get your resolved agent identity',
      inputSchema: { type: 'object', properties: {}, additionalProperties: false },
    },
    {
      name: 'watercooler_v1_list_threads',
      description: 'List all watercooler threads',
      inputSchema: {
        type: 'object',
        properties: {
          open_only: { type: 'boolean', description: 'Filter by open status' },
          limit: { type: 'number', default: 50 },
          cursor: { type: 'string' },
          format: { type: 'string', default: 'markdown' },
        },
        additionalProperties: false,
      },
    },
    {
      name: 'watercooler_v1_read_thread',
      description: 'Read the complete content of a watercooler thread',
      inputSchema: {
        type: 'object',
        properties: {
          topic: { type: 'string', description: 'Thread topic identifier' },
          from_entry: { type: 'number', default: 0 },
          limit: { type: 'number', default: 100 },
          format: { type: 'string', default: 'markdown' },
        },
        required: ['topic'],
        additionalProperties: false,
      },
    },
    {
      name: 'watercooler_v1_say',
      description: 'Add your response to a thread and flip the ball',
      inputSchema: {
        type: 'object',
        properties: {
          topic: { type: 'string', description: 'Thread topic identifier' },
          title: { type: 'string', description: 'Entry title' },
          body: { type: 'string', description: 'Full entry content' },
          role: { type: 'string', default: 'implementer' },
          entry_type: { type: 'string', default: 'Note' },
        },
        required: ['topic', 'title', 'body'],
        additionalProperties: false,
      },
    },
    {
      name: 'watercooler_v1_ack',
      description: 'Acknowledge a thread without flipping the ball',
      inputSchema: {
        type: 'object',
        properties: {
          topic: { type: 'string', description: 'Thread topic identifier' },
          title: { type: 'string', default: '' },
          body: { type: 'string', default: '' },
        },
        required: ['topic'],
        additionalProperties: false,
      },
    },
    {
      name: 'watercooler_v1_handoff',
      description: 'Hand off the ball to another agent',
      inputSchema: {
        type: 'object',
        properties: {
          topic: { type: 'string', description: 'Thread topic identifier' },
          note: { type: 'string', default: '' },
          target_agent: { type: 'string' },
        },
        required: ['topic'],
        additionalProperties: false,
      },
    },
    {
      name: 'watercooler_v1_set_status',
      description: 'Update the status of a thread',
      inputSchema: {
        type: 'object',
        properties: {
          topic: { type: 'string', description: 'Thread topic identifier' },
          status: { type: 'string', description: 'New status value' },
        },
        required: ['topic', 'status'],
        additionalProperties: false,
      },
    },
    {
      name: 'watercooler_v1_reindex',
      description: 'Generate and return the index content',
      inputSchema: { type: 'object', properties: {}, additionalProperties: false },
    },
  ];

  // Register tool handlers
  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: TOOLS,
  }));

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;

    try {
      // Call backend JSON endpoint
      const backendUrl = `${env.BACKEND_URL}/mcp/${name}`;
      const backendResponse = await fetch(backendUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Id': identity.userId,
          'X-Agent-Name': identity.agentName,
          'X-Project-Id': selectedProject,
          'X-Internal-Auth': env.INTERNAL_AUTH_SECRET,
        },
        body: JSON.stringify(args || {}),
      });

      if (!backendResponse.ok) {
        const errorText = await backendResponse.text();
        throw new Error(`Backend error: ${backendResponse.status} - ${errorText}`);
      }

      const result = await backendResponse.json();

      return {
        content: [
          {
            type: 'text',
            text: result.content || JSON.stringify(result),
          },
        ],
      };
    } catch (error) {
      return {
        content: [
          {
            type: 'text',
            text: `Error calling ${name}: ${error}`,
          },
        ],
        isError: true,
      };
    }
  });

  // Create SSE transport
  const transport = new SSEServerTransport('/sse', request);

  await server.connect(transport);

  return transport.getResponse();
}

/**
 * Resolve identity from session token
 */
async function resolveIdentity(
  sessionToken: string,
  env: Env
): Promise<{ userId: string; agentName: string } | null> {
  // Dev mode: allow session=dev for local testing
  if (sessionToken === 'dev') {
    return {
      userId: 'gh:dev',
      agentName: 'Dev',
    };
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
