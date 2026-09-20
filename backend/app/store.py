"""Single in-memory store shared by tools.py, orchestrator.py, and main.py.

No database per spec (in-memory + a JSONL audit file on disk). Kept as one
module-level dict of module-level dicts/lists rather than a class — there is
exactly one process, one cohort, one run; a class would just be ceremony
around the same two globals (ponytail: YAGNI).
"""

from __future__ import annotations

import json
import os

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

JOB: dict = {}
# Raw, unredacted candidate records — server-side only, keyed by id. Used by
# bias_check() to read the protected `gender` field and never exposed via API.
CANDIDATES_RAW: dict[str, dict] = {}
# Public API-facing record per candidate, keyed by id. This is what
# GET /api/candidates serves and what flag_for_approval()/`/api/decide` mutate.
PUBLIC: dict[str, dict] = {}
ORIGINAL_ORDER: list[str] = []

AGENT_RUNNING: bool = False
# Append-only log of every SSE event emitted so far, oldest first — replayed
# in full to any new/reconnecting client before it starts streaming new ones.
EVENTS: list[dict] = []
# One asyncio.Queue per currently-open SSE connection (ponytail: a single
# shared queue can't serve a reconnect-without-loss *and* a second open tab —
# whichever connection calls .get() first would steal the other's event — so
# each connection gets its own queue and every emitted event is fanned out to
# all of them; EVENTS above is what makes replay-on-reconnect possible).
SUBSCRIBERS: list = []


def _new_public_record(candidate_id: str) -> dict:
    return {
        "id": candidate_id,
        "redacted_profile": None,
        "removed_fields": None,
        "scrubbed_spans": None,
        "score": None,
        "explanation": None,
        "matched_must_haves": None,
        "missing_must_haves": None,
        "matched_nice_to_haves": None,
        "bias_note": None,
        "recommendation": None,
        "recommendation_reasoning": None,
        "status": "not_started",
        "decision_actor": None,
        "decision_reason": None,
        "is_override": None,
    }


def load_seed_data() -> None:
    """Loads job.json/candidates.json from disk and (re)initializes all
    in-memory state. Safe to call once at startup; a second call would reset
    an in-progress run, which is intentionally not exposed via any route."""
    global JOB, CANDIDATES_RAW, PUBLIC, ORIGINAL_ORDER, AGENT_RUNNING, EVENTS, SUBSCRIBERS

    with open(os.path.join(_DATA_DIR, "job.json"), encoding="utf-8") as f:
        JOB = json.load(f)
    with open(os.path.join(_DATA_DIR, "candidates.json"), encoding="utf-8") as f:
        candidates = json.load(f)

    CANDIDATES_RAW = {c["id"]: c for c in candidates}
    ORIGINAL_ORDER = [c["id"] for c in candidates]
    PUBLIC = {c["id"]: _new_public_record(c["id"]) for c in candidates}
    AGENT_RUNNING = False
    EVENTS = []
    SUBSCRIBERS = []


def sorted_public_candidates() -> list[dict]:
    """Sorted by score desc once scored; ties/unscored keep original order."""
    def sort_key(candidate_id: str):
        score = PUBLIC[candidate_id]["score"]
        # Unscored candidates (None) sort after scored ones, in original order.
        return (0, -score) if score is not None else (1, 0)

    ordered = sorted(ORIGINAL_ORDER, key=sort_key)
    return [PUBLIC[cid] for cid in ordered]
