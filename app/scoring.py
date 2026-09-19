"""Deterministic, explainable candidate scoring rubric.

No model call, no randomness, no I/O: score_candidate() is a pure function of its
two arguments, so the same input always produces the same output (contract
requirement). See SPEC.md for the full interface contract.
"""

MUST_HAVE_MAX = 60.0
NICE_TO_HAVE_MAX = 20.0
EXPERIENCE_MAX = 20.0


def _skill_matches(required_skill: str, candidate_skills: list) -> bool:
    """Case-insensitive substring match: required_skill vs. each candidate skill."""
    req = str(required_skill).strip().lower()
    if not req:
        return False
    for raw in candidate_skills:
        cand = str(raw).strip().lower()
        if not cand:
            continue
        if req in cand or cand in req:
            return True
    return False


def _score_skill_bucket(required_skills: list, candidate_skills: list, points_max: float):
    """Split points_max evenly across required_skills; return (score, matched, missing).

    An empty requirement list is vacuously satisfied (nothing to miss), so it
    scores full marks rather than dividing by zero.
    """
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
    # Scaled down linearly; naturally 0 when years == 0.
    return EXPERIENCE_MAX * (years / min_years), False


def _format_skill_list(skills: list) -> str:
    return ", ".join(skills) if skills else "none"


def _build_explanation(
    must: tuple,
    nice: tuple,
    exp_met: bool,
    years: int,
    min_years: int,
    exp_score: float,
    total: float,
) -> str:
    must_score, must_matched, must_missing = must
    nice_score, nice_matched, _nice_missing = nice

    must_sentence = (
        "Matched {matched_n}/{total_n} must-have skills "
        "(matched: {matched}; missing: {missing}) for {score:.1f}/{max:.0f} pts."
    ).format(
        matched_n=len(must_matched),
        total_n=len(must_matched) + len(must_missing),
        matched=_format_skill_list(must_matched),
        missing=_format_skill_list(must_missing),
        score=must_score,
        max=MUST_HAVE_MAX,
    )

    nice_sentence = (
        "Matched {matched_n}/{total_n} nice-to-have skills "
        "(matched: {matched}) for {score:.1f}/{max:.0f} pts."
    ).format(
        matched_n=len(nice_matched),
        total_n=len(nice_matched) + len(_nice_missing),
        matched=_format_skill_list(nice_matched),
        score=nice_score,
        max=NICE_TO_HAVE_MAX,
    )

    if exp_met:
        exp_sentence = (
            "Experience bar met ({years} yrs >= required {min_years} yrs) "
            "for {score:.1f}/{max:.0f} pts."
        ).format(years=years, min_years=min_years, score=exp_score, max=EXPERIENCE_MAX)
    else:
        exp_sentence = (
            "Experience bar NOT met ({years} yrs < required {min_years} yrs) "
            "for {score:.1f}/{max:.0f} pts."
        ).format(years=years, min_years=min_years, score=exp_score, max=EXPERIENCE_MAX)

    return "{} {} {} Total score: {:.1f}/100.".format(
        must_sentence, nice_sentence, exp_sentence, total
    )


def score_candidate(redacted_fields: dict, job: dict) -> dict:
    """Score one redacted candidate against one job, deterministically.

    Returns {"score": float 0-100, "matched_must_haves": [...],
    "missing_must_haves": [...], "matched_nice_to_haves": [...], "explanation": str}.

    Rubric:
      - 60 pts max, split evenly across job["must_have_skills"] (case-insensitive
        substring/skill-list match against redacted_fields["skills"]).
      - 20 pts max, split evenly across job["nice_to_have_skills"].
      - 20 pts for years_experience >= min_years_experience, scaled down linearly
        if under (0 if years_experience == 0).
    Score is rounded to 1 decimal. explanation names exactly which must-haves
    matched/were missing and whether the experience bar was met; every number in
    the score is traceable in the sentence.
    """
    candidate_skills = redacted_fields.get("skills") or []
    must_have_skills = job.get("must_have_skills") or []
    nice_to_have_skills = job.get("nice_to_have_skills") or []
    years_experience = redacted_fields.get("years_experience", 0)
    min_years_experience = job.get("min_years_experience", 0)

    must_score, must_matched, must_missing = _score_skill_bucket(
        must_have_skills, candidate_skills, MUST_HAVE_MAX
    )
    nice_score, nice_matched, nice_missing = _score_skill_bucket(
        nice_to_have_skills, candidate_skills, NICE_TO_HAVE_MAX
    )
    exp_score, exp_met = _score_experience(years_experience, min_years_experience)

    total = round(must_score + nice_score + exp_score, 1)

    explanation = _build_explanation(
        (must_score, must_matched, must_missing),
        (nice_score, nice_matched, nice_missing),
        exp_met,
        max(0, years_experience or 0),
        max(0, min_years_experience or 0),
        exp_score,
        total,
    )

    return {
        "score": total,
        "matched_must_haves": must_matched,
        "missing_must_haves": must_missing,
        "matched_nice_to_haves": nice_matched,
        "explanation": explanation,
    }
