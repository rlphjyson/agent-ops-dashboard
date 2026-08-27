const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type RunStatus = "queued" | "running" | "completed" | "failed";

export interface Run {
  id: string;
  prompt: string;
  status: RunStatus;
  result_text: string | null;
  error_message: string | null;
  cost_usd: number | null;
  num_turns: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface SystemPayload {
  tools: string[];
}
export interface AssistantTextPayload {
  text: string;
}
export interface ToolUsePayload {
  tool_use_id: string;
  name: string;
  input: Record<string, unknown>;
}
export interface ToolResultPayload {
  tool_use_id: string | null;
  content: unknown;
  is_error: boolean;
}
export interface ResultPayload {
  is_error: boolean;
  result_text: string;
  cost_usd: number | null;
  num_turns: number | null;
}
export interface ErrorPayload {
  message: string;
}

interface RunEventBase {
  id: number;
  run_id: string;
  created_at: string;
}

// A discriminated union on `kind` -- matches the backend's NormalizedEvent contract
// (services/agent_engines/base.py) exactly, so a `switch`/`if` on `kind` narrows `payload`'s
// type in the UI code that renders each kind differently.
export type RunEvent =
  | (RunEventBase & { kind: "system"; payload: SystemPayload })
  | (RunEventBase & { kind: "assistant_text"; payload: AssistantTextPayload })
  | (RunEventBase & { kind: "tool_use"; payload: ToolUsePayload })
  | (RunEventBase & { kind: "tool_result"; payload: ToolResultPayload })
  | (RunEventBase & { kind: "result"; payload: ResultPayload })
  | (RunEventBase & { kind: "error"; payload: ErrorPayload });

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(body.detail ?? "Request failed", response.status);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function signup(email: string, password: string): Promise<{ access_token: string }> {
  return request("/auth/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export function login(email: string, password: string): Promise<{ access_token: string }> {
  return request("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export function createRun(token: string, prompt: string): Promise<Run> {
  return request(
    "/runs",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    },
    token,
  );
}

export function listRuns(token: string): Promise<Run[]> {
  return request("/runs", {}, token);
}

export function getRun(token: string, runId: string): Promise<Run> {
  return request(`/runs/${runId}`, {}, token);
}

export function getRunEvents(token: string, runId: string): Promise<RunEvent[]> {
  return request(`/runs/${runId}/events`, {}, token);
}

export function deleteRun(token: string, runId: string): Promise<void> {
  return request(`/runs/${runId}`, { method: "DELETE" }, token);
}

/** Builds the /ws/runs URL, translating the API base's http(s) scheme to ws(s) -- a browser's
 * native WebSocket API can't set an Authorization header, so the token travels as a query param
 * instead (see the backend's routers/ws.py for the matching decode). */
export function buildRunsWebSocketUrl(token: string, runId?: string): string {
  const wsBase = API_BASE_URL.replace(/^http/, "ws");
  const params = new URLSearchParams({ token });
  if (runId) params.set("run_id", runId);
  return `${wsBase}/ws/runs?${params.toString()}`;
}
