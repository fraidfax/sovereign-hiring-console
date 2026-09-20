// Types mirror the backend HTTP/SSE contract exactly (field names are load-bearing).

export interface Job {
  id: string;
  title: string;
  location: string;
  description: string;
  must_have_skills: string[];
  nice_to_have_skills: string[];
  min_years_experience: number;
}

export interface RedactedProfile {
  id: string;
  years_experience: number;
  skills: string[];
  education: string;
  work_history: string;
  cover_letter_excerpt: string;
}

export interface ScrubbedSpan {
  field: string;
  original: string;
  replacement: string;
}

export type CandidateStatus =
  | "not_started"
  | "processing"
  | "pending_review"
  | "approved"
  | "rejected";

export type Recommendation = "approve" | "reject";

export interface Candidate {
  id: string;
  redacted_profile: RedactedProfile;
  removed_fields: string[];
  scrubbed_spans: ScrubbedSpan[];
  score: number | null;
  explanation: string | null;
  matched_must_haves: string[];
  missing_must_haves: string[];
  matched_nice_to_haves: string[];
  bias_note: string | null;
  recommendation: Recommendation | null;
  recommendation_reasoning: string | null;
  status: CandidateStatus;
  decision_actor: string | null;
  decision_reason: string | null;
  is_override: boolean;
}

export type AgentEventType =
  | "tool_call"
  | "tool_result"
  | "narration"
  | "recommendation"
  | "done";

export interface AgentEvent {
  type: AgentEventType;
  candidate_id: string | null;
  tool: string | null;
  detail: unknown;
  ts: string;
}

export interface ExternalService {
  name: string;
  receives_pii: boolean;
  note: string;
}

export interface DataResidency {
  location: string;
  external_services: ExternalService[];
  pii_external_requests_total: number;
}

export type AuditEvent = "ai_recommendation" | "human_decision";

export interface AuditLogEntry {
  ts: string;
  event: AuditEvent;
  // Payload fields are not fixed by the contract beyond ts/event; treat
  // everything else as optional and render defensively.
  candidate_id?: string;
  actor?: string;
  decision?: Recommendation;
  recommendation?: Recommendation;
  reason?: string;
  reasoning?: string;
  is_override?: boolean;
  score?: number;
  [key: string]: unknown;
}

export interface DecideRequest {
  candidate_id: string;
  decision: Recommendation;
  actor: string;
  reason?: string;
}

export interface ApiErrorBody {
  error: string;
}
