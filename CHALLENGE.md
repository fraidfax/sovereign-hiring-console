# Challenge: "What becomes possible when trust is built in?" (Microsoft — Data Sovereignty)

Extracted from `September_Hack_Challenge_Slides_Microsoft.pptx`.

## The ask

Design and build an AI-powered assistant/agent/solution that helps organisations create
**sovereign and secure AI environments**. It must help organisations:

- Understand and interpret data residency, privacy, and compliance requirements.
- Design secure and sovereign Azure environments based on business and regulatory needs.
- Apply governance, security, and responsible-AI principles by default.
- Accelerate AI adoption while keeping humans in control of critical decisions.

## The fixed bar (applies to every scenario)

1. Show **where the data lives**.
2. Prove **one concrete privacy/security technique** (not just claim it).
3. Keep a **human in the loop** for at least one critical decision.
4. Name the **regulation** you're designing for (GDPR, EU AI Act, NIS2, sector rules).

## Suggested scenarios (pick one, or bring your own)

| Scenario | Core idea | Regulatory focus |
|---|---|---|
| Manufacturing | Factory-floor copilot answering from on-site machine logs, with a lineage panel tracing every answer to its source log entry | GDPR (operator data), EU AI Act transparency (workplace AI) |
| **HR / Talent** | AI ranks candidates and explains its reasoning; **no rejection is final without a human**; bias-check summary shown alongside every ranking | EU AI Act high-risk employment rules; GDPR Art. 22 (automated decisions) |
| Retail | Shopping/service assistant on purchase history, EU-hosted, with a human-readable audit log | GDPR consent/profiling, EU AI Act transparency |

## Deliverables

- A working end-to-end demo (small is fine, but it must run).
- A 5-minute pitch covering: the sovereignty challenge, the proposed solution, how it
  maintains control/transparency/trust, how AI creates value, and how the design aligns
  with data-sovereignty and responsible-innovation principles.

## Judging criteria

1. Does it solve a real, believable problem for a real user?
2. Can you **show, not just claim**, that sensitive data stayed under control?
3. Did you address at least one concrete privacy/security technique **and** one human
   oversight moment?
4. Is the demo working end-to-end, even if small?

## Decisions made (no stakeholder available to ask — proceeding autonomously)

- **Scenario chosen: HR / Talent screening with a human veto.** Of the three, it has the
  most explicit, literal human-in-the-loop requirement (a veto button) and the most
  natural home for a demonstrable privacy technique (anonymized/blind screening), which
  together map directly onto judging criteria 2 and 3. It also needs no synthetic
  "machine logs" or "purchase history" corpus with retrieval infrastructure — a
  structured candidate list is enough to build and demo quickly and reliably.
- **Privacy/security technique: PII redaction ("blind screening") before scoring.** Name,
  email, phone, address, date of birth, gender, nationality, and photo placeholder are
  stripped from every candidate before the scoring engine ever sees it; free-text fields
  (cover letter, work history) get a second-pass regex scrub for names/ages/pronouns. The
  UI shows a visible before/after diff so the claim is provable, not asserted.
  Maps to **GDPR Art. 5 (data minimisation)**.
- **AI is a deterministic, template-explained rubric engine, not a hosted LLM call.**
  This environment has no Azure/OpenAI/Anthropic API key configured, and a real API call
  would mean HR data leaving the machine — which undercuts the sovereignty pitch. A fully
  local, deterministic, rule-based scorer is instead framed as the *stronger* answer to
  "apply responsible-AI principles by default": it is 100% explainable, reproducible, and
  auditable, and it never sends candidate data anywhere. This is disclosed explicitly in
  the pitch, not hidden.
- **Human oversight: nothing is auto-decided.** Every candidate starts `pending`; an
  `approve`/`reject` action from a named human actor is required to finalize a decision,
  and rejecting a candidate the engine ranked highly requires a written override reason.
  Maps to **GDPR Art. 22** and **EU AI Act Annex III / Art. 14** (human oversight for
  high-risk employment AI).
- **Sovereign Azure design is a documented target architecture, not a live deployment.**
  No Azure subscription is available in this environment. The repo includes an
  architecture diagram/narrative (EU region, Azure OpenAI in the EU Data Boundary if an
  LLM were added later, Private Link/VNet, Microsoft Purview for governance, Confidential
  Compute, Customer-Managed Keys via Key Vault, immutable audit storage, Entra ID RBAC)
  as the production target this demo is a working proof-of-concept for. This is stated as
  an assumption, not presented as if it were deployed.
- **Tech stack: Python standard library only**, front end is static HTML/CSS/vanilla JS.
  Zero install friction for judges (`python server.py` and open a browser) and zero
  third-party dependency/licensing risk in a time-boxed build.
- **GitHub push**: attempted at the end of the build; this environment has no `gh` CLI
  and no configured git credential helper, so it may not be possible without the user
  supplying a remote/auth. Flagged in the final report rather than blocking the build.
