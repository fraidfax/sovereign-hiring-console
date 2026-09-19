# Sovereign Hiring Console

A recruiter-facing hiring app that ranks candidates using a deterministic scoring engine after stripping personally identifying information. Nothing is auto-decided: every candidate's final status requires a named human actor, rejecting a top-ranked candidate requires a written reason, and every AI recommendation and human decision is recorded in an append-only audit log. The demo runs entirely on one machine with Python standard library only — no cloud call, no external API, no data egress.

## How to run it

This is a Python 3 stdlib-only app with no pip install step, designed so judges can run it offline.

```bash
python app/server.py
```

The server listens on `http://localhost:8080` by default (bound to `127.0.0.1` only — nothing else on your network can reach it). Open that URL in a browser.

To let other devices on your network reach it (e.g. judges on the same WiFi) — safe here since the dataset is synthetic, but note there is no authentication on this demo server:
```bash
python app/server.py --host 0.0.0.0 --port 8080
```

That's it. The first load takes less than a second. No external network calls happen at any point, even if your machine is offline.

## How this meets the CHALLENGE.md bar

### The four fixed requirements:

1. **Where the data lives** → Every candidate record, decision, and audit event is a JSON file under `app/data/` on local disk. `app/server.py` never reads or writes to any other location. Proof: inspect `/api/candidates` in the browser to see the scoring + redaction, or use `ls app/data/` to see the actual files.

2. **One concrete privacy/security technique** → **PII redaction ("blind screening")**: before the scoring engine ever sees a candidate, `app/redaction.py` strips name, email, phone, address, DOB, gender, nationality, photo entirely. It then regex-scrubs the free-text fields (work history, cover letter) to remove the candidate's name again, standalone age mentions ("32 years old"), and gendered pronouns (he/him/she/her/they/them). The UI shows a `<details>` expandable on each candidate card ("Redacted fields") that displays the before/after of each scrubbed span so the claim is visible and verifiable, not asserted. Maps to **GDPR Article 5 (data minimisation)**.

3. **Human in the loop for at least one critical decision** → Nothing here is auto-decided. Every candidate starts with `decision_status: "pending"`. The `/api/decide` endpoint (called by the "Approve" and "Reject" buttons) is the only code path that changes that status, and it requires: a named human actor (never null or empty), and if the candidate is in the top 3 by score and being rejected, a written reason must accompany it. The UI enforces this: buttons appear for both decisions, a reason field shows conditionally when required (override), and nothing posts to the server without both fields filled. Proof: click "Reject" on a high-ranked candidate and try to submit without a reason — it fails client-side and server-side.

4. **The regulation you're designing for** → **GDPR Articles 5 (lawfulness, fairness, transparency, data minimisation) and 22 (automated decisions), plus EU AI Act Annex III and Article 14 (high-risk employment AI requires human oversight)**. The bias-check panel (on the "Candidates" tab) shows average scores grouped by gender, with a one-line statement of spread, proving the redaction removed the ranking's direct dependency on protected attributes. Groups smaller than 3 (a k-anonymity floor) are combined into one bucket with their average withheld — an earlier version of this panel published a size-1 group's exact average, which *is* that specific candidate's exact score and would have re-identified their gender; `app/audit.py`'s `bias_check()` and `tests/test_audit.py` now both guard against that. The audit log (tab 2) records every AI recommendation and every human decision with actor, reason, and timestamp.

### The four judging criteria:

1. **Solves a real, believable problem** → High-risk employment AI (hiring decisions can alter someone's livelihood) must be explainable, auditable, and under human control. This demo proves that all three are possible without sacrificing sovereignty. Judges can see the code, click through decisions, and read the audit trail.

2. **Can you show sensitive data stayed under control?** → Yes. The demo has no outbound network calls (inspect `app/server.py` for all I/O — it only reads/writes the `app/data/` directory, the codebase, and `/dev/null`). No cloud SDK, no HTTP client imports, no ability to exfiltrate data even if someone tried. Run it offline to prove it works without any network.

3. **Address one privacy/security technique AND one human oversight moment** → Privacy: redaction + scrubbing (above). Human oversight: decision endpoint (above). Audit proof: `/api/audit-log` shows the append-only events; the UI tabs between candidates and the audit trail so judges can trace a decision back to the AI recommendation.

4. **Is the demo working end-to-end?** → Yes. Load the page, see the candidate list ranked by score with redacted fields and explanations visible, click bias-check to see that group averages have minimal spread, expand the audit tab to see the AI recommendations and human decisions, use the Approve/Reject buttons to make a decision (with override reason if needed), and reload the page to confirm the decision persisted.

## Architecture: local proof-of-concept for a sovereign target design

This working demo runs on one machine with flat JSON files and zero network calls, so it can be judged without any Azure subscription or cloud account.

**See `docs/architecture.md`** for the production target: a sovereign Azure environment in the EU Data Boundary with confidential compute, customer-managed encryption keys, private networking (no public endpoints), Entra ID RBAC, immutable audit storage, and Microsoft Purview data classification. That architecture is a design deliverable showing how the same sovereignty and transparency guarantees scale to production. The demo is a proof-of-concept that the core guarantees (no data egress, human decision control, explainable scoring) are technically achievable — the Azure layer adds defense-in-depth (encryption, isolation, formal governance) around the same logic.

## What's deliberately out of scope

- **No external LLM call**: This environment has no Azure/OpenAI API key, and sending HR data to a remote LLM would undercut the sovereignty pitch. Instead, the scoring engine is a deterministic template-explained rubric: 100% explainable, reproducible, auditable, and local. Per CHALLENGE.md, this is a strength, not a compromise — it is framed explicitly in the pitch.

- **No authentication on the demo server**: The UI is for local judging in a controlled environment. A recruiter using this in production would authenticate via Entra ID (as shown in the architecture target). The demo assumes a trusted judge on a trusted network.

- **`decisions.json` is a single flat file, not a real datastore**: writes are lock-protected and atomic (temp file + `Path.replace()`; verified safe under 14 concurrent `POST /api/decide` requests in `tests/test_server.py`), so it won't corrupt — but it's still one file with no query/index/multi-tenant support. Production would use a real store (Azure Storage, Cosmos DB, or PostgreSQL). The code has an inline comment (`ponytail:`) noting this ceiling.
- **No rate limiting**: a single recruiter clicking buttons doesn't need it for this demo; a production deployment behind the Azure architecture in `docs/architecture.md` would add it at the gateway.

## How to run the tests

All tests use Python's stdlib `unittest` framework; no pytest or external dependencies needed.

```bash
python -m unittest discover tests -v
```

This runs all tests in `tests/test_*.py` (28 total):
- `test_scoring.py` — 6 tests covering the rubric engine (full match, no match, missing skills, determinism, experience scaling, empty requirements)
- `test_redaction.py` — 5 tests covering PII removal, name/age/pronoun scrubbing, and span recording
- `test_audit.py` — 9 tests covering append-only logging, file creation, read order, and bias-check aggregation including the k-anonymity suppression (single-group, two-singleton-groups, and mixed-size scenarios)
- `test_server.py` — 8 integration tests that boot a real server on an ephemeral port and exercise it over real HTTP: every `/api/decide` validation branch (missing actor, invalid decision, unknown id, missing override reason), a persisted decision surviving a re-fetch, the security headers on every JSON response, and that `/api/bias-check` never returns a group smaller than 3

Example output:
```
test_appends_and_returns_record (tests.test_audit.TestLogEvent) ... ok
test_groups_below_minimum_size_never_expose_an_individual_score (tests.test_audit.TestBiasCheck) ... ok
test_full_match_scores_close_to_100 (tests.test_scoring.ScoreCandidateTests) ... ok
test_json_responses_carry_security_headers (tests.test_server.ServerTestCase) ... ok
...
Ran 28 tests in 4.5s

OK
```

## Implementation details

**Core modules:**
- `app/server.py` — Stdlib HTTP server (`http.server`), routes all endpoints, integrates redaction/scoring/audit, serves static HTML/JS/CSS. Registers AI recommendations once per process lifetime (idempotent), logs human decisions atomically.
- `app/redaction.py` — Pure function redacting PII fields and regex-scrubbing free text for names, ages, pronouns. Returns the redacted fields, list of removed fields, and list of scrubbed spans with before/after for UI display.
- `app/scoring.py` — Pure function (deterministic, no I/O, no randomness) scoring a redacted candidate against a job using a fixed rubric: 60 pts for must-have skills (evenly split), 20 pts for nice-to-have (evenly split), 20 pts for experience (scaled linearly if below bar). Produces a score (0–100, 1 decimal), explanation (template-generated sentence naming exactly which skills matched/missed), and matched/missing lists.
- `app/audit.py` — Append-only audit log (JSONL, one record per line), bias-check aggregate (computes per-group average scores and max spread from unredacted data server-side only, never re-ranked, never sent to client per-candidate).

**Data:**
- `app/data/job.json` — One job posting (Backend Engineer, Helsinki, 4 yrs experience, 4 must-have + 3 nice-to-have skills).
- `app/data/candidates.json` — 14 synthetic candidates with varied skill matches and experience levels (0–10 yrs), drawn from real EU/global backgrounds. Skills and experience vary enough that the ranking is not trivial; at least 2–3 candidates fall within 5 points of each other, so override judgments matter.
- `app/data/decisions.json` — Runtime-written, one record per candidate with `decision_status` ("pending"/"approved"/"rejected"), `decision_reason` (null unless an override), and `decision_actor` (the human who decided).
- `app/data/audit_log.jsonl` — Runtime-written, append-only. Each line is one JSON record: `{"ts": "2026-09-20T...", "event": "ai_recommendation"|"human_decision", ...}`. Used by the audit tab and as the immutable record per GDPR Art. 12 and EU AI Act Art. 12.

**Frontend:**
- `app/static/index.html` — Semantic HTML, tabbed interface (Candidates / Audit Log).
- `app/static/app.js` — Vanilla JS, no framework, no build step, no CDN. Fetches `/api/job`, `/api/candidates`, `/api/bias-check`, `/api/audit-log`; calls `POST /api/decide` to record decisions. Renders candidate cards with score, explanation, matched/missing skills, expandable "Redacted fields" diff, and Approve/Reject buttons. Conditional reason field for overrides.
- `app/static/styles.css` — Simple, readable styling. Focus on clarity and accessibility (no fancy animations, high contrast, clear touch targets).

## Code locations for proof points

| Claim | File / Endpoint |
|-------|---|
| PII redacted before scoring | `/app/redaction.py` (function `redact_candidate`) → `/api/candidates` shows `removed_fields` and `scrubbed_spans` for every candidate |
| Scoring is deterministic | `/app/scoring.py` (function `score_candidate` is pure, no I/O, no randomness) |
| Explanation is traceable | `/app/scoring.py` lines 104–106 (`_build_explanation`); every number in the score appears in the sentence |
| Human decision required | `app/server.py`'s `Handler._post_decide` (validates actor and override reason) → `/api/decide` endpoint enforces |
| Audit trail is immutable | `app/audit.py` (`log_event` appends, never overwrites; `read_audit_log` skips a malformed line rather than failing the whole read) → `/api/audit-log` returns oldest first |
| Bias check never re-identifies a small group | `app/audit.py`'s `bias_check` (groups below `MIN_GROUP_SIZE=3` are combined and their average withheld) → `/api/bias-check` endpoint; `tests/test_server.py::test_bias_check_never_returns_a_group_smaller_than_three` asserts it live |
| Request bodies are size-capped | `app/server.py`'s `MAX_BODY_BYTES` (64 KB) checked before `rfile.read()` in `_post_decide` |
| Responses carry defensive security headers | `app/server.py`'s `SECURITY_HEADERS` (`nosniff`, `X-Frame-Options: DENY`, same-origin CSP) sent on every JSON and static response |
| No outbound calls | `grep -r "socket\|urllib\|http\|requests\|httpx" app/` returns nothing but `urllib.parse`/`http.server` (stdlib routing, not a client); only file I/O and stdout |

## Candidate data note

All 14 candidates are synthetic (invented names, emails, addresses). The scenario is realistic (Backend Engineer for an EU-based fintech/SaaS product), but the individuals do not exist. The data is diverse in nationality, gender, experience level, and skill mix to make the ranking meaningful and the override feature testable.

## Appendix: decision flow

1. Recruiter views candidate list (sorted by score desc).
2. Recruiter reads redacted profile, explanation, matched/missing skills, bias-check context.
3. Recruiter decides (Approve / Reject).
4. If rejecting a top-3 candidate, a reason is required (server-side + client-side validation).
5. POST `/api/decide` with `{candidate_id, decision, actor, reason}`.
6. Server logs `human_decision` event to audit log, persists decision to `decisions.json`.
7. UI updates to show decision status and reason.
8. Recruiter can switch to Audit tab to see all AI recommendations and human decisions in one timeline.

---

**Built for the AaltoAI 2026 hackathon challenge**: "What becomes possible when trust is built in?" — Microsoft Data Sovereignty track.
