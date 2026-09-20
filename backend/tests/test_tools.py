import json
import os

import pytest

from app import store, tools


def _candidate(**overrides):
    base = {
        "id": "cand-01",
        "full_name": "Jamie Rivera",
        "email": "jamie.rivera@example.com",
        "phone": "+1-555-0100",
        "address": "123 Example St, Springfield",
        "date_of_birth": "1994-03-12",
        "gender": "non_binary",
        "nationality": "Finnish",
        "photo_placeholder": "avatar-07",
        "years_experience": 5,
        "skills": ["Python", "PostgreSQL"],
        "education": "BSc Computer Science",
        "work_history": "Jamie Rivera led backend projects; she shipped three releases on time.",
        "cover_letter_excerpt": "I'm 34 and aged 29 mentally; they said Rivera was reliable.",
    }
    base.update(overrides)
    return base


JOB = {
    "must_have_skills": ["Python", "PostgreSQL"],
    "nice_to_have_skills": ["Kubernetes"],
    "min_years_experience": 4,
}


# --- redact_pii ------------------------------------------------------------

def test_pii_fields_fully_removed():
    result = tools.redact_pii(_candidate())
    redacted = result["redacted"]
    for field in tools.PII_FIELDS:
        assert field not in redacted
    assert redacted["id"] == "cand-01"
    assert redacted["years_experience"] == 5
    assert set(result["removed_fields"]) == set(tools.PII_FIELDS)


def test_name_age_and_pronoun_mentions_are_scrubbed_in_free_text():
    result = tools.redact_pii(_candidate())
    redacted = result["redacted"]
    for field in ("work_history", "cover_letter_excerpt"):
        assert "Jamie" not in redacted[field]
        assert "Rivera" not in redacted[field]
    assert "34" not in redacted["cover_letter_excerpt"]
    assert "aged 29" not in redacted["cover_letter_excerpt"]
    assert "she" not in redacted["work_history"].lower().split()
    originals = {s["original"] for s in result["scrubbed_spans"]}
    assert "Jamie" in originals or "Rivera" in originals


def test_curly_apostrophe_age_mention_is_scrubbed():
    candidate = _candidate(cover_letter_excerpt="I’m 34 and excited about this role.")
    result = tools.redact_pii(candidate)
    redacted = result["redacted"]
    assert "34" not in redacted["cover_letter_excerpt"]
    age_spans = [
        s for s in result["scrubbed_spans"]
        if s["field"] == "cover_letter_excerpt" and any(c.isdigit() for c in s["original"])
    ]
    assert age_spans


# --- score_candidate ---------------------------------------------------

def test_full_match_scores_near_100():
    redacted = {"skills": ["Python", "PostgreSQL", "Kubernetes"], "years_experience": 10}
    result = tools.score_candidate(redacted, JOB)
    assert result["score"] == pytest.approx(100.0)
    assert result["missing_must_haves"] == []


def test_zero_match_scores_zero():
    redacted = {"skills": [], "years_experience": 0}
    result = tools.score_candidate(redacted, JOB)
    assert result["score"] == 0.0
    assert result["matched_must_haves"] == []
    assert result["missing_must_haves"] == JOB["must_have_skills"]


def test_score_candidate_is_deterministic():
    redacted = {"skills": ["Python"], "years_experience": 2}
    first = tools.score_candidate(redacted, JOB)
    second = tools.score_candidate(dict(redacted), dict(JOB))
    assert first == second


def test_empty_requirement_lists_score_full_marks_no_zero_division():
    empty_job = {"must_have_skills": [], "nice_to_have_skills": [], "min_years_experience": 0}
    result = tools.score_candidate({"skills": [], "years_experience": 0}, empty_job)
    assert result["score"] == 100.0


# --- bias_check ----------------------------------------------------------

def test_bias_check_suppresses_singleton_groups_and_withholds_avg_score():
    """The single most important test: two singleton groups must never
    individually appear, and the suppressed bucket's avg_score must be None
    — genuinely withheld, not computed-then-hidden."""
    unredacted_by_id = {
        "c1": {"gender": "female"}, "c2": {"gender": "female"}, "c3": {"gender": "female"},
        "c4": {"gender": "male"}, "c5": {"gender": "male"}, "c6": {"gender": "male"},
        "c7": {"gender": "non_binary"},  # singleton
        "c8": {"gender": "undisclosed"},  # singleton
    }
    scored = [
        {"id": "c1", "score": 80.0}, {"id": "c2", "score": 82.0}, {"id": "c3", "score": 78.0},
        {"id": "c4", "score": 60.0}, {"id": "c5", "score": 62.0}, {"id": "c6", "score": 58.0},
        {"id": "c7", "score": 95.0},
        {"id": "c8", "score": 10.0},
    ]
    result = tools.bias_check(scored, unredacted_by_id)

    assert "non_binary" not in result["groups"]
    assert "undisclosed" not in result["groups"]
    assert tools.SUPPRESSED_LABEL in result["groups"]
    assert result["groups"][tools.SUPPRESSED_LABEL]["avg_score"] is None
    assert result["groups"][tools.SUPPRESSED_LABEL]["n"] == 2

    assert result["groups"]["female"]["avg_score"] == pytest.approx(80.0)
    assert result["groups"]["male"]["avg_score"] == pytest.approx(60.0)
    # max_spread only ever considers unsuppressed groups
    assert result["max_spread"] == pytest.approx(20.0)
    assert "95" not in result["statement"]
    assert "10" not in result["statement"] or "10" not in result["statement"].split("(")[0]


def test_bias_check_with_no_scored_candidates_for_a_group_is_skipped():
    result = tools.bias_check([], {})
    assert result["groups"] == {}
    assert result["max_spread"] == 0.0


# --- flag_for_approval -----------------------------------------------------

def test_flag_for_approval_sets_pending_review_never_final():
    store.load_seed_data()
    candidate_id = store.ORIGINAL_ORDER[0]
    updated = tools.flag_for_approval(candidate_id, "approve", "Strong skill match.")
    assert updated["status"] == "pending_review"
    assert updated["recommendation"] == "approve"
    assert updated["recommendation_reasoning"] == "Strong skill match."
    assert store.PUBLIC[candidate_id]["status"] == "pending_review"


# --- log_to_audit / read_audit_log -----------------------------------------

@pytest.fixture()
def temp_audit_log(tmp_path, monkeypatch):
    path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr(tools, "AUDIT_LOG_PATH", str(path))
    return path


def test_log_to_audit_appends_jsonl_with_caller_supplied_ts(temp_audit_log):
    record = tools.log_to_audit("ai_recommendation", {"candidate_id": "cand-01"}, "2026-01-01T00:00:00Z")
    assert record == {"ts": "2026-01-01T00:00:00Z", "event": "ai_recommendation", "candidate_id": "cand-01"}
    lines = temp_audit_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == record


def test_read_audit_log_skips_malformed_lines(temp_audit_log):
    tools.log_to_audit("human_decision", {"a": 1}, "2026-01-01T00:00:00Z")
    with open(temp_audit_log, "a", encoding="utf-8") as f:
        f.write("not valid json\n")
    tools.log_to_audit("human_decision", {"a": 2}, "2026-01-01T00:00:01Z")

    records = tools.read_audit_log()
    assert len(records) == 2
    assert records[0]["a"] == 1
    assert records[1]["a"] == 2


def test_read_audit_log_returns_empty_list_when_file_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "AUDIT_LOG_PATH", str(tmp_path / "missing.jsonl"))
    assert tools.read_audit_log() == []
