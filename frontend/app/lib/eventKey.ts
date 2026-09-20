import type { AgentEvent } from "./types";

/** Stable dedupe/react key for a replayed SSE event. */
export function eventKey(e: AgentEvent): string {
  return `${e.type}|${e.candidate_id ?? "-"}|${e.ts}`;
}
