# Sovereign Hiring Agent — Data Sovereignty + Human Veto for AI Recruitment

**An AI agent screens job candidates with PII redaction and a human approval gate on every decision — no candidate decision is ever final without a human reviewer.**

This is a working end-to-end proof of concept demonstrating secure, sovereign AI use in high-risk employment settings. The agent ranks candidates using deterministic scoring and Claude reasoning, but the hiring decision always remains under human control. All candidate data stays on the local machine; sensitive information is stripped before any external model call. Bias is tracked and suppressed per k-anonymity rules to prevent re-identification of small demographic groups.

---

## How to Run It

### Prerequisites

- **Python 3.10+** with `pip` (install dependencies: `pip install -r backend/requirements.txt` from the `backend/` directory)
- **Node.js 18+** with `npm` (install frontend deps: `npm install` from the `frontend/` directory)
- **Claude CLI** installed and authenticated (`claude auth status` should show an active session; this app uses your existing Claude Pro subscription, not a paid API key)

### One-Command Launch

```bash
python run.py
```

This starts the FastAPI backend (port 8000) and Next.js frontend (port 3000) as subprocesses, waits for both to come up, and opens your browser to http://localhost:3000. Press Ctrl+C to stop both servers.

### Manual Launch (Alternative)

**Terminal 1** — Backend:
```bash
cd backend
python -m uvicorn app.main:app --port 8000
```

**Terminal 2** — Frontend:
```bash
cd frontend
npm run dev
```

Then open http://localhost:3000 in your browser.

---

## Why the Claude CLI Instead of an API Key?

This demo has no `ANTHROPIC_API_KEY` because it deliberately uses your existing Claude Pro subscription (via OAuth). The CLI approach makes the reasoning call one consolidated call per candidate instead of a 5-round-trip tool-use loop:

- **One-shot design**: Every reasoning stage (redaction note, score interpretation, bias reflection, recommendation) is captured in one structured JSON request to the Claude CLI.
- **Cost/latency tradeoff**: A live 5-round tool-use loop would be ~70 CLI calls for 14 candidates (many minutes of latency, significant subscription quota burn). One call per candidate is ~2–3s each and minimal quota impact.
- **Sovereignty still held**: The prompt never contains raw PII — only the already-redacted profile. The single Claude call only receives anonymized data plus aggregate bias stats.

This is disclosed in the UI (the data-residency banner says "Claude receives no PII fields") and in the pitch deck, not hidden.

---

## The Agent Architecture

### Five Real Tools (All Deterministic, All Synchronous)

1. **`redact_pii(candidate)`** — Strips 8 PII fields (name, email, phone, address, DOB, gender, nationality, photo) and scrubs mentions of those data points (plus ages and pronouns) from free-text fields (work history, cover letter, education). Returns the redacted profile plus a detailed log of what was removed.

2. **`score_candidate(redacted_profile, job)`** — Applies a deterministic 60/20/20 rubric:
   - Must-have skills: 60 points
   - Nice-to-have skills: 20 points
   - Years of experience: 20 points
   Returns the numerical score and a human-readable explanation of every component.

3. **`bias_check(scored_candidates, unredacted_data)`** — Compares average scores across demographic groups (gender, disclosed/undisclosed). **Applies k-anonymity**: groups smaller than 3 people are combined into one "suppressed" bucket whose average is not computed at all (withheld, not hidden). This prevents re-identification of individuals in tiny groups.

4. **`flag_for_approval(candidate_id, recommendation, reasoning)`** — Marks the candidate `status="pending_review"` and attaches the agent's recommendation and reasoning. This is the only function that moves a candidate out of "processing"; nothing is ever auto-approved or auto-rejected.

5. **`log_to_audit(event_type, payload, timestamp)`** — Appends every decision to an immutable JSONL audit log on disk. Two event types: `ai_recommendation` (agent suggests approve/reject) and `human_decision` (human accepts or overrides, with the actor's name and reason if overriding).

### Reasoning Loop Per Candidate

1. **Redact & Score** (runs serially for all candidates):
   - redact_pii() → real-time SSE event to frontend
   - score_candidate() → real-time SSE event

2. **Bias Check** (once for the whole cohort):
   - bias_check() on all scored candidates → suppresses small groups, calculates spread
   - SSE event to frontend

3. **Brain Reasoning** (bounded concurrency: max 3 simultaneous Claude calls):
   - For each candidate, build a one-shot prompt containing the redacted profile, score result, and bias statement
   - Call `claude -p <prompt> --output-format json` from a clean temp directory
   - Parse the JSON reply for redaction note, score note, bias note, recommendation, and reasoning
   - On any failure (timeout, malformed JSON, CLI exit nonzero), fall back to a clearly-labeled automatic recommendation (score >= 60 → approve, else reject)
   - Emit redaction/score/bias narration to frontend (one SSE event per note)
   - Call flag_for_approval() to set status="pending_review"
   - Log the recommendation to audit trail
   - Emit recommendation SSE event to frontend

### Event Stream Shape

Every event on the SSE stream has this structure:
```json
{
  "type": "tool_call" | "tool_result" | "narration" | "recommendation" | "done",
  "candidate_id": "cand-XX" | null,
  "tool": "redact_pii" | "score_candidate" | "bias_check" | "brain" | null,
  "detail": {},
  "ts": "2026-09-20T12:34:56.789Z"
}
```

The frontend subscribes to this stream and reconstructs a live view of which candidates are being processed, their scores, the agent's narration, and its recommendation.

---

## How This Meets the Hard Requirements

### 1. Show Where the Data Lives
**Component**: `frontend/app/components/DataResidencyBanner.tsx`  
**Endpoint**: `GET /api/data-residency`

The banner shows:
- Location: "This machine — localhost, no cloud deployment"
- External services: Claude (reasoning narration only), labeled "0 PII fields sent"
- Counter: "0 requests carrying personal data have left this boundary"

### 2. Prove One Concrete Privacy/Security Technique
**Component**: `frontend/app/components/RedactionReveal.tsx`  
**Tool**: `backend/app/tools.py::redact_pii`

Before/after diff showing:
- **Stripped fields**: full_name, email, phone, address, date_of_birth, gender, nationality, photo_placeholder
- **Scrubbed free text**: name mentions, ages, pronouns redacted from work history, cover letter, education

Click "PII redaction — before / after" to expand and see exactly what was removed.

**Test that proves it**: `backend/tests/test_tools.py::test_pii_fields_fully_removed` and `test_name_age_and_pronoun_mentions_are_scrubbed_in_free_text`

### 3. Human in the Loop on Every Critical Decision
**Component**: `frontend/app/components/ApprovalGate.tsx`  
**Endpoint**: `POST /api/decide`

For every candidate:
- Agent makes a recommendation (approve or reject)
- Status moves to "pending_review"
- Human reviewer enters their name, then:
  - **Accept**: One click, no reason required (the agent's reasoning is on screen)
  - **Override**: Requires a non-empty written reason, enforced client and server side
- Decision is recorded with actor name, timestamp, reason (if override), and is_override flag
- Audit log stores both the agent's recommendation and the human's decision

Override examples shown on screen explain why this path is accountable.

### 4. Name the Regulation You're Designing For
**Component**: `frontend/app/components/RegulationBadge.tsx`

Two badges visible in the approval-gate section:
- **EU AI Act, Article 6**: "Classifies employment-related AI as high-risk, which triggers a legal duty for human oversight of its outputs."
- **GDPR, Article 22**: "Gives candidates the right not to be subject to a decision based solely on automated processing — a human must review it."

Hover or click each badge to see the full gloss.

---

## Sovereignty Claim: Precisely Stated

**Claude never receives raw PII.**

### Which Fields Are Never Sent to Claude

The following PII fields are **always** stripped before the prompt is built:
- `full_name`
- `email`
- `phone`
- `address`
- `date_of_birth`
- `gender`
- `nationality`
- `photo_placeholder`

Additionally, free-text fields (work history, cover letter, education) are scrubbed of:
- Any name mention (extracted from full_name)
- Any age mention (regex patterns for "32 years old", "aged 29", "I'm 34", etc.)
- Any pronoun (he, him, she, her, they, them, his, her, their, etc.)

### What Claude Receives Instead

The prompt contains only:
1. The already-redacted candidate profile (PII fields absent, free text scrubbed)
2. The job posting (never contains PII)
3. The deterministic score result (only numbers and skill names, no candidate identity)
4. An aggregate bias-check statement (group-level averages, no individual scores)

### Proof

**Test**: `backend/tests/test_brain.py::test_prompt_never_contains_raw_pii_field_names_or_values`

This test:
1. Takes a fully realistic PII-laden candidate (full name "Zara Al-Sayed", email, phone, address, etc.)
2. Redacts it
3. Mocks the subprocess call to capture the exact prompt string
4. Asserts that the raw PII values (name, email, phone, etc.) **do not appear** in the literal prompt
5. Asserts that the field names (e.g., `"full_name"`) **do not appear** in the literal prompt

**Defensive fallback** (in `backend/app/brain.py::_assert_no_pii`):
Even if the caller's redaction were buggy, the brain module refuses to build a prompt at all if any PII field key is present. It raises `ValueError("refusing to call Claude: PII fields leaked...")` before the subprocess is invoked.

---

## Tests

### Run the Test Suite

```bash
cd backend
python -m pytest tests -v
```

### Current Status: 33 Tests, All Passing

```
backend/tests/test_brain.py
  test_happy_path_parses_correctly PASSED
  test_cli_timeout_falls_back_cleanly PASSED
  test_cli_malformed_json_falls_back_cleanly PASSED
  test_cli_nonzero_exit_falls_back_cleanly PASSED
  test_model_json_wrapped_in_code_fences_is_parsed PASSED
  test_prompt_never_contains_raw_pii_field_names_or_values PASSED [SOVEREIGNTY PROOF]
  test_pii_leak_in_redacted_profile_raises_before_calling_claude PASSED

backend/tests/test_main.py (7 tests)
  test_get_job_returns_seed_job PASSED
  test_get_candidates_returns_all_not_started_initially PASSED
  test_security_headers_present_on_every_response PASSED
  test_data_residency_shape PASSED
  test_run_agent_route_starts_background_task_when_idle PASSED
  test_run_agent_route_reports_already_running PASSED
  test_decide_* (override/reason validation) PASSED [6 tests]
  test_audit_log_is_newest_first PASSED

backend/tests/test_tools.py
  test_pii_fields_fully_removed PASSED
  test_name_age_and_pronoun_mentions_are_scrubbed_in_free_text PASSED
  test_curly_apostrophe_age_mention_is_scrubbed PASSED
  test_full_match_scores_near_100 PASSED
  test_zero_match_scores_zero PASSED
  test_score_candidate_is_deterministic PASSED
  test_empty_requirement_lists_score_full_marks_no_zero_division PASSED
  test_bias_check_suppresses_singleton_groups_and_withholds_avg_score PASSED [BIAS BUG PROOF]
  test_bias_check_with_no_scored_candidates_for_a_group_is_skipped PASSED
  test_flag_for_approval_sets_pending_review_never_final PASSED
  test_log_to_audit_appends_jsonl_with_caller_supplied_ts PASSED
  test_read_audit_log_skips_malformed_lines PASSED
  test_read_audit_log_returns_empty_list_when_file_absent PASSED
```

### Most Important Tests

1. **`test_bias_check_suppresses_singleton_groups_and_withholds_avg_score`**: Proves the k-anonymity fix. Groups of fewer than 3 candidates are combined into one "suppressed" bucket whose average score is **never computed** (genuinely withheld, not computed then hidden), preventing re-identification of individuals in tiny demographic groups.

2. **`test_prompt_never_contains_raw_pii_field_names_or_values`**: Automated proof that the literal prompt string handed to Claude contains zero raw PII values and zero PII field names — the sovereignty claim is mechanically verified by the test harness.

---

## Scope: What's Out of Scope / Honest Limitations

### By Design (Deliberate Trade-Offs)

- **No metered API key**: This app uses the `claude` CLI (OAuth via Claude Pro) instead of `ANTHROPIC_API_KEY`. Tradeoff: bounded to your subscription quota; latency ~2–3s per candidate; cost modeled in SPEC_V2.md. Benefit: no API billing, no shared key in the environment, easier for a judge to run without secrets.

- **One consolidated Claude call per candidate, not multi-round tool use**: See SPEC_V2.md § "Hard constraint discovered this session". A 5-round-trip loop would be 70+ CLI calls for 14 candidates. One call per candidate preserves sovereignty (still no PII sent) while keeping latency under 1 minute for a full demo run.

- **No persistent database**: In-memory store only (candidate data, job posting, decisions). Audit log persists to disk as append-only JSONL (`backend/app/data/audit_log.jsonl`). Benefit: no schema, no migrations, judges can inspect the raw audit file. Limitation: restarting the backend wipes all decision state (not the audit log). Running a second time requires deleting `backend/app/data/audit_log.jsonl` or restarting fresh.

- **No authentication on local dev servers**: Both backend and frontend accept any request from localhost. Auth is not the focus of this demo (human oversight is); it would be added in production via Entra ID (Azure) or another identity layer mentioned in `docs/architecture.md` (the production-target narrative).

- **Scoring is deterministic, not ML-driven**: The 60/20/20 rubric is hard-coded, not learned. Benefit: fully explainable, reproducible, auditable. Limitation: judges cannot ask "what would happen if I tweak the weights" — the rubric is baked. Future versions could add tunable weights or swap in a real ML model while keeping the redaction and oversight layers.

### Operational Notes

- **Re-running the agent** requires restarting the backend (the in-memory store must be reset). Once a run completes and decisions are recorded in the audit log, running the agent again fetches any candidates not yet processed. Starting from scratch: delete `backend/app/data/audit_log.jsonl` and restart.

- **Concurrency**: Claude calls are bounded to 3 simultaneous (via semaphore in `orchestrator.py`). With 14 candidates, a full run takes ~2–3 seconds per candidate × number of concurrent slots, or roughly 10–20 seconds total.

- **No file uploads**: Candidate data is loaded from `backend/app/data/candidates.json` at startup. The 14 synthetic candidates are reused from the earlier v1 build — already diverse, already redaction-heavy, already validated.

- **Browser refresh mid-demo**: The SSE event stream replays all events emitted so far, so refreshing the browser mid-run shows the full history up to that point, plus streams any new events as they happen.

---

## Architecture Files

- **Backend**: `backend/app/main.py` (FastAPI routes), `backend/app/tools.py` (five real tools), `backend/app/brain.py` (Claude CLI interface), `backend/app/orchestrator.py` (agent loop), `backend/app/store.py` (in-memory state).
- **Frontend**: `frontend/app/page.tsx` (main dashboard), `frontend/app/components/` (DataResidencyBanner, RedactionReveal, ApprovalGate, RegulationBadge, ReasoningFeed, CandidateCard, AuditLogView, ErrorBanner).
- **Launcher**: `run.py` (one-command startup).
- **Specification**: `SPEC_V2.md` (detailed rationale for design decisions), `CHALLENGE.md` (the original challenge brief and scenario choice).
- **Production Target**: `docs/architecture.md` (EU-region Azure deployment with Confidential Compute, Customer-Managed Keys, Private Link, etc. — this demo is a proof-of-concept for that architecture).

---

## Files and Tools Involved

### Data & Config

- `backend/app/data/job.json` — The job posting (must-haves, nice-to-haves, experience requirement)
- `backend/app/data/candidates.json` — 14 synthetic candidates with diverse demographics and redaction-triggering data
- `backend/app/data/audit_log.jsonl` — Created at runtime, appended to on every decision

### Backend Dependencies

See `backend/requirements.txt`:
- `fastapi`, `uvicorn[standard]` — HTTP server
- `pydantic` — Request/response validation
- `pytest`, `httpx` — Testing

No ORM, no database client, no external API clients (Claude call via subprocess, not SDK).

### Frontend Dependencies

See `frontend/package.json`:
- `next` 14.2.35 — App Router
- `react` 18.3.1, `react-dom` 18.3.1
- `tailwindcss` 3.4.3 — Styling (dark theme, custom tokens)
- `typescript` 5.4.5

---

## Judges: How to Verify the Claims

1. **"No PII ever reaches Claude"**: Read `backend/tests/test_brain.py::test_prompt_never_contains_raw_pii_field_names_or_values`. Run it. Inspect the test output — it captures the exact subprocess argv and asserts the prompt string.

2. **"PII is redacted before the UI shows it"**: Click "PII redaction — before / after" on any candidate card. See the fields and text scrubbed.

3. **"Bias is suppressed per k-anonymity"**: Run `python -m pytest backend/tests/test_tools.py::test_bias_check_suppresses_singleton_groups_and_withholds_avg_score -v`. The test proves singleton groups are withheld, not computed.

4. **"Every decision requires human confirmation"**: Try clicking "Run Agent" and then waiting for candidates to appear. Each candidate will be in "pending_review" state. Try clicking "Accept" without entering a reviewer name — it will error. Try clicking "Override" without a reason — it will error. Enter your name and a reason; the decision records.

5. **"The audit log is immutable"**: Look at `backend/app/data/audit_log.jsonl` after running the agent and making decisions. The file is append-only (each line is one JSON record). Inspect the `human_decision` events — they record the actor, decision, reason (if override), and `is_override` flag.

6. **"Data stays local"**: The DataResidencyBanner shows "This machine — localhost". The API endpoint `GET /api/data-residency` returns zero PII external requests. No cloud backend is involved except the Claude CLI call, which is explicitly shown as "receives no PII fields".

---

## Summary

This is a **working, end-to-end proof of concept** for sovereign, human-controlled AI in high-risk employment screening. It demonstrates:

- **Concrete privacy**: PII redaction before any model call, with before/after UI proof.
- **Audit trail**: Immutable JSONL log of every agent recommendation and human decision.
- **Human veto**: No candidate outcome is final without named human approval; overrides require written justification.
- **Regulatory mapping**: EU AI Act Art. 6 and GDPR Art. 22 cited in the UI, connected to the design (high-risk classification, duty of oversight, right not to be solely automated).
- **Sovereignty hold**: Claude call never receives raw PII — proven by test.
- **Transparent limitations**: No persistent database, bounded to subscription quota, all decisions reset on backend restart. These are acknowledged, not hidden.

**Start with `python run.py`**. Everything else follows.
