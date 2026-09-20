import type {
  AgentEvent,
  AuditLogEntry,
  Candidate,
  DataResidency,
  DecideRequest,
  Job,
} from "./types";

export const API_BASE = "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch (err) {
    throw new ApiError(
      `Could not reach the backend at ${API_BASE}. Is it running? (${
        err instanceof Error ? err.message : String(err)
      })`,
      0,
    );
  }
  if (!res.ok) {
    let message = `Request failed with status ${res.status}`;
    try {
      const body = (await res.json()) as { error?: string };
      if (body?.error) message = body.error;
    } catch {
      // response body wasn't JSON; keep the generic message
    }
    throw new ApiError(message, res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function fetchJob(): Promise<Job> {
  return apiFetch<Job>("/api/job");
}

export function fetchCandidates(): Promise<Candidate[]> {
  return apiFetch<Candidate[]>("/api/candidates");
}

export function runAgent(): Promise<void> {
  return apiFetch<void>("/api/run-agent", { method: "POST" });
}

export function decide(body: DecideRequest): Promise<void> {
  return apiFetch<void>("/api/decide", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function fetchAuditLog(): Promise<AuditLogEntry[]> {
  return apiFetch<AuditLogEntry[]>("/api/audit-log");
}

export function fetchDataResidency(): Promise<DataResidency> {
  return apiFetch<DataResidency>("/api/data-residency");
}

/**
 * Opens the agent-stream SSE connection. The stream replays everything
 * emitted so far on (re)connect, so callers should treat each `onEvent`
 * call as "here is the full history so far isn't guaranteed" — dedupe by
 * key is handled by the caller (ReasoningFeed), not here.
 */
export function subscribeAgentStream(
  onEvent: (event: AgentEvent) => void,
  onError: (message: string) => void,
): EventSource {
  const source = new EventSource(`${API_BASE}/api/agent-stream`);
  source.onmessage = (msg) => {
    try {
      const parsed = JSON.parse(msg.data) as AgentEvent;
      onEvent(parsed);
    } catch {
      onError("Received an unreadable event from the agent stream.");
    }
  };
  source.onerror = () => {
    onError(
      "Lost connection to the agent stream. It will keep retrying automatically.",
    );
  };
  return source;
}
