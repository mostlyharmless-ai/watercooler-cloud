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
  AGENT_TYPE: string; // AI agent type (e.g., "Codex", "Claude")
  KV_PROJECTS: KVNamespace;
  GITHUB_CLIENT_ID: string;
  GITHUB_CLIENT_SECRET: string;
  INTERNAL_AUTH_SECRET: string;
  ALLOW_DEV_SESSION?: string; // "true" to enable dev mode
  // When "true", allow watercooler_v1_set_project to automatically add
  // the requested project to the caller's ACL if it doesn't exist yet.
  // This is useful during development or when you want on-demand project creation
  // without out-of-band ACL seeding. Auto-enrollment validates against actual
  // projects on the backend to prevent filesystem artifacts from being added.
  AUTO_ENROLL_PROJECTS?: string;
  SESSION_MANAGER: DurableObjectNamespace;
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

interface TokenData {
  userId: string;
  createdAt: number;
  expiresAt: number;
  note?: string;
}

/**
 * Validate if a project exists on the backend by checking for thread data or marker file
 */
async function validateProjectExists(projectName: string, env: Env): Promise<boolean> {
  try {
    const response = await fetch(`${env.BACKEND_URL}/admin/discover-projects`, {
      method: 'POST',
      headers: {
        'X-Internal-Auth': env.INTERNAL_AUTH_SECRET || '',
        'Content-Type': 'application/json'
      }
    });

    if (!response.ok) {
      console.log(JSON.stringify({ event: 'project_validation_failed', status: response.status }));
      return false;
    }

    const data = await response.json() as {
      projects_by_user?: Record<string, Array<{
        project_id: string,
        has_threads: boolean,
        has_marker: boolean
      }>>
    };

    // Check if project exists with thread data OR marker file across all users
    for (const projects of Object.values(data.projects_by_user || {})) {
      for (const project of projects) {
        if (project.project_id === projectName && (project.has_threads || project.has_marker)) {
          return true;
        }
      }
    }

    return false;
  } catch (err: any) {
    console.log(JSON.stringify({ event: 'project_validation_error', error: String(err?.message || err) }));
    return false;
  }
}

/**
 * Map MCP method to backend endpoint
 */
function mapMethodToEndpoint(method: string): string {
  if (method === 'tools/call') {
    return '/mcp/'; // Will be appended with tool name
  }
  // For other methods, return base path (not used in current implementation)
  return '/mcp';
}

/**
 * Tool definitions for tools/list
 */
const TOOL_DEFS = [
  { name: 'watercooler_v1_health', description: 'Check server health and configuration', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'watercooler_v1_whoami', description: 'Get your resolved agent identity', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'watercooler_v1_list_threads', description: 'List all watercooler threads', inputSchema: { type: 'object', properties: { open_only: { type: 'boolean' }, limit: { type: 'number' }, cursor: { type: 'string' }, format: { type: 'string', enum: ['markdown'] }, project: { type: 'string', description: 'Optional: target a specific project instead of current session project' } }, additionalProperties: false } },
  { name: 'watercooler_v1_read_thread', description: 'Read full thread content', inputSchema: { type: 'object', properties: { topic: { type: 'string' }, from_entry: { type: 'number' }, limit: { type: 'number' }, format: { type: 'string', enum: ['markdown'] }, project: { type: 'string', description: 'Optional: target a specific project instead of current session project' } }, required: ['topic'], additionalProperties: false } },
  { name: 'watercooler_v1_say', description: 'Add entry and flip ball', inputSchema: { type: 'object', properties: { topic: { type: 'string' }, title: { type: 'string' }, body: { type: 'string' }, role: { type: 'string' }, entry_type: { type: 'string' }, project: { type: 'string', description: 'Optional: target a specific project instead of current session project' }, create_if_missing: { type: 'boolean', description: 'Create thread if it does not exist (default: false)', default: false } }, required: ['topic', 'title', 'body'], additionalProperties: false } },
  { name: 'watercooler_v1_ack', description: 'Acknowledge thread', inputSchema: { type: 'object', properties: { topic: { type: 'string' }, title: { type: 'string' }, body: { type: 'string' }, project: { type: 'string', description: 'Optional: target a specific project instead of current session project' } }, required: ['topic'], additionalProperties: false } },
  { name: 'watercooler_v1_handoff', description: 'Hand off ball to another agent', inputSchema: { type: 'object', properties: { topic: { type: 'string' }, note: { type: 'string' }, target_agent: { type: 'string' }, project: { type: 'string', description: 'Optional: target a specific project instead of current session project' } }, required: ['topic'], additionalProperties: false } },
  { name: 'watercooler_v1_set_status', description: 'Update thread status', inputSchema: { type: 'object', properties: { topic: { type: 'string' }, status: { type: 'string' }, project: { type: 'string', description: 'Optional: target a specific project instead of current session project' } }, required: ['topic', 'status'], additionalProperties: false } },
  { name: 'watercooler_v1_reindex', description: 'Generate and return the index content', inputSchema: { type: 'object', properties: { project: { type: 'string', description: 'Optional: target a specific project instead of current session project' } }, additionalProperties: false } },
  { name: 'watercooler_v1_set_project', description: 'Bind this session to a project', inputSchema: { type: 'object', properties: { project: { type: 'string' } }, required: ['project'], additionalProperties: false } },
  { name: 'watercooler_v1_set_agent', description: 'Set AI agent identity for this session', inputSchema: { type: 'object', properties: { base: { type: 'string', description: 'Base agent name (e.g., "Claude", "Codex")' }, spec: { type: 'string', description: 'Optional specialization (e.g., "technical-documentation-specialist")' } }, required: ['base'], additionalProperties: false } },
  { name: 'watercooler_v1_list_projects', description: 'List allowed projects for the current user', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'watercooler_v1_create_project', description: 'Create a new project with marker file', inputSchema: { type: 'object', properties: { project: { type: 'string', description: 'Project name (alphanumeric, hyphens, underscores only)' }, description: { type: 'string', description: 'Optional project description' } }, required: ['project'], additionalProperties: false } },
];

/**
 * SessionManager Durable Object
 * Holds per-session state: identity, project, SSE controller
 */
export class SessionManager {
  state: DurableObjectState;
  env: Env;
  controller: ReadableStreamDefaultController<Uint8Array> | null = null;
  identity: { userId: string; agentName: string } | null = null;
  projectId: string | null = null;
  lastSeen: number = Date.now();

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
    // Load persisted state asynchronously
    this.state.blockConcurrencyWhile(async () => {
      const stored = await this.state.storage.get<{ projectId?: string; agentName?: string }>('session');
      if (stored?.projectId) {
        this.projectId = stored.projectId;
      }
      // Load persisted agent name if available
      if (stored?.agentName && this.identity) {
        this.identity.agentName = stored.agentName;
      }
    });
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    console.log(JSON.stringify({ event: 'do_fetch_called', pathname: url.pathname, method: request.method }));

    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-User-Id, X-Agent-Name, X-Project-Id, X-Internal-Auth',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    // Simple ping to positively verify DO execution path and logging
    if (url.pathname === '/do/ping') {
      console.log(JSON.stringify({ event: 'do_ping' }));
      return new Response('pong', { status: 200, headers: { ...corsHeaders, 'Content-Type': 'text/plain' } });
    }

    if (url.pathname === '/do/sse') {
      console.log(JSON.stringify({ event: 'do_routing_to_sse' }));
      return this.handleSSE(request, corsHeaders);
    }

    if (url.pathname === '/do/messages') {
      return this.handleMessages(request, corsHeaders);
    }

    console.log(JSON.stringify({ event: 'do_path_not_found', pathname: url.pathname }));
    return new Response('Not Found', { status: 404, headers: corsHeaders });
  }

  async handleSSE(request: Request, corsHeaders: Record<string, string>): Promise<Response> {
    // Extract identity from headers (set by Worker after auth)
    const userId = request.headers.get('X-User-Id') || '';
    let agentName = request.headers.get('X-Agent-Name') || this.env.DEFAULT_AGENT;
    const projectId = request.headers.get('X-Project-Id') || '';

    if (!userId || !projectId) {
      return new Response('Missing identity headers', { status: 400, headers: corsHeaders });
    }

    // Check for persisted agent name (from set_agent tool)
    const stored = await this.state.storage.get<{ projectId?: string; agentName?: string }>('session');
    if (stored?.agentName) {
      agentName = stored.agentName; // Prefer persisted agent over header
    }

    this.identity = { userId, agentName };
    this.projectId = projectId;
    this.lastSeen = Date.now();

    const sessionId = new URL(request.url).searchParams.get('sessionId') || '';
    console.log(JSON.stringify({ event: 'session_open', sessionId, user: userId, project: projectId }));

    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start: (controller) => {
        this.controller = controller;
        // Send endpoint event
        controller.enqueue(encoder.encode(`event: endpoint\ndata: /messages?sessionId=${sessionId}\n\n`));
        console.log(JSON.stringify({ event: 'endpoint_sent', sessionId }));

        // Heartbeat to keep connection alive
        const heartbeat = setInterval(() => {
          try {
            controller.enqueue(encoder.encode(': keep-alive\n\n'));
            this.lastSeen = Date.now();
          } catch (e) {
            clearInterval(heartbeat);
          }
        }, 15000);

        // Clean up on close
        this.state.waitUntil((async () => {
          await new Promise(resolve => setTimeout(resolve, 3600000)); // 1 hour max
          clearInterval(heartbeat);
        })());
      },
      cancel: () => {
        this.controller = null;
        console.log(JSON.stringify({ event: 'session_close', sessionId, user: userId }));
      }
    });

    return new Response(stream, {
      headers: {
        ...corsHeaders,
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });
  }

  async getUserACL(): Promise<ProjectACL | null> {
    if (!this.identity) return null;
    try {
      const aclKey = `user:${this.identity.userId}`;
      const aclData = await this.env.KV_PROJECTS.get(aclKey);
      if (aclData) {
        return JSON.parse(aclData) as ProjectACL;
      }
    } catch (e) {
      console.error('Error loading ACL:', e);
    }
    return null;
  }

  async handleMessages(request: Request, corsHeaders: Record<string, string>): Promise<Response> {
    if (!this.controller || !this.identity || !this.projectId) {
      return new Response('Invalid session', { status: 400, headers: corsHeaders });
    }

    this.lastSeen = Date.now();

    let payload: any;
    try {
      payload = await request.json();
    } catch {
      return new Response('Invalid JSON', { status: 400, headers: corsHeaders });
    }

    const messages = Array.isArray(payload) ? payload : [payload];
    for (const msg of messages) {
      await this.handleJsonRpc(msg);
    }

    return new Response('Accepted', { status: 202, headers: corsHeaders });
  }

  async handleJsonRpc(message: any) {
    const encoder = new TextEncoder();
    const send = (obj: any) => {
      if (this.controller) {
        const chunk = `event: message\ndata: ${JSON.stringify(obj)}\n\n`;
        this.controller.enqueue(encoder.encode(chunk));
      }
    };

    const id = message.id;
    const method = message.method;
    const params = message.params || {};

    // Handle initialize
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

    // Handle tools/list
    if (method === 'tools/list') {
      return send({ jsonrpc: '2.0', id, result: { tools: TOOL_DEFS } });
    }

    // Handle tools/call
    if (method === 'tools/call') {
      const name = params.name as string;
      const args = (params.arguments as Record<string, unknown>) || {};
      // Local tool: set project context within this session (no backend call)
      if (name === 'watercooler_v1_set_project') {
        try {
          const requested = String(args['project'] || '').trim();
          if (!requested) {
            return send({ jsonrpc: '2.0', id, error: { code: -32602, message: 'Missing project' } });
          }
          // Load ACL for current user
          let allowed: string[] = [];
          let aclObj: ProjectACL | null = null;
          try {
            const aclKey = `user:${this.identity!.userId}`;
            const aclData = await this.env.KV_PROJECTS.get(aclKey);
            if (aclData) {
              const acl = JSON.parse(aclData) as ProjectACL;
              aclObj = acl;
              allowed = Array.isArray(acl.projects) ? acl.projects : [];
            }
          } catch {}
          if (!allowed.includes(requested)) {
            const canAutoEnroll = this.env.AUTO_ENROLL_PROJECTS === 'true' || this.env.ALLOW_DEV_SESSION === 'true';
            if (canAutoEnroll) {
              // Validate project exists on backend before auto-enrolling
              const projectExists = await validateProjectExists(requested, this.env);
              if (!projectExists) {
                console.log(JSON.stringify({ event: 'acl_denied', reason: 'project_not_found_on_backend', user: this.identity!.userId, project: requested }));
                return send({ jsonrpc: '2.0', id, error: { code: -32000, message: `Project '${requested}' does not exist on backend or has no thread data` } });
              }
              // Create or update user's ACL to include the requested project
              const userId = this.identity!.userId;
              const aclKey = `user:${userId}`;
              const next: ProjectACL = aclObj ?? { user_id: userId, default: requested, projects: [] };
              if (!next.projects.includes(requested)) next.projects.push(requested);
              if (!next.default) next.default = requested;
              await this.env.KV_PROJECTS.put(aclKey, JSON.stringify(next));
              allowed = next.projects;
              console.log(JSON.stringify({ event: 'acl_enrolled_project', user: userId, project: requested }));
            } else {
              console.log(JSON.stringify({ event: 'acl_denied', reason: 'project_not_in_allowlist', user: this.identity!.userId, project: requested }));
              return send({ jsonrpc: '2.0', id, error: { code: -32000, message: 'Access denied for project' } });
            }
          }
          this.projectId = requested;
          // Persist project to durable storage
          await this.state.storage.put('session', { projectId: requested });
          console.log(JSON.stringify({ event: 'session_project_set', user: this.identity!.userId, project: requested }));
          // Normalize result to MCP content shape so clients reliably render output
          const payload = { project: requested, message: 'Project context set for this session' };
          const normalized = normalizeMcpResult(payload);
          return send({ jsonrpc: '2.0', id, result: normalized });
        } catch (err: any) {
          return send({ jsonrpc: '2.0', id, error: { code: -32603, message: 'Failed to set project', data: String(err?.message || err) } });
        }
      }

      // Local tool: set agent identity for this session (no backend call)
      if (name === 'watercooler_v1_set_agent') {
        try {
          const base = String(args['base'] || '').trim();
          const spec = args['spec'] ? String(args['spec']).trim() : undefined;

          if (!base) {
            return send({ jsonrpc: '2.0', id, error: { code: -32602, message: 'Missing base agent name' } });
          }

          // Construct agent name (base or base:spec)
          const agentName = spec ? `${base}:${spec}` : base;

          // Update session identity
          if (this.identity) {
            this.identity.agentName = agentName;
          }

          // Persist to durable storage
          const stored = await this.state.storage.get<{ projectId?: string; agentName?: string }>('session') || {};
          stored.agentName = agentName;
          await this.state.storage.put('session', stored);

          console.log(JSON.stringify({
            event: 'session_agent_set',
            user: this.identity!.userId,
            agent: agentName
          }));

          // Normalize result to MCP content shape so clients reliably render output
          const payload = { agent: agentName, message: 'Agent identity set for this session' };
          const normalized = normalizeMcpResult(payload);
          return send({ jsonrpc: '2.0', id, result: normalized });
        } catch (err: any) {
          return send({ jsonrpc: '2.0', id, error: { code: -32603, message: 'Failed to set agent', data: String(err?.message || err) } });
        }
      }

      if (name === 'watercooler_v1_list_projects') {
        try {
          const aclKey = `user:${this.identity!.userId}`;
          const aclData = await this.env.KV_PROJECTS.get(aclKey);
          let result = { default: null as string | null, projects: [] as string[] };
          if (aclData) {
            const acl = JSON.parse(aclData) as ProjectACL;
            result = {
              default: acl.default || null,
              projects: Array.isArray(acl.projects) ? acl.projects : [],
            };
          }
          // Safe fallback: if ACL exists but yields no projects, include current session project when available
          if ((!result.projects || result.projects.length === 0) && this.projectId) {
            console.log(JSON.stringify({ event: 'list_projects_empty_acl_fallback', user: this.identity!.userId, session_project: this.projectId }));
            result.projects = [this.projectId];
            if (!result.default) result.default = this.projectId;
          }
          // Emit debug when still empty to aid staging diagnostics
          if (!result.projects || result.projects.length === 0) {
            console.log(JSON.stringify({ event: 'list_projects_empty_result', user: this.identity!.userId, acl_present: Boolean(aclData) }));
          } else {
            console.log(JSON.stringify({ event: 'list_projects_ok', user: this.identity!.userId, count: result.projects.length }));
          }
          // Normalize to MCP content so clients see output consistently
          const normalized = normalizeMcpResult(result);
          return send({ jsonrpc: '2.0', id, result: normalized });
        } catch (err: any) {
          return send({ jsonrpc: '2.0', id, error: { code: -32603, message: 'Failed to list projects', data: String(err?.message || err) } });
        }
      }

      if (name === 'watercooler_v1_create_project') {
        try {
          const project = args['project'] as string;
          const description = (args['description'] as string) || '';

          if (!project) {
            return send({ jsonrpc: '2.0', id, error: { code: -32602, message: 'Missing project parameter' } });
          }

          // Call backend to create project
          const response = await fetch(`${this.env.BACKEND_URL}/admin/create-project`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Internal-Auth': this.env.INTERNAL_AUTH_SECRET || '',
              'X-User-Id': this.identity!.userId,
              'X-Agent-Name': this.identity!.agentName
            },
            body: JSON.stringify({ project, description })
          });

          if (!response.ok) {
            const errorText = await response.text();
            return send({ jsonrpc: '2.0', id, error: { code: -32603, message: 'Backend create-project failed', data: errorText } });
          }

          const result = await response.json();

          // Auto-enroll user in the new project if AUTO_ENROLL enabled
          if (this.env.AUTO_ENROLL_PROJECTS === 'true' || this.env.ALLOW_DEV_SESSION === 'true') {
            const aclKey = `user:${this.identity!.userId}`;
            const aclData = await this.env.KV_PROJECTS.get(aclKey);
            const acl = aclData ? JSON.parse(aclData) : { user_id: this.identity!.userId, default: project, projects: [] };
            if (!acl.projects.includes(project)) {
              acl.projects.push(project);
            }
            if (!acl.default) {
              acl.default = project;
            }
            await this.env.KV_PROJECTS.put(aclKey, JSON.stringify(acl));
            console.log(JSON.stringify({ event: 'create_project_auto_enrolled', user: this.identity!.userId, project }));
          }

          const normalized = normalizeMcpResult(result);
          return send({ jsonrpc: '2.0', id, result: normalized });
        } catch (err: any) {
          return send({ jsonrpc: '2.0', id, error: { code: -32603, message: 'Failed to create project', data: String(err?.message || err) } });
        }
      }

      try {
        // Determine target project: explicit param overrides session project
        const explicitProject = args['project'] as string | undefined;
        const targetProject = explicitProject || this.projectId;

        if (!targetProject) {
          return send({ jsonrpc: '2.0', id, error: { code: -32001, message: 'Project not set. Call watercooler_v1_set_project first.' } });
        }

        // Validate ACL for target project
        if (explicitProject && explicitProject !== this.projectId) {
          // Cross-project access - verify user has access
          try {
            const aclKey = `user:${this.identity!.userId}`;
            const aclData = await this.env.KV_PROJECTS.get(aclKey);
            if (aclData) {
              const acl = JSON.parse(aclData) as ProjectACL;
              if (!acl.projects.includes(explicitProject)) {
                console.log(JSON.stringify({ event: 'cross_project_denied', user: this.identity!.userId, from: this.projectId, to: explicitProject }));
                return send({ jsonrpc: '2.0', id, error: { code: -32000, message: `Access denied for project: ${explicitProject}` } });
              }
            } else {
              return send({ jsonrpc: '2.0', id, error: { code: -32000, message: 'Access denied - no ACL entry' } });
            }
          } catch (e) {
            return send({ jsonrpc: '2.0', id, error: { code: -32603, message: 'Error validating project access' } });
          }
          console.log(JSON.stringify({ event: 'cross_project_access', user: this.identity!.userId, from: this.projectId, to: explicitProject, tool: name }));
        }

        // Thread existence checking for thread-specific operations
        const threadTools = ['watercooler_v1_say', 'watercooler_v1_read_thread', 'watercooler_v1_ack', 'watercooler_v1_handoff', 'watercooler_v1_set_status'];
        const topic = args['topic'] as string | undefined;
        const createIfMissing = args['create_if_missing'] === true;

        if (threadTools.includes(name) && topic && !createIfMissing) {
          // Check if thread exists in target project
          const checkResponse = await fetch(`${this.env.BACKEND_URL}/mcp/watercooler_v1_list_threads`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Internal-Auth': this.env.INTERNAL_AUTH_SECRET,
              'X-User-Id': this.identity!.userId,
              'X-Agent-Name': this.identity!.agentName,
              'X-Project-Id': targetProject,
            },
            body: JSON.stringify({}),
          });

          if (checkResponse.ok) {
            const listResult = await checkResponse.json();
            // Parse result to check if thread exists
            let threadExists = false;
            let otherProjects: string[] = [];

            // The backend returns content as a string
            if (listResult?.content) {
              const text = listResult.content;
              // Simple check: does the topic appear in the thread list?
              threadExists = text.includes(`**${topic}**`) || text.includes(`topic: ${topic}`) || text.includes(topic);
            }

            if (!threadExists) {
              // Check other projects to provide helpful error
              const userACL = await this.getUserACL();
              if (userACL) {
                for (const proj of userACL.projects) {
                  if (proj === targetProject) continue;
                  const otherCheck = await fetch(`${this.env.BACKEND_URL}/mcp/watercooler_v1_list_threads`, {
                    method: 'POST',
                    headers: {
                      'Content-Type': 'application/json',
                      'X-Internal-Auth': this.env.INTERNAL_AUTH_SECRET,
                      'X-User-Id': this.identity!.userId,
                      'X-Agent-Name': this.identity!.agentName,
                      'X-Project-Id': proj,
                    },
                    body: JSON.stringify({}),
                  });
                  if (otherCheck.ok) {
                    const otherResult = await otherCheck.json();
                    if (otherResult?.content) {
                      const text = otherResult.content;
                      if (text.includes(`**${topic}**`) || text.includes(`topic: ${topic}`) || text.includes(topic)) {
                        otherProjects.push(proj);
                      }
                    }
                  }
                }
              }

              const errorMsg = otherProjects.length > 0
                ? `Thread '${topic}' not found in project '${targetProject}'. Thread exists in: [${otherProjects.join(', ')}]. Use set_project or specify project explicitly.`
                : `Thread '${topic}' not found in project '${targetProject}'. Use create_if_missing=true to create it.`;

              console.log(JSON.stringify({ event: 'thread_not_found', topic, project: targetProject, found_in: otherProjects, user: this.identity!.userId }));
              return send({ jsonrpc: '2.0', id, error: { code: -32002, message: errorMsg } });
            }
          }
        }

        // Forward to backend with target project
        const response = await fetch(`${this.env.BACKEND_URL}/mcp/${name}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Internal-Auth': this.env.INTERNAL_AUTH_SECRET,
            'X-User-Id': this.identity!.userId,
            'X-Agent-Name': this.identity!.agentName,
            'X-Project-Id': targetProject,
          },
          body: JSON.stringify(args),
        });

        const result = await response.json();

        if (response.ok) {
          const isCrossProject = explicitProject && explicitProject !== this.projectId;
          console.log(JSON.stringify({ event: 'do_dispatch_ok', method, tool: name, user: this.identity!.userId, project: targetProject, cross_project: isCrossProject }));
          // Normalize to MCP tool result shape and add metadata
          const normalized = normalizeMcpResult(result);
          // Add project_id to response metadata
          const metadata = {
            project_id: targetProject,
            cross_project: isCrossProject,
            session_project: this.projectId,
          };
          send({ jsonrpc: '2.0', id, result: { ...normalized, _metadata: metadata } });
        } else {
          console.log(JSON.stringify({ event: 'do_dispatch_err', method, tool: name, status: response.status, user: this.identity!.userId }));
          send({ jsonrpc: '2.0', id, error: { code: -32603, message: 'Tool call failed', data: result } });
        }
      } catch (err: any) {
        console.log(JSON.stringify({ event: 'do_dispatch_err', method, tool: name, error: err.message, user: this.identity!.userId }));
        send({ jsonrpc: '2.0', id, error: { code: -32603, message: 'Internal error', data: err.message } });
      }
      return;
    }

    // Unknown method
    return send({ jsonrpc: '2.0', id, error: { code: -32601, message: `Method not found: ${method}` } });
  }
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
    // OAuth/OIDC Well-known discovery endpoints (for mcp-remote http-first)
    if (url.pathname === '/.well-known/oauth-protected-resource') return handleWellKnownResource(request, env, corsHeaders);
    if (url.pathname === '/.well-known/oauth-authorization-server' || url.pathname.endsWith('/.well-known/oauth-authorization-server')) return handleWellKnownOAuthAS(request, env, corsHeaders);
    if (url.pathname === '/.well-known/openid-configuration' || url.pathname.endsWith('/.well-known/openid-configuration')) return handleWellKnownOIDC(request, env, corsHeaders);
    // OAuth Dynamic Client Registration / Token / Authorize
    if (url.pathname === '/register') return handleOAuthRegister(request, env, corsHeaders);
    if (url.pathname === '/authorize') return handleOAuthAuthorize(request, env, corsHeaders);
    if (url.pathname === '/token') return handleOAuthToken(request, env, corsHeaders);
    if (url.pathname === '/auth/login') return handleAuthLogin(request, env, corsHeaders);
    if (url.pathname === '/auth/callback') return handleOAuthCallback(request, env, corsHeaders);
    // JSON auth preflight stubs for clients that expect status/registration
    if (url.pathname === '/auth/status') return handleAuthStatus(request, env, corsHeaders);
    if (url.pathname === '/auth/register') return handleAuthRegister(request, env, corsHeaders);
    // Generic /auth and /auth/* preflight handlers (avoid 404 from clients expecting JSON)
    if (url.pathname === '/auth') return handleAuthStatus(request, env, corsHeaders);
    if (url.pathname.startsWith('/auth/')) {
      // Allow unknown subpaths by returning status for GET/head and register for POST
      if (request.method === 'GET' || request.method === 'HEAD') {
        return handleAuthStatus(request, env, corsHeaders);
      }
      if (request.method === 'POST') {
        return handleAuthRegister(request, env, corsHeaders);
      }
      return new Response(JSON.stringify({ error: 'Method Not Allowed' }), { status: 405, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
    }
    // Generic /oauth and /oauth/* preflight (some clients use this base path)
    if (url.pathname === '/oauth') return handleAuthStatus(request, env, corsHeaders);
    if (url.pathname.startsWith('/oauth/')) {
      if (request.method === 'GET' || request.method === 'HEAD') {
        return handleAuthStatus(request, env, corsHeaders);
      }
      if (request.method === 'POST') {
        return handleAuthRegister(request, env, corsHeaders);
      }
      return new Response(JSON.stringify({ error: 'Method Not Allowed' }), { status: 405, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
    }
    if (url.pathname === '/tokens/issue') return handleTokenIssue(request, env, corsHeaders);
    if (url.pathname === '/tokens/revoke') return handleTokenRevoke(request, env, corsHeaders);
    if (url.pathname === '/console') return handleConsole(request, env, corsHeaders);
    // Debug: DO liveness probe
    if (url.pathname === '/do-ping') {
      const id = env.SESSION_MANAGER.idFromName('ping');
      const stub = env.SESSION_MANAGER.get(id);
      const resp = await stub.fetch(`${url.origin}/do/ping`);
      return resp;
    }
    if (url.pathname === '/sse') return handleMCP(request, env, corsHeaders);
    if (url.pathname === '/messages') return handleMessages(request, env, corsHeaders);
    if (url.pathname === '/debug/last-sse') {
      const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
      try {
        const dbg = await env.KV_PROJECTS.get(`debug:last_sse:${ip}`);
        const body = dbg ? dbg : JSON.stringify({});
        return new Response(body, { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
      } catch {
        return new Response(JSON.stringify({}), { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
      }
    }
    if (url.pathname === '/health') {
      return new Response(JSON.stringify({ status: 'ok', service: 'watercooler-cloud-worker', backend: env.BACKEND_URL }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    if (url.pathname === '/debug/secrets') {
      return new Response(JSON.stringify({
        has_github_client_id: !!env.GITHUB_CLIENT_ID,
        github_client_id_length: env.GITHUB_CLIENT_ID?.length || 0,
        github_client_id_prefix: env.GITHUB_CLIENT_ID?.substring(0, 6) || 'undefined',
        has_github_client_secret: !!env.GITHUB_CLIENT_SECRET,
        has_internal_auth: !!env.INTERNAL_AUTH_SECRET
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    if (url.pathname === '/debug/envkeys') {
      // Expose the binding keys present on this env (for diagnostics only)
      const keys = Object.keys(env as unknown as Record<string, unknown>).sort();
      return new Response(JSON.stringify(keys), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    console.log(JSON.stringify({ event: 'route_not_found', path: url.pathname, method: request.method }));
    return new Response(JSON.stringify({ error: 'Not Found', path: url.pathname }), { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
  },
};

/**
 * Generate unique ULID-like ID (simplified version)
 */
function generateStateId(): string {
  return `${Date.now()}_${crypto.randomUUID()}`;
}

/**
 * Minimal JSON endpoints to satisfy clients that perform an auth preflight
 * before opening SSE. These do not change auth semantics; they simply return
 * JSON 200 when the existing Bearer token or cookie session is valid.
 */
async function handleAuthStatus(
  request: Request,
  env: Env,
  corsHeaders: Record<string, string>
): Promise<Response> {
  // Return 200 JSON regardless of auth to satisfy clients' preflight checks.
  // Include identity hints when available, but do NOT change data-plane auth.
  const clientIP = request.headers.get('CF-Connecting-IP') || 'unknown';
  let detail: any = { authenticated: false, method: 'none' };
  const bearerToken = extractBearerToken(request);
  if (bearerToken) {
    const id = await resolveTokenIdentity(bearerToken, env, clientIP);
    if (id) detail = { authenticated: true, userId: id.userId, method: 'bearer' };
  } else {
    const sessionToken = extractSessionToken(request);
    if (sessionToken) {
      const sess = await resolveIdentity(sessionToken, env);
      if (sess) detail = { authenticated: true, userId: sess.userId, method: 'cookie' };
    }
  }
  return new Response(JSON.stringify(detail), { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
}

async function handleAuthRegister(
  request: Request,
  env: Env,
  corsHeaders: Record<string, string>
): Promise<Response> {
  // Always return 200 JSON so clients proceed to SSE; include user when available
  const clientIP = request.headers.get('CF-Connecting-IP') || 'unknown';
  let body: any = { status: 'ok' };
  const bearerToken = extractBearerToken(request);
  if (bearerToken) {
    const id = await resolveTokenIdentity(bearerToken, env, clientIP);
    if (id) body.userId = id.userId;
  } else {
    const sessionToken = extractSessionToken(request);
    if (sessionToken) {
      const sess = await resolveIdentity(sessionToken, env);
      if (sess) body.userId = sess.userId;
    }
  }
  return new Response(JSON.stringify(body), { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
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

  // Debug: Log secret availability
  console.log(JSON.stringify({
    event: 'auth_login_debug',
    has_client_id: !!env.GITHUB_CLIENT_ID,
    client_id_length: env.GITHUB_CLIENT_ID?.length || 0,
    client_id_firstchars: env.GITHUB_CLIENT_ID?.substring(0, 4) || 'undefined'
  }));

  // Guard: required secrets must be present before building OAuth URL
  const missing: string[] = [];
  if (!env.GITHUB_CLIENT_ID) missing.push('GITHUB_CLIENT_ID');
  if (!env.GITHUB_CLIENT_SECRET) missing.push('GITHUB_CLIENT_SECRET');
  if (!env.INTERNAL_AUTH_SECRET) missing.push('INTERNAL_AUTH_SECRET');
  if (missing.length > 0) {
    console.log(JSON.stringify({ event: 'missing_secrets', missing }));
    return new Response(JSON.stringify({ error: 'missing_secrets', missing }), {
      status: 503,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }

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

/**
 * Handle token issuance - create CLI token for authenticated user
 */
async function handleTokenIssue(
  request: Request,
  env: Env,
  corsHeaders: Record<string, string>
): Promise<Response> {
  if (request.method !== 'POST') {
    return new Response('Method not allowed', { status: 405, headers: corsHeaders });
  }

  const clientIP = request.headers.get('CF-Connecting-IP') || 'unknown';

  // Require OAuth session
  const sessionToken = extractSessionToken(request);
  if (!sessionToken) {
    return new Response('Unauthorized - OAuth session required', {
      status: 401,
      headers: corsHeaders
    });
  }

  const identity = await resolveIdentity(sessionToken, env);
  if (!identity) {
    return new Response('Unauthorized - Invalid session', {
      status: 401,
      headers: corsHeaders
    });
  }

  // Rate limiting - 3 tokens per hour per user
  const rateLimitAllowed = await checkRateLimit(env, `token:issue:${identity.userId}`, 3, 3600);
  if (!rateLimitAllowed) {
    console.log(JSON.stringify({
      event: 'rate_limit_exceeded',
      endpoint: '/tokens/issue',
      user: identity.userId,
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));
    return new Response('Too many tokens created. Try again later.', {
      status: 429,
      headers: { ...corsHeaders, 'Retry-After': '3600' }
    });
  }

  // Parse request body
  let body: { note?: string; ttlSeconds?: number } = {};
  try {
    const contentType = request.headers.get('Content-Type') || '';
    if (contentType.includes('application/json')) {
      body = await request.json();
    }
  } catch (error) {
    return new Response('Invalid JSON', { status: 400, headers: corsHeaders });
  }

  // Generate token
  const tokenId = crypto.randomUUID();
  const ttl = body.ttlSeconds || 86400; // Default 24 hours
  const now = Date.now();

  const tokenData: TokenData = {
    userId: identity.userId,
    createdAt: now,
    expiresAt: now + (ttl * 1000),
    note: body.note,
  };

  // Store in KV
  await env.KV_PROJECTS.put(
    `token:${tokenId}`,
    JSON.stringify(tokenData),
    { expirationTtl: ttl }
  );

  // Log token issuance
  console.log(JSON.stringify({
    event: 'token_issue',
    user: identity.userId,
    token_id: tokenId.substring(0, 16),
    ttl,
    note: body.note || '',
    ip: clientIP,
    timestamp: new Date().toISOString(),
  }));

  // Return token (only shown once)
  return new Response(JSON.stringify({ token: tokenId, expiresAt: tokenData.expiresAt }), {
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
}

/**
 * Handle token revocation
 */
async function handleTokenRevoke(
  request: Request,
  env: Env,
  corsHeaders: Record<string, string>
): Promise<Response> {
  if (request.method !== 'POST') {
    return new Response('Method not allowed', { status: 405, headers: corsHeaders });
  }

  const clientIP = request.headers.get('CF-Connecting-IP') || 'unknown';

  // Require OAuth session
  const sessionToken = extractSessionToken(request);
  if (!sessionToken) {
    return new Response('Unauthorized - OAuth session required', {
      status: 401,
      headers: corsHeaders
    });
  }

  const identity = await resolveIdentity(sessionToken, env);
  if (!identity) {
    return new Response('Unauthorized - Invalid session', {
      status: 401,
      headers: corsHeaders
    });
  }

  // Rate limiting - prevent abuse
  const rateLimitAllowed = await checkRateLimit(env, `token:revoke:${identity.userId}`, 10, 3600);
  if (!rateLimitAllowed) {
    console.log(JSON.stringify({
      event: 'rate_limit_exceeded',
      endpoint: '/tokens/revoke',
      user: identity.userId,
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));
    return new Response('Too many revocation requests. Try again later.', {
      status: 429,
      headers: { ...corsHeaders, 'Retry-After': '3600' }
    });
  }

  // Parse request body
  let body: { tokenId?: string } = {};
  try {
    body = await request.json();
  } catch (error) {
    return new Response('Invalid JSON', { status: 400, headers: corsHeaders });
  }

  if (!body.tokenId) {
    return new Response('Missing tokenId', { status: 400, headers: corsHeaders });
  }

  // Verify token belongs to user before deleting
  const tokenData = await env.KV_PROJECTS.get(`token:${body.tokenId}`);
  if (tokenData) {
    const parsed: TokenData = JSON.parse(tokenData);
    if (parsed.userId !== identity.userId) {
      return new Response('Unauthorized - Token does not belong to you', {
        status: 403,
        headers: corsHeaders
      });
    }
  }

  // Delete token
  await env.KV_PROJECTS.delete(`token:${body.tokenId}`);

  // Log token revocation
  console.log(JSON.stringify({
    event: 'token_revoke',
    user: identity.userId,
    token_id: body.tokenId.substring(0, 16),
    ip: clientIP,
    timestamp: new Date().toISOString(),
  }));

  return new Response(JSON.stringify({ success: true }), {
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
}

/**
 * Handle console page - token management UI
 */
async function handleConsole(
  request: Request,
  env: Env,
  corsHeaders: Record<string, string>
): Promise<Response> {
  const clientIP = request.headers.get('CF-Connecting-IP') || 'unknown';

  // Require OAuth session
  const sessionToken = extractSessionToken(request);
  if (!sessionToken) {
    return new Response(
      'Unauthorized - Please login at /auth/login first',
      { status: 401, headers: corsHeaders }
    );
  }

  const identity = await resolveIdentity(sessionToken, env);
  if (!identity) {
    return new Response(
      'Unauthorized - Invalid session. Please login at /auth/login',
      { status: 401, headers: corsHeaders }
    );
  }

  // Get user's ACL
  let allowedProjects: string[] = [];
  try {
    const aclKey = `user:${identity.userId}`;
    const aclData = await env.KV_PROJECTS.get(aclKey);
    if (aclData) {
      const userACL: ProjectACL = JSON.parse(aclData);
      allowedProjects = userACL.projects || [];
    }
  } catch (error) {
    console.error('Error loading ACL:', error);
  }

  // Log console access
  console.log(JSON.stringify({
    event: 'console_view',
    user: identity.userId,
    ip: clientIP,
    timestamp: new Date().toISOString(),
  }));

  // Generate HTML
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Watercooler MCP Console</title>
  <style>
    body {
      font-family: system-ui, -apple-system, sans-serif;
      max-width: 800px;
      margin: 40px auto;
      padding: 0 20px;
      line-height: 1.6;
      color: #333;
    }
    h1 { color: #2563eb; }
    h2 { color: #1e40af; margin-top: 32px; }
    .info-box {
      background: #f3f4f6;
      border-left: 4px solid #2563eb;
      padding: 16px;
      margin: 16px 0;
    }
    .form-group {
      margin: 16px 0;
    }
    label {
      display: block;
      font-weight: 600;
      margin-bottom: 4px;
    }
    input, textarea {
      width: 100%;
      padding: 8px;
      border: 1px solid #d1d5db;
      border-radius: 4px;
      font-family: inherit;
    }
    button {
      background: #2563eb;
      color: white;
      padding: 10px 20px;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 600;
    }
    button:hover { background: #1e40af; }
    .token-result {
      background: #fef3c7;
      border: 1px solid #f59e0b;
      padding: 16px;
      margin: 16px 0;
      border-radius: 4px;
      word-break: break-all;
    }
    .error {
      background: #fee2e2;
      border: 1px solid #ef4444;
      padding: 16px;
      margin: 16px 0;
      border-radius: 4px;
    }
    .success {
      background: #d1fae5;
      border: 1px solid #10b981;
      padding: 16px;
      margin: 16px 0;
      border-radius: 4px;
    }
    code {
      background: #f3f4f6;
      padding: 2px 6px;
      border-radius: 3px;
      font-family: 'Monaco', 'Menlo', monospace;
    }
  </style>
</head>
<body>
  <h1>🌊 Watercooler MCP Console</h1>

  <div class="info-box">
    <strong>User:</strong> ${identity.userId}<br>
    <strong>Agent Name:</strong> ${identity.agentName}<br>
    <strong>Allowed Projects:</strong> ${allowedProjects.length > 0 ? allowedProjects.join(', ') : 'None (contact admin)'}
  </div>

  <h2>Create CLI Token</h2>
  <p>Generate a Personal MCP Token for CLI access. Token will be shown once - save it securely!</p>
  <p><strong>Rate limit:</strong> 3 tokens per hour</p>

  <div class="form-group">
    <label for="note">Note (optional)</label>
    <input type="text" id="note" placeholder="e.g., 'My dev laptop'">
  </div>

  <div class="form-group">
    <label for="ttl">TTL (seconds)</label>
    <input type="number" id="ttl" value="86400" placeholder="86400 (24 hours)">
  </div>

  <button onclick="createToken()">Create Token</button>

  <div id="tokenResult"></div>

  <h2>Revoke Token</h2>
  <p>Revoke a token by its ID. Once revoked, it cannot be used.</p>

  <div class="form-group">
    <label for="revokeId">Token ID</label>
    <input type="text" id="revokeId" placeholder="Enter full token UUID">
  </div>

  <button onclick="revokeToken()">Revoke Token</button>

  <div id="revokeResult"></div>

  <h2>Using Tokens</h2>
  <p>Configure your CLI client with:</p>
  <code>Authorization: Bearer &lt;your-token&gt;</code>

  <p>Example for mcp-remote:</p>
  <code>npx -y mcp-remote "https://mharmless-remote-mcp.mostlyharmless-ai.workers.dev/sse?project=proj-alpha" --header "Authorization: Bearer YOUR_TOKEN"</code>

  <script>
    async function createToken() {
      const note = document.getElementById('note').value;
      const ttl = parseInt(document.getElementById('ttl').value) || 86400;
      const resultDiv = document.getElementById('tokenResult');

      try {
        const response = await fetch('/tokens/issue', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ note, ttlSeconds: ttl }),
        });

        const data = await response.json();

        if (response.ok) {
          resultDiv.innerHTML = \`
            <div class="token-result">
              <strong>⚠️ Token created! Save this - it won't be shown again:</strong><br><br>
              <code>\${data.token}</code><br><br>
              <strong>Expires:</strong> \${new Date(data.expiresAt).toLocaleString()}
            </div>
          \`;
        } else {
          resultDiv.innerHTML = \`<div class="error">Error: \${response.status} - \${response.statusText}</div>\`;
        }
      } catch (error) {
        resultDiv.innerHTML = \`<div class="error">Error: \${error.message}</div>\`;
      }
    }

    async function revokeToken() {
      const tokenId = document.getElementById('revokeId').value.trim();
      const resultDiv = document.getElementById('revokeResult');

      if (!tokenId) {
        resultDiv.innerHTML = '<div class="error">Please enter a token ID</div>';
        return;
      }

      try {
        const response = await fetch('/tokens/revoke', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tokenId }),
        });

        if (response.ok) {
          resultDiv.innerHTML = '<div class="success">✓ Token revoked successfully</div>';
          document.getElementById('revokeId').value = '';
        } else {
          const text = await response.text();
          resultDiv.innerHTML = \`<div class="error">Error: \${response.status} - \${text}</div>\`;
        }
      } catch (error) {
        resultDiv.innerHTML = \`<div class="error">Error: \${error.message}</div>\`;
      }
    }
  </script>
</body>
</html>`;

  return new Response(html, {
    headers: { ...corsHeaders, 'Content-Type': 'text/html; charset=utf-8' },
  });
}

// Handle POSTed JSON-RPC messages and stream responses via SSE
async function handleMessages(
  request: Request,
  env: Env,
  corsHeaders: Record<string, string>
): Promise<Response> {
  const url = new URL(request.url);
  const sessionId = url.searchParams.get('sessionId') || '';

  if (!sessionId) {
    return new Response('Missing sessionId', { status: 400, headers: corsHeaders });
  }

  // Delegate to Durable Object
  const durableObjectId = env.SESSION_MANAGER.idFromName(sessionId);
  const stub = env.SESSION_MANAGER.get(durableObjectId);

  // Forward request to Durable Object
  const doRequest = new Request(`${url.origin}/do/messages?sessionId=${sessionId}`, {
    method: 'POST',
    headers: request.headers,
    body: request.body,
  });

  return await stub.fetch(doRequest);
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
  const clientIP = request.headers.get('CF-Connecting-IP') || 'unknown';

  // Log basic request auth signals for diagnostics (no secrets).
  const authHeader = request.headers.get('Authorization') || '';
  const hasBearer = authHeader.startsWith('Bearer ');
  const hasCookie = !!request.headers.get('Cookie');
  console.log(JSON.stringify({
    event: 'sse_request',
    has_bearer: hasBearer,
    has_cookie: hasCookie,
    project: projectId,
    ip: clientIP,
    timestamp: new Date().toISOString(),
  }));
  // Persist last SSE request signals by caller IP for quick debugging
  try {
    const dbgKey = `debug:last_sse:${clientIP}`;
    const dbgPayload = {
      event: 'sse_request',
      has_bearer: hasBearer,
      has_cookie: hasCookie,
      project: projectId,
      timestamp: new Date().toISOString(),
    } as any;
    await env.KV_PROJECTS.put(dbgKey, JSON.stringify(dbgPayload), { expirationTtl: 600 });
  } catch {}

  // Removed strict Accept header requirement to improve client compatibility.

  // Authentication: Prefer Bearer token over cookie session
  let identity: { userId: string; agentName: string } | null = null;

  // Try Bearer token first (for CLI clients)
  const bearerToken = extractBearerToken(request);
  if (bearerToken) {
    const tokenIdentity = await resolveTokenIdentity(bearerToken, env, clientIP);
    if (tokenIdentity) {
      identity = { userId: tokenIdentity.userId, agentName: tokenIdentity.agentName };
    } else {
      return new Response('Unauthorized - Invalid or expired token', {
        status: 401,
        headers: corsHeaders
      });
    }
  }

  // Fall back to cookie session (for Desktop clients)
  if (!identity) {
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
        reason: 'no_auth',
        ip: clientIP,
        timestamp: new Date().toISOString(),
      }));
      return new Response('Unauthorized - No session cookie or Bearer token', {
        status: 401,
        headers: corsHeaders
      });
    }

    // Resolve identity from session (with dev mode support)
    identity = await resolveIdentity(sessionToken, env);
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
  // Update debug doc with validation results
  try {
    const dbgKey = `debug:last_sse:${clientIP}`;
    const existing = await env.KV_PROJECTS.get(dbgKey);
    const base = existing ? JSON.parse(existing) : {};
    base.validated = true;
    base.user = identity.userId;
    base.project = selectedProject;
    base.timestamp = new Date().toISOString();
    await env.KV_PROJECTS.put(dbgKey, JSON.stringify(base), { expirationTtl: 600 });
  } catch {}

  // Delegate to Durable Object for session management
  const sessionId = crypto.randomUUID();
  console.log(JSON.stringify({ event: 'creating_do_stub', sessionId: sessionId.substring(0, 16), user: identity.userId }));

  const durableObjectId = env.SESSION_MANAGER.idFromName(sessionId);
  const stub = env.SESSION_MANAGER.get(durableObjectId);

  // Forward request to Durable Object with identity headers
  const doRequest = new Request(`${url.origin}/do/sse?sessionId=${sessionId}`, {
    method: 'GET',
    headers: {
      'Accept': 'text/event-stream',
      'X-User-Id': identity.userId,
      'X-Agent-Name': identity.agentName,
      'X-Project-Id': selectedProject,
      'X-Internal-Auth': env.INTERNAL_AUTH_SECRET,
    },
  });

  console.log(JSON.stringify({ event: 'forwarding_to_do', sessionId: sessionId.substring(0, 16), url: doRequest.url }));

  try {
    const response = await stub.fetch(doRequest);
    console.log(JSON.stringify({ event: 'do_response_received', sessionId: sessionId.substring(0, 16), status: response.status }));
    return response;
  } catch (error) {
    console.log(JSON.stringify({ event: 'do_fetch_error', sessionId: sessionId.substring(0, 16), error: String(error) }));
    return new Response(`Durable Object error: ${error}`, { status: 500, headers: corsHeaders });
  }
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
      agentName: env.AGENT_TYPE, // Use AI agent type instead of GitHub username
    };
  } catch (error) {
    console.error('Error resolving identity:', error);
    return null;
  }
}

/**
 * Validate and resolve identity from Bearer token
 */
async function resolveTokenIdentity(
  token: string,
  env: Env,
  clientIP: string
): Promise<{ userId: string; agentName: string; tokenId: string } | null> {
  try {
    const tokenData = await env.KV_PROJECTS.get(`token:${token}`);
    if (!tokenData) {
      console.log(JSON.stringify({
        event: 'token_auth_failure',
        reason: 'token_not_found',
        token_id: token.substring(0, 16),
        ip: clientIP,
        timestamp: new Date().toISOString(),
      }));
      return null;
    }

    const parsed: TokenData = JSON.parse(tokenData);

    // Check expiration
    if (Date.now() > parsed.expiresAt) {
      console.log(JSON.stringify({
        event: 'token_auth_failure',
        reason: 'token_expired',
        token_id: token.substring(0, 16),
        user: parsed.userId,
        ip: clientIP,
        timestamp: new Date().toISOString(),
      }));
      return null;
    }

    console.log(JSON.stringify({
      event: 'token_auth_success',
      user: parsed.userId,
      token_id: token.substring(0, 16),
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));

    return {
      userId: parsed.userId,
      agentName: env.AGENT_TYPE, // Use AI agent type instead of GitHub username
      tokenId: token,
    };
  } catch (error) {
    console.log(JSON.stringify({
      event: 'token_auth_failure',
      reason: 'parse_error',
      error: String(error),
      ip: clientIP,
      timestamp: new Date().toISOString(),
    }));
    return null;
  }
}

/**
 * Extract session token from cookie
 */
function extractSessionToken(request: Request): string | null {
  const cookieHeader = request.headers.get('Cookie');
  if (cookieHeader) {
    const cookies = cookieHeader.split(';').map((c) => c.trim());
    for (const cookie of cookies) {
      if (cookie.startsWith('session=')) {
        return cookie.substring('session='.length);
      }
    }
  }
  return null;
}

/**
 * Extract Bearer token from Authorization header
 */
function extractBearerToken(request: Request): string | null {
  const authHeader = request.headers.get('Authorization');
  if (authHeader?.startsWith('Bearer ')) {
    return authHeader.substring('Bearer '.length);
  }
  return null;
}

/**
 * Normalize arbitrary backend tool responses to MCP-compatible tool result shape.
 * Ensures `content` is always an array of typed items.
 */
function normalizeMcpResult(result: any): any {
  try {
    if (result && typeof result === 'object' && 'content' in result) {
      const c = (result as any).content;
      if (Array.isArray(c)) return result;
      if (typeof c === 'string') return { ...result, content: [{ type: 'text', text: c }] };
      if (c == null) return { ...result, content: [] };
      // Unknown content shape: stringify
      return { ...result, content: [{ type: 'text', text: JSON.stringify(c) }] };
    }
    // No `content` field
    if (typeof result === 'string') return { content: [{ type: 'text', text: result }] };
    return { content: [{ type: 'text', text: JSON.stringify(result) }] };
  } catch (_e) {
    // Defensive fallback
    const text = typeof result === 'string' ? result : JSON.stringify(result);
    return { content: [{ type: 'text', text }] };
  }
}

/**
 * OAuth/OIDC support for mcp-remote http-first
 */
function originFromRequest(request: Request): string {
  try {
    const u = new URL(request.url);
    return `${u.protocol}//${u.host}`;
  } catch {
    return '';
  }
}

async function handleWellKnownResource(request: Request, env: Env, corsHeaders: Record<string, string>): Promise<Response> {
  const origin = originFromRequest(request);
  const body = {
    resource: origin,
    authorization_servers: [origin],
  };
  return new Response(JSON.stringify(body), { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
}

function buildOAuthMetadata(request: Request) {
  const origin = originFromRequest(request);
  return {
    issuer: origin,
    authorization_endpoint: `${origin}/authorize`,
    token_endpoint: `${origin}/token`,
    registration_endpoint: `${origin}/register`,
    response_types_supported: ['code'],
    grant_types_supported: ['authorization_code', 'refresh_token'],
    code_challenge_methods_supported: ['S256'],
    token_endpoint_auth_methods_supported: ['none'],
  };
}

async function handleWellKnownOAuthAS(request: Request, env: Env, corsHeaders: Record<string, string>): Promise<Response> {
  const body = buildOAuthMetadata(request);
  return new Response(JSON.stringify(body), { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
}

async function handleWellKnownOIDC(request: Request, env: Env, corsHeaders: Record<string, string>): Promise<Response> {
  // Provide a minimal OIDC-compatible configuration mirroring OAuth metadata
  const meta = buildOAuthMetadata(request);
  const body = {
    issuer: meta.issuer,
    authorization_endpoint: meta.authorization_endpoint,
    token_endpoint: meta.token_endpoint,
    registration_endpoint: meta.registration_endpoint,
    response_types_supported: meta.response_types_supported,
    grant_types_supported: meta.grant_types_supported,
    code_challenge_methods_supported: meta.code_challenge_methods_supported,
  };
  return new Response(JSON.stringify(body), { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
}

function b64url(bytes: ArrayBuffer): string {
  let str = '';
  const arr = new Uint8Array(bytes);
  for (let i = 0; i < arr.length; i++) str += String.fromCharCode(arr[i]);
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

async function sha256(input: string): Promise<string> {
  const enc = new TextEncoder();
  const data = enc.encode(input);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return b64url(digest);
}

interface OAuthClientInfo { client_id: string; client_id_issued_at: number; token_endpoint_auth_method?: string }

async function handleOAuthRegister(request: Request, env: Env, corsHeaders: Record<string, string>): Promise<Response> {
  // Parse incoming client metadata and echo required fields in response
  let metadata: any = {};
  try {
    metadata = await request.json();
  } catch {
    metadata = {};
  }
  const redirect_uris = Array.isArray(metadata.redirect_uris) ? metadata.redirect_uris : [];
  if (redirect_uris.length === 0) {
    // Return OAuth error JSON that the client can parse
    const err = { error: 'invalid_client_metadata', error_description: 'redirect_uris is required' };
    return new Response(JSON.stringify(err), { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
  }

  const client_id = crypto.randomUUID();
  const issued_at = Math.floor(Date.now() / 1000);
  const info = {
    client_id,
    client_id_issued_at: issued_at,
    token_endpoint_auth_method: 'none',
    redirect_uris,
    grant_types: Array.isArray(metadata.grant_types) ? metadata.grant_types : ['authorization_code', 'refresh_token'],
    response_types: Array.isArray(metadata.response_types) ? metadata.response_types : ['code'],
    application_type: metadata.application_type || 'native',
    client_name: metadata.client_name || 'mcp-remote',
    // Optional echoes to satisfy strict parsers
    scope: typeof metadata.scope === 'string' ? metadata.scope : undefined,
    client_secret_expires_at: 0,
  };
  // Optionally persist client metadata
  // await env.KV_PROJECTS.put(`oauth:client:${client_id}`, JSON.stringify(info));
  return new Response(JSON.stringify(info), { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
}

async function handleOAuthAuthorize(request: Request, env: Env, corsHeaders: Record<string, string>): Promise<Response> {
  const url = new URL(request.url);
  const redirect_uri = url.searchParams.get('redirect_uri');
  const state = url.searchParams.get('state') || '';
  const code_challenge = url.searchParams.get('code_challenge');
  const code_challenge_method = url.searchParams.get('code_challenge_method') || 'S256';

  if (!redirect_uri || !code_challenge || code_challenge_method !== 'S256') {
    return new Response(JSON.stringify({ error: 'invalid_request' }), { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
  }

  // Resolve identity: prefer Bearer; else cookie session; else require GitHub OAuth
  const clientIP = request.headers.get('CF-Connecting-IP') || 'unknown';
  const bearer = extractBearerToken(request);
  let userId: string | null = null;
  if (bearer) {
    const id = await resolveTokenIdentity(bearer, env, clientIP);
    if (id) userId = id.userId;
  }
  if (!userId) {
    const sessionToken = extractSessionToken(request);
    if (sessionToken) {
      const sess = await resolveIdentity(sessionToken, env);
      if (sess) userId = sess.userId;
    }
  }
  if (!userId) {
    // If not authenticated, kick off GitHub OAuth
    return handleAuthLogin(request, env, corsHeaders);
  }

  // Issue authorization code and store PKCE data
  const code = crypto.randomUUID();
  const payload = { userId, code_challenge, redirect_uri, expiresAt: Date.now() + 10 * 60 * 1000 };
  await env.KV_PROJECTS.put(`oauth:code:${code}`, JSON.stringify(payload), { expirationTtl: 600 });
  const redirect = new URL(redirect_uri);
  redirect.searchParams.set('code', code);
  if (state) redirect.searchParams.set('state', state);
  return new Response(null, { status: 302, headers: { ...corsHeaders, Location: redirect.toString() } });
}

async function handleOAuthToken(request: Request, env: Env, corsHeaders: Record<string, string>): Promise<Response> {
  const contentType = request.headers.get('Content-Type') || '';
  let params: URLSearchParams;
  if (contentType.includes('application/x-www-form-urlencoded')) {
    const bodyText = await request.text();
    params = new URLSearchParams(bodyText);
  } else {
    // Try JSON for robustness
    try {
      const data = await request.json();
      params = new URLSearchParams();
      for (const [k, v] of Object.entries(data)) params.set(k, String(v));
    } catch {
      return new Response(JSON.stringify({ error: 'invalid_request' }), { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
    }
  }

  const grant_type = params.get('grant_type') || '';
  if (grant_type === 'authorization_code') {
    const code = params.get('code') || '';
    const code_verifier = params.get('code_verifier') || '';
    const redirect_uri = params.get('redirect_uri') || '';
    const rec = await env.KV_PROJECTS.get(`oauth:code:${code}`);
    if (!rec) return new Response(JSON.stringify({ error: 'invalid_grant' }), { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
    const payload = JSON.parse(rec) as { userId: string; code_challenge: string; redirect_uri: string; expiresAt: number };
    if (Date.now() > payload.expiresAt) return new Response(JSON.stringify({ error: 'invalid_grant' }), { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
    if (redirect_uri && payload.redirect_uri && redirect_uri !== payload.redirect_uri) return new Response(JSON.stringify({ error: 'invalid_request' }), { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
    const expected = await sha256(code_verifier);
    if (expected !== payload.code_challenge) return new Response(JSON.stringify({ error: 'invalid_grant' }), { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });

    // Issue access + refresh tokens; store access token in same namespace as CLI tokens so data-plane accepts it
    const access = crypto.randomUUID();
    const refresh = crypto.randomUUID();
    const now = Date.now();
    const ttl = 3600; // 1h access token
    const accessData: TokenData = { userId: payload.userId, createdAt: now, expiresAt: now + ttl * 1000 };
    await env.KV_PROJECTS.put(`token:${access}`, JSON.stringify(accessData), { expirationTtl: ttl });
    await env.KV_PROJECTS.put(`oauth:refresh:${refresh}`, JSON.stringify({ userId: payload.userId }), { expirationTtl: 30 * 24 * 3600 });
    // Invalidate code
    await env.KV_PROJECTS.delete(`oauth:code:${code}`);
    const body = { access_token: access, token_type: 'Bearer', expires_in: ttl, refresh_token: refresh };
    return new Response(JSON.stringify(body), { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
  }
  if (grant_type === 'refresh_token') {
    const refresh = params.get('refresh_token') || '';
    const rec = await env.KV_PROJECTS.get(`oauth:refresh:${refresh}`);
    if (!rec) return new Response(JSON.stringify({ error: 'invalid_grant' }), { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
    const data = JSON.parse(rec) as { userId: string };
    const access = crypto.randomUUID();
    const now = Date.now();
    const ttl = 3600;
    const accessData: TokenData = { userId: data.userId, createdAt: now, expiresAt: now + ttl * 1000 };
    await env.KV_PROJECTS.put(`token:${access}`, JSON.stringify(accessData), { expirationTtl: ttl });
    const body = { access_token: access, token_type: 'Bearer', expires_in: ttl, refresh_token: refresh };
    return new Response(JSON.stringify(body), { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
  }
  return new Response(JSON.stringify({ error: 'unsupported_grant_type' }), { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
}
