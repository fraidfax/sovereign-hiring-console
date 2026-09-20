"""Five real, deterministic, pure-Python tools for the Sovereign Hiring Agent.

Ported from the prior validated build (v1's app/redaction.py, app/scoring.py,
app/audit.py) — same logic, same previously-fixed bugs, now exposed as the
tool functions the orchestrator calls. No imports beyond stdlib.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional, Pattern

# ---------------------------------------------------------------------------
# redact_pii
# ---------------------------------------------------------------------------

PII_FIELDS = (
    "full_name",
    "email",
    "phone",
    "address",
    "date_of_birth",
    "gender",
    "nationality",
    "photo_placeholder",
)

FREE_TEXT_FIELDS = ("work_history", "cover_letter_excerpt", "education")

REDACTION_REPLACEMENT = "[REDACTED]"

_PRONOUNS = ("he", "him", "his", "she", "her", "they", "them", "their")
_PRONOUN_RE = re.compile(r"\b(?:" + "|".join(_PRONOUNS) + r")\b", re.IGNORECASE)

# Standalone age mentions: "32 years old", "29-year-old", "aged 29", "I'm 34",
# "I am 34" — including the curly apostrophe (’) most phones auto-substitute.
_AGE_RE = re.compile(
    r"\b\d{1,3}[\s-]+years?[\s-]+old\b"
    r"|\baged\s+\d{1,3}\b"
    r"|\bI\s*(?:['’]m|\s+am)\s+\d{1,3}\b",
    re.IGNORECASE,
)


def _name_pattern(full_name: Any) -> Optional[Pattern]:
    """Whole-word pattern matching any token of full_name, including each
    hyphen sub-part (e.g. "Al-Sayed" also matches bare "Al" or "Sayed")."""
    if not isinstance(full_name, str):
        return None
    tokens = [p for p in re.split(r"\s+", full_name.strip()) if p]
    if not tokens:
        return None
    parts = set(tokens)
    for token in tokens:
        parts.update(p for p in token.split("-") if p)
    ordered = sorted(parts, key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(re.escape(p) for p in ordered) + r")\b", re.IGNORECASE)


def _scrub(pattern: Pattern, text: str, field: str, spans: list[dict]) -> str:
    def _replace(match: "re.Match") -> str:
        spans.append({"field": field, "original": match.group(0), "replacement": REDACTION_REPLACEMENT})
        return REDACTION_REPLACEMENT

    return pattern.sub(_replace, text)


def redact_pii(candidate: dict) -> dict:
    """Strip PII_FIELDS wholesale and scrub name/age/pronoun mentions from
    FREE_TEXT_FIELDS. Returns {"redacted", "removed_fields", "scrubbed_spans"}."""
    redacted: dict[str, Any] = {k: v for k, v in candidate.items() if k not in PII_FIELDS}
    removed_fields = [f for f in PII_FIELDS if f in candidate]
    scrubbed_spans: list[dict] = []

    name_re = _name_pattern(candidate.get("full_name"))

    for field in FREE_TEXT_FIELDS:
        text = redacted.get(field)
        if not isinstance(text, str):
            continue
        if name_re is not None:
            text = _scrub(name_re, text, field, scrubbed_spans)
        text = _scrub(_AGE_RE, text, field, scrubbed_spans)
        text = _scrub(_PRONOUN_RE, text, field, scrubbed_spans)
        redacted[field] = text

    return {
        "redacted": redacted,
        "removed_fields": removed_fields,
        "scrubbed_spans": scrubbed_spans,
    }


# ---------------------------------------------------------------------------
# score_candidate
# ---------------------------------------------------------------------------

MUST_HAVE_MAX = 60.0
NICE_TO_HAVE_MAX = 20.0
EXPERIENCE_MAX = 20.0


def _skill_matches(required_skill: str, candidate_skills: list) -> bool:
    req = str(required_skill).strip().lower()
    if not req:
        return False
    for raw in candidate_skills:
        cand = str(raw).strip().lower()
        if cand and (req in cand or cand in req):
            return True
    return False


def _score_skill_bucket(required_skills: list, candidate_skills: list, points_max: float):
    if not required_skills:
        return points_max, [], []
    per_skill = points_max / len(required_skills)
    matched = [s for s in required_skills if _skill_matches(s, candidate_skills)]
    missing = [s for s in required_skills if s not in matched]
    return per_skill * len(matched), matched, missing


def _score_experience(years_experience: int, min_years_experience: int):
    years = max(0, years_experience or 0)
    min_years = max(0, min_years_experience or 0)
    if min_years == 0:
        return EXPERIENCE_MAX, True
    if years >= min_years:
        return EXPERIENCE_MAX, True
    return EXPERIENCE_MAX * (years / min_years), False


def _format_skill_list(skills: list) -> str:
    return ", ".join(skills) if skills else "none"


def _build_explanation(must: tuple, nice: tuple, exp_met: bool, years: int, min_years: int,
                        exp_score: float, total: float) -> str:
    must_score, must_matched, must_missing = must
    nice_score, nice_matched, nice_missing = nice

    must_sentence = (
        "Matched {matched_n}/{total_n} must-have skills (matched: {matched}; "
        "missing: {missing}) for {score:.1f}/{max:.0f} pts."
    ).format(
        matched_n=len(must_matched), total_n=len(must_matched) + len(must_missing),
        matched=_format_skill_list(must_matched), missing=_format_skill_list(must_missing),
        score=must_score, max=MUST_HAVE_MAX,
    )
    nice_sentence = (
        "Matched {matched_n}/{total_n} nice-to-have skills (matched: {matched}) "
        "for {score:.1f}/{max:.0f} pts."
    ).format(
        matched_n=len(nice_matched), total_n=len(nice_matched) + len(nice_missing),
        matched=_format_skill_list(nice_matched), score=nice_score, max=NICE_TO_HAVE_MAX,
    )
    if exp_met:
        exp_sentence = (
            "Experience bar met ({years} yrs >= required {min_years} yrs) for "
            "{score:.1f}/{max:.0f} pts."
        ).format(years=years, min_years=min_years, score=exp_score, max=EXPERIENCE_MAX)
    else:
        exp_sentence = (
            "Experience bar NOT met ({years} yrs < required {min_years} yrs) for "
            "{score:.1f}/{max:.0f} pts."
        ).format(years=years, min_years=min_years, score=exp_score, max=EXPERIENCE_MAX)

    return "{} {} {} Total score: {:.1f}/100.".format(must_sentence, nice_sentence, exp_sentence, total)


def score_candidate(redacted_fields: dict, job: dict) -> dict:
    """Deterministic 60/20/20 rubric. Pure arithmetic/string formatting only."""
    candidate_skills = redacted_fields.get("skills") or []
    must_have_skills = job.get("must_have_skills") or []
    nice_to_have_skills = job.get("nice_to_have_skills") or []
    years_experience = redacted_fields.get("years_experience", 0)
    min_years_experience = job.get("min_years_experience", 0)

    must_score, must_matched, must_missing = _score_skill_bucket(must_have_skills, candidate_skills, MUST_HAVE_MAX)
    nice_score, nice_matched, nice_missing = _score_skill_bucket(nice_to_have_skills, candidate_skills, NICE_TO_HAVE_MAX)
    exp_score, exp_met = _score_experience(years_experience, min_years_experience)

    total = round(must_score + nice_score + exp_score, 1)

    explanation = _build_explanation(
        (must_score, must_matched, must_missing),
        (nice_score, nice_matched, nice_missing),
        exp_met, max(0, years_experience or 0), max(0, min_years_experience or 0),
        exp_score, total,
    )

    return {
        "score": total,
        "matched_must_haves": must_matched,
        "missing_must_haves": must_missing,
        "matched_nice_to_haves": nice_matched,
        "explanation": explanation,
    }


# ---------------------------------------------------------------------------
# bias_check
# ---------------------------------------------------------------------------

MIN_GROUP_SIZE = 3
SUPPRESSED_LABEL = "suppressed (group smaller than 3)"


def bias_check(scored_candidates: list[dict], unredacted_by_id: dict) -> dict:
    """Groups by the raw server-side-only gender field. Any group smaller than
    MIN_GROUP_SIZE is folded into one suppressed bucket with avg_score=None —
    never computed then hidden, genuinely withheld, since a group of 1-2 has
    an avg_score that equals a specific person's real score and would
    re-identify their gender."""
    scores_by_group: dict[str, list[float]] = {}
    for entry in scored_candidates:
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


# ---------------------------------------------------------------------------
# flag_for_approval — the only function that can move a candidate out of
# "processing"; it always lands on pending_review, never approved/rejected.
# ---------------------------------------------------------------------------

def flag_for_approval(candidate_id: str, recommendation: str, reasoning: str) -> dict:
    """Sets that candidate's in-memory status="pending_review",
    recommendation, recommendation_reasoning=reasoning. Mutates the shared
    in-memory store (app.store.PUBLIC) — the single source of truth the API
    routes read from — and returns the updated record. This is the only
    function that can move a candidate out of "processing"; it always lands
    on pending_review, never approved/rejected directly."""
    from app import store  # deferred: avoids a hard import cycle at module load

    record = store.PUBLIC[candidate_id]
    record["status"] = "pending_review"
    record["recommendation"] = recommendation
    record["recommendation_reasoning"] = reasoning
    return record


# ---------------------------------------------------------------------------
# log_to_audit / read_audit_log
# ---------------------------------------------------------------------------

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIT_LOG_PATH = os.path.join(_APP_DIR, "data", "audit_log.jsonl")


def log_to_audit(event_type: str, payload: dict, ts: str) -> dict:
    """Appends {"ts": ts, "event": event_type, **payload} as one JSON line.
    ts is always caller-supplied — never call datetime.now() in here, keeps
    this testable/deterministic."""
    record = {"ts": ts, "event": event_type, **payload}
    os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record


def read_audit_log() -> list[dict]:
    """All records oldest-first; [] if absent. Skips (does not raise on) a
    malformed line so one bad write can't blank the whole log."""
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
