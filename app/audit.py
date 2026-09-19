"""Append-only audit log + bias-check aggregate (stdlib only).

Contract note (resolves the ts-placement ambiguity for every other file reading
the same SPEC.md contract): log_event(event_type, payload, ts) takes ts as an
explicit ISO-8601 string the caller already computed; this module never calls
datetime.now()/time.time() itself.
"""

import json
import os

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
# Module-level so tests can monkeypatch it to a tempfile path.
AUDIT_LOG_PATH = os.path.join(_APP_DIR, "data", "audit_log.jsonl")

# k-anonymity floor for bias_check(): a group smaller than this would have its
# avg_score equal (or nearly equal) to a specific member's exact score, which
# re-identifies that person's protected attribute. Such groups are combined
# into one suppressed bucket instead of being reported individually.
MIN_GROUP_SIZE = 3
SUPPRESSED_LABEL = "suppressed (group smaller than 3)"


def log_event(event_type: str, payload: dict, ts: str) -> dict:
    """Appends {"ts": ts, "event": event_type, **payload} as one JSON line to
    AUDIT_LOG_PATH (creating the file/dir if absent) and returns the written
    record. ts is an ISO-8601 string supplied by the caller."""
    record = {"ts": ts, "event": event_type, **payload}
    os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record


def read_audit_log() -> list[dict]:
    """Returns all records from AUDIT_LOG_PATH, oldest first; [] if the file is
    absent. A single malformed line (partial write, manual edit) is skipped
    rather than raising — the log's whole value is that it stays readable, so
    one bad line must not blank out every other entry."""
    if not os.path.exists(AUDIT_LOG_PATH):
        return []
    records = []
    with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def bias_check(candidates_with_scores: list[dict], unredacted_by_id: dict) -> dict:
    """candidates_with_scores: [{"id":..., "score":...}, ...]. unredacted_by_id
    maps id -> original (server-side-only) candidate dict, used solely to read
    the protected "gender" attribute for grouping — never to re-identify or
    re-rank an individual candidate.

    Groups smaller than MIN_GROUP_SIZE are combined into one SUPPRESSED_LABEL
    bucket with avg_score withheld (None): a size-1 (or 2) group's avg_score
    would equal (or nearly equal) a specific candidate's exact score, which
    would re-identify that candidate's gender from the public candidate list —
    the exact leak this function exists to prevent, not create.

    Returns {"groups": {group: {"n": int, "avg_score": float | None}, ...},
    "max_spread": float, "statement": str}. max_spread and the statement's
    group comparison only ever consider unsuppressed groups.
    """
    scores_by_group: dict[str, list[float]] = {}
    for entry in candidates_with_scores:
        candidate = unredacted_by_id.get(entry["id"])
        if candidate is None:
            continue
        group = candidate.get("gender", "undisclosed")
        scores_by_group.setdefault(group, []).append(entry["score"])

    groups: dict[str, dict] = {}
    suppressed_n = 0
    for group, scores in scores_by_group.items():
        if not scores:
            continue
        if len(scores) < MIN_GROUP_SIZE:
            suppressed_n += len(scores)
            continue
        groups[group] = {"n": len(scores), "avg_score": round(sum(scores) / len(scores), 1)}

    if suppressed_n:
        groups[SUPPRESSED_LABEL] = {"n": suppressed_n, "avg_score": None}

    reportable = {name: g for name, g in groups.items() if name != SUPPRESSED_LABEL}
    averages = [g["avg_score"] for g in reportable.values()]
    max_spread = round(max(averages) - min(averages), 1) if len(averages) >= 2 else 0.0

    if len(reportable) < 2:
        statement = (
            f"Not enough groups of at least {MIN_GROUP_SIZE} scored candidates "
            "to compare across protected attributes."
        )
    else:
        parts = ", ".join(
            f"{name}: avg {stats['avg_score']} (n={stats['n']})"
            for name, stats in sorted(reportable.items())
        )
        statement = f"Max spread across groups is {max_spread} points ({parts})."

    if suppressed_n:
        statement += (
            f" {suppressed_n} candidate(s) in group(s) smaller than {MIN_GROUP_SIZE} "
            "were combined and their average withheld to avoid re-identifying them."
        )

    return {"groups": groups, "max_spread": max_spread, "statement": statement}
