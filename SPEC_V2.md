# SPEC v2 — Sovereign Hiring Agent (rebuild)

Supersedes the v1 stdlib build for this same HR/Talent scenario. v1's app/, tests/,
pitch.html, README.md are being replaced; CHALLENGE.md's scenario choice and named
regulations stand, docs/architecture.md's sovereign-Azure target narrative is retained as
context but is no longer this doc's concern.

## What changed and why

The user supplied stricter, more specific requirements: a genuine AI agent (reasoning
loop + tools) calling the real Claude model, not a deterministic rubric; Next.js +
Tailwind + FastAPI; a live-streamed reasoning feed; specific named regulations in the
UI (EU AI Act Art. 6, GDPR Art. 22); a rebuilt pitch deck with a 1:1 slide-topic mapping
and a hidden presenter-only Q&A slide.

## Hard constraint discovered this session: no metered Claude API access

This environment has no `ANTHROPIC_API_KEY`. The user has a Claude Pro subscription and
wants to use that, for free, rather than pay for API access. The only way to reach a real
Claude model without a key is shelling out to the already-authenticated `claude` CLI
(OAuth session). Measured empirically before committing to this design:

- `claude -p "<prompt>" --output-format json`, even from a directory with no
  CLAUDE.md/project config and with slash-commands/MCP disabled: **~$0.33–0.67
  cost-equivalent and ~2.5–3.5s latency per call**, because the full Claude Code coding-
  agent harness (built-in tool schemas, system prompt) loads every time. `--bare` mode
  removes that overhead but explicitly **requires** `ANTHROPIC_API_KEY` (forbids OAuth) —
  not available here.
- A true multi-round-trip tool-use loop (5 separate reasoning calls per candidate — one
  per tool) would mean ~70 CLI invocations for 14 candidates: several minutes of latency
  and a large chunk of the user's subscription usage quota, for a single demo run. Not
  viable for a live 5-minute pitch.

**Decision**: the agent makes **one consolidated `claude -p` reasoning call per
candidate**, run from a clean temp working directory (to minimize — not eliminate — the
fixed harness overhead), asking for a structured JSON response covering every reasoning
stage at once (redaction rationale, score interpretation, bias note, recommendation +
justification). The five pipeline **tools remain real, independent, deterministic
Python functions** — `redact_pii`, `score_candidates`, `bias_check`, `flag_for_approval`,
`log_to_audit` — that actually execute and produce the real data shown on screen; only
the natural-language narration and the recommendation come from the single Claude call.
The backend streams each tool's real result plus its slice of Claude's narration to the
frontend as a sequence of SSE events, so the UI shows a genuine multi-step agent
pipeline, paced to feel live, built from one efficient model call instead of five
expensive ones. This is disclosed as a design decision in README.md and the pitch — not
hidden.

Sovereignty is preserved even though a cloud model is now in the loop: **the Claude call
never receives raw PII**. `redact_pii` always runs first, in local Python; the prompt
sent to Claude contains only the already-redacted profile, the job posting, the
deterministic score, and the bias-check aggregate — never a name, email, phone, address,
DOB, gender, nationality, or photo. This is enforced in code (the brain module's prompt
builder only ever receives the redacted dict) and is itself a claim the demo can prove by
inspecting the exact request payload.

## Architecture

```
backend/                      FastAPI, Python
  app/
    main.py                    FastAPI app, routes, CORS, static seed data load
    tools.py                   5 real deterministic tools (redact_pii, score_candidates,
                                bias_check, flag_for_approval, log_to_audit)
    brain.py                   builds the one-shot prompt, shells out to `claude -p`
                                from a clean temp cwd, parses the structured JSON reply
    orchestrator.py            the agent loop: sequences tool calls + brain narration
                                per candidate, yields ordered AgentEvent objects
    audit.py                   append-only JSONL audit log (ai_recommendation /
                                human_decision), adapted from the v1 module
    models.py                  pydantic models for all request/response/event shapes
    data/job.json               reused, one job posting
    data/candidates.json        reused, the 14 synthetic candidates from v1 (already
                                 diverse, already redaction-triggering, already
                                 validated) — no reason to re-invent them
  tests/                       pytest, mocks brain.call_claude so tests never shell out
  requirements.txt

frontend/                     Next.js 14 (App Router), Tailwind, dark theme
  app/
    page.tsx                   dashboard: data-residency banner, run-agent trigger,
                                live reasoning feed, candidate list, approval gate
    components/
      DataResidencyBanner.tsx   "where your data lives" indicator (hard requirement 1)
      RedactionReveal.tsx       before/after PII redaction animation (hard requirement 2)
      ReasoningFeed.tsx         live SSE-streamed agent steps
      ApprovalGate.tsx          the centerpiece: recommendation + accept/override,
                                 override requires a written reason (hard requirement 3)
      RegulationBadge.tsx       "EU AI Act Art. 6" / "GDPR Art. 22" badges (hard req 4)
      AuditLogView.tsx
    lib/api.ts                  typed fetch/SSE client for the FastAPI backend
  package.json, tailwind.config.ts, next.config.mjs

run.py                        one-command launcher: starts uvicorn + next dev,
                               waits for both, opens the browser
README.md                     rewritten for the new stack and run command
pitch.html                    rebuilt per the new 5-slide + hidden-Q&A spec
```

## Tool contracts (all real, all deterministic, all reused/adapted from the validated v1
logic)

- `redact_pii(candidate: dict) -> RedactionResult` — strips the same 8 PII fields, scrubs
  the same 3 free-text fields for name/age/pronoun mentions. Same behavior as v1's
  `app/redaction.py`, ported in.
- `score_candidates(redacted: dict, job: dict) -> ScoreResult` — same 60/20/20 rubric,
  same template explanation, ported from v1's `app/scoring.py`.
- `bias_check(scores: list, unredacted_by_id: dict) -> BiasResult` — same
  `MIN_GROUP_SIZE=3` k-anonymity suppression (the real bug found and fixed in v1),
  ported from v1's `app/audit.py`.
- `flag_for_approval(candidate_id: str, recommendation: str, reasoning: str) -> None` —
  marks the candidate `status="pending_review"` with the agent's own recommendation
  attached; nothing is ever auto-finalized.
- `log_to_audit(event: dict) -> dict` — append-only JSONL, same shape as v1's
  `app/audit.py::log_event`.

## Human oversight model (updated for the new "agent recommends, human decides" framing)

Every candidate gets an agent **recommendation** (`approve` or `reject`) with reasoning,
via `flag_for_approval`. A human reviewer can:
- **Accept** the recommendation as-is (one click).
- **Override** it (approve what the agent rejected, or reject what it approved) — this
  requires a non-empty written reason, enforced client- and server-side, exactly like
  v1's top-3 override rule but now applied to every override rather than only top-3
  rejections, since there is no ranking-based "top 3" concept in a per-candidate
  recommendation model.

Named regulations shown directly in the UI, not just documentation:
- **EU AI Act, Article 6** (classification rules that make employment-related AI
  "high-risk", triggering the oversight duties this app implements).
- **GDPR, Article 22** (right not to be subject to a solely automated decision).

## Deliverables checklist

- [ ] Working app: `python run.py` starts backend + frontend, opens browser
- [ ] README.md — new stack, run command, architecture, the CLI-cost tradeoff disclosed
- [ ] pitch.html — 5 slides mapped 1:1 to the given topics + judging-criteria-aware
      speaker notes + hidden presenter-only Q&A slide
- [ ] GitHub push
