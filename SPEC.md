# SPEC — Sovereign Hiring Console

A single deployable demo answering the HR/Talent scenario from `CHALLENGE.md`.

## Product

**Sovereign Hiring Console**: a recruiter-facing web app that ranks candidates for one
job opening using a fully local, deterministic, explainable scoring engine — after
stripping every personally identifying field. Nothing is auto-rejected: a human must
approve or reject every candidate, and overriding a high-ranked candidate requires a
written reason. Every AI recommendation and every human decision is written to an
append-only, human-readable audit log. A bias-check panel proves the redaction actually
removed the ranking's exposure to protected attributes.

## Tech stack (fastest path that meets the bar)

- **Backend**: Python 3, standard library only (`http.server`, `json`, `re`, `dataclasses`).
  No pip install step for judges.
- **Frontend**: static HTML + vanilla JS + CSS, served by the same process. No build step.
- **Persistence**: flat JSON/JSONL files under `app/data/` (candidates, job, decisions,
  audit log). No database — appropriate for a demo, and it keeps "where does the data
  live" trivially answerable (a directory on disk you can point at).
- **Tests**: `unittest`, stdlib only, no pip install.

## File layout

```
app/
  server.py        # HTTP server + routes (owns integration; written last)
  scoring.py        # deterministic rubric scorer
  redaction.py       # PII stripper + free-text scrubber
  audit.py          # append-only audit log + bias-check aggregate
  data/
    job.json         # one job posting
    candidates.json    # ~14 synthetic candidates (never real people)
    decisions.json     # runtime-written, human decisions per candidate id
    audit_log.jsonl    # runtime-written, append-only
  static/
    index.html
    app.js
    styles.css
tests/
  test_scoring.py
  test_redaction.py
  test_audit.py
README.md
docs/
  architecture.md    # sovereign Azure target-state diagram (mermaid) + narrative
pitch/
  sovereign-hiring-console.pptx   # 5-minute pitch deck
```

## Interface contract (fixed up front so build phases can run in parallel)

### `app/data/job.json`
```json
{
  "id": "job-2026-eng-004",
  "title": "string",
  "location": "string, must state an EU city/region",
  "description": "string",
  "must_have_skills": ["string", "..."],
  "nice_to_have_skills": ["string", "..."],
  "min_years_experience": 0
}
```

### `app/data/candidates.json` (array)
Each candidate has PII fields (stripped before scoring) and content fields (scored):
```json
{
  "id": "cand-01",
  "full_name": "string",
  "email": "string",
  "phone": "string",
  "address": "string",
  "date_of_birth": "YYYY-MM-DD",
  "gender": "female|male|non_binary|undisclosed",
  "nationality": "string",
  "photo_placeholder": "string, e.g. an initials avatar id",
  "years_experience": 0,
  "skills": ["string", "..."],
  "education": "string",
  "work_history": "free text, 2-4 sentences",
  "cover_letter_excerpt": "free text, 2-4 sentences, may reference age/family/pronouns"
}
```
Synthetic only — invented names/emails, never a real person. Skills/experience should be
varied enough that ranking is not trivially tied (some strong matches, some weak, at
least 2-3 candidates within 5 points of each other to make the override path meaningful).

### `app/redaction.py`
```python
def redact_candidate(candidate: dict) -> dict:
    """Returns {"redacted": {...fields minus PII...}, "removed_fields": [str, ...],
    "scrubbed_spans": [{"field": str, "original": str, "replacement": str}, ...]}.
    Strips full_name, email, phone, address, date_of_birth, gender, nationality,
    photo_placeholder entirely. Additionally regex-scrubs work_history and
    cover_letter_excerpt for: the candidate's own name, standalone age mentions
    ("32 years old", "aged 29"), and gendered pronouns (he/him/his/she/her/they/them as
    whole words), replacing each with "[REDACTED]" and recording the original span in
    scrubbed_spans."""
```

### `app/scoring.py`
```python
def score_candidate(redacted_fields: dict, job: dict) -> dict:
    """Returns {"score": float 0-100, "matched_must_haves": [...], "missing_must_haves": [...],
    "matched_nice_to_haves": [...], "explanation": str}. Deterministic rubric:
    - 60 points max, split evenly across job["must_have_skills"] (case-insensitive
      substring/skill-list match against redacted_fields["skills"])
    - 20 points max, split evenly across job["nice_to_have_skills"]
    - 20 points for years_experience >= min_years_experience, scaled down linearly if
      under (0 if years_experience == 0)
    Round score to 1 decimal. explanation is a template-generated sentence naming exactly
    which must-haves matched/were missing and whether the experience bar was met — no
    opaque black-box output; every number in the score must be traceable in the sentence."""
```

### `app/audit.py`
```python
def log_event(event_type: str, payload: dict) -> dict:
    """Appends {"ts": iso8601 str (pass in explicitly, do not call datetime.now() at
    import time), "event": event_type, **payload} as one JSON line to
    app/data/audit_log.jsonl. Returns the written record."""

def read_audit_log() -> list[dict]:
    """Returns all records from audit_log.jsonl, oldest first, [] if file absent."""

def bias_check(candidates_with_scores: list[dict], unredacted_by_id: dict) -> dict:
    """candidates_with_scores: [{"id":..., "score":...}, ...]. unredacted_by_id maps id ->
    original candidate dict (server-side only, never sent to the client per-candidate).
    Returns {"groups": {"female": {"n": int, "avg_score": float}, "male": {...}, ...},
    "max_spread": float, "statement": human-readable one-liner}. Used ONLY to produce this
    aggregate; never used to re-identify or re-rank a candidate."""
```

### HTTP API (`app/server.py`, stdlib `http.server`)
- `GET /` → `static/index.html`
- `GET /static/<path>` → static assets, `Content-Type` by extension
- `GET /api/job` → job.json contents
- `GET /api/candidates` → array sorted by score desc, each item:
  `{id, redacted_profile, removed_fields, scrubbed_spans, score, explanation,
  matched_must_haves, missing_must_haves, matched_nice_to_haves, decision_status:
  "pending"|"approved"|"rejected", decision_reason, decision_actor}` (decision fields
  come from `decisions.json`, default `"pending"`/`null`).
- `GET /api/bias-check` → `bias_check()` output.
- `GET /api/audit-log` → `read_audit_log()`, newest first for display.
- `POST /api/decide` body `{"candidate_id": str, "decision": "approve"|"reject",
  "actor": str (required, non-empty), "reason": str (required only if decision ==
  "reject" AND the candidate's rank is in the top 3 by score — i.e. an override)}`.
  Validates, updates `decisions.json`, calls `log_event("human_decision", {...})`,
  returns the updated candidate record. 400 on missing/invalid fields — never silently
  accept a decision without an actor.
- Every ranking computation also gets one `log_event("ai_recommendation", {...})` per
  candidate the first time `/api/candidates` is served in a process lifetime (idempotent
  per id — do not re-log on every poll), so the audit log shows the AI's original
  recommendation next to whatever the human later decided.

### Frontend (`static/`)
Single page, "Recruiter Console":
- Header: job title/location, a "Sovereignty" banner: "All data processed locally. No
  external API calls. No data leaves this machine." with a link to `docs/architecture.md`
  content (rendered inline or as a modal — no build step, so simplest is an expandable
  `<details>` block with the same narrative).
- Bias-check panel (from `/api/bias-check`).
- Candidate list sorted by score: each card shows score, explanation, matched/missing
  skills, a `<details>` "Redacted fields" showing `removed_fields` + `scrubbed_spans`
  before/after, decision buttons (Approve/Reject), a reason field that appears when
  required, and current `decision_status`.
- Audit Log tab: renders `/api/audit-log` as a readable timeline.

## Build phases

1. **Understand** (done) → `CHALLENGE.md`.
2. **Plan** (done) → this file.
3. **Build — parallel, independent files given the contract above**:
   synthetic data, `redaction.py`+tests, `scoring.py`+tests, `audit.py`+tests,
   `server.py`, `static/*`. Run as one fan-out; no phase here depends on another phase's
   *output*, only on the contract already fixed above.
4. **Integrate** (sequential, one owner): wire it up, run the server, curl every
   endpoint, click through the UI, fix any mismatch between what an agent assumed and
   what another agent actually wrote.
5. **Review — parallel**: code-reviewer + security-reviewer over the new `app/` code
   (mandatory per this repo's code-review/security rules for new user-input-handling
   code). Fix CRITICAL/HIGH findings.
6. **Deliver**: `README.md`, `docs/architecture.md`, pitch deck (`pitch/*.pptx`), git
   init + commit, attempt GitHub push, final report.

Phases 3 and 5 are the two Workflow fan-outs; 1/2/4/6 are single-owner and done directly.
