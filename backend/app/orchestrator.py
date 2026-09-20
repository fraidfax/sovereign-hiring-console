"""The agent loop: sequences real tool calls + brain narration per candidate,
emitting SSE-shaped events as it goes.

Runs as a background asyncio task (started by POST /api/run-agent). Never
blocks the event loop on the blocking `claude` CLI subprocess call — that runs
via asyncio.to_thread, bounded to 3 concurrent candidates at a time.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app import brain, store, tools

CONCURRENT_BRAIN_CALLS = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(event_type: str, candidate_id: str | None, tool: str | None, detail: dict) -> dict:
    """Appends to the replay log and fans the event out to every currently
    open SSE connection (see store.SUBSCRIBERS for why one queue isn't
    enough)."""
    event = {"type": event_type, "candidate_id": candidate_id, "tool": tool, "detail": detail, "ts": _now_iso()}
    store.EVENTS.append(event)
    for queue in store.SUBSCRIBERS:
        queue.put_nowait(event)
    return event


async def _redact_and_score(candidate_id: str) -> dict:
    """Runs the two always-real, always-synchronous tools for one candidate
    and writes their results into the public record. Returns the score
    result dict (needed later for bias_check and the brain prompt)."""
    raw = store.CANDIDATES_RAW[candidate_id]
    public = store.PUBLIC[candidate_id]
    public["status"] = "processing"

    _emit("tool_call", candidate_id, "redact_pii", {})
    redaction = tools.redact_pii(raw)
    public["redacted_profile"] = redaction["redacted"]
    public["removed_fields"] = redaction["removed_fields"]
    public["scrubbed_spans"] = redaction["scrubbed_spans"]
    _emit("tool_result", candidate_id, "redact_pii", redaction)

    _emit("tool_call", candidate_id, "score_candidate", {})
    score_result = tools.score_candidate(redaction["redacted"], store.JOB)
    public["score"] = score_result["score"]
    public["explanation"] = score_result["explanation"]
    public["matched_must_haves"] = score_result["matched_must_haves"]
    public["missing_must_haves"] = score_result["missing_must_haves"]
    public["matched_nice_to_haves"] = score_result["matched_nice_to_haves"]
    _emit("tool_result", candidate_id, "score_candidate", score_result)

    return score_result


async def _reason_about_candidate(candidate_id: str, redacted_profile: dict, score_result: dict,
                                   bias_statement: str, semaphore: asyncio.Semaphore) -> None:
    """Calls the brain (bounded concurrency), narrates, flags for approval,
    and audit-logs — the per-candidate tail of the pipeline."""
    async with semaphore:
        reasoning = await asyncio.to_thread(
            brain.get_agent_reasoning, redacted_profile, store.JOB, score_result, bias_statement,
        )

    for note_key in ("redaction_note", "score_note", "bias_note"):
        _emit("narration", candidate_id, "brain", {note_key: reasoning[note_key]})

    tools.flag_for_approval(candidate_id, reasoning["recommendation"], reasoning["recommendation_reasoning"])

    _emit("recommendation", candidate_id, None, {
        "recommendation": reasoning["recommendation"],
        "recommendation_reasoning": reasoning["recommendation_reasoning"],
    })

    tools.log_to_audit("ai_recommendation", {
        "candidate_id": candidate_id,
        "score": score_result["score"],
        "recommendation": reasoning["recommendation"],
        "recommendation_reasoning": reasoning["recommendation_reasoning"],
    }, _now_iso())

    _emit("done", candidate_id, None, {"status": store.PUBLIC[candidate_id]["status"]})


async def run_agent() -> None:
    """Full pipeline for every candidate not yet processed, in order:
    redact -> score (per candidate) -> bias_check (once, whole cohort) ->
    brain reasoning + flag_for_approval + audit log (per candidate,
    concurrency-bounded)."""
    store.AGENT_RUNNING = True
    try:
        candidate_ids = [cid for cid in store.ORIGINAL_ORDER if store.PUBLIC[cid]["status"] == "not_started"]

        score_results: dict[str, dict] = {}
        for candidate_id in candidate_ids:
            score_results[candidate_id] = await _redact_and_score(candidate_id)

        _emit("tool_call", None, "bias_check", {})
        scored_list = [{"id": cid, "score": score_results[cid]["score"]} for cid in candidate_ids]
        bias_result = tools.bias_check(scored_list, store.CANDIDATES_RAW)
        _emit("tool_result", None, "bias_check", bias_result)
        for candidate_id in candidate_ids:
            store.PUBLIC[candidate_id]["bias_note"] = bias_result["statement"]

        semaphore = asyncio.Semaphore(CONCURRENT_BRAIN_CALLS)
        await asyncio.gather(*(
            _reason_about_candidate(
                candidate_id,
                store.PUBLIC[candidate_id]["redacted_profile"],
                score_results[candidate_id],
                bias_result["statement"],
                semaphore,
            )
            for candidate_id in candidate_ids
        ))

        _emit("done", None, None, {"status": "all_complete"})
    finally:
        store.AGENT_RUNNING = False
