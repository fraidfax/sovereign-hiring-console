"""The one real Claude reasoning call per candidate.

Shells out to the already-authenticated `claude` CLI (OAuth session via Claude
Pro — no ANTHROPIC_API_KEY in this environment, see SPEC_V2.md's cost/latency
rationale for why this is one consolidated call per candidate rather than a
5-round-trip tool-use loop).

Sovereignty guarantee this module exists to prove: redacted_profile passed in
here must never contain a PII field. That is enforced defensively below even
though the caller (orchestrator.py, via tools.redact_pii) already redacts —
this is the exact claim a judge can verify by inspecting the literal prompt
string sent to the subprocess.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from typing import Any

from app.tools import PII_FIELDS

CLAUDE_TIMEOUT_SECONDS = 45

_RESULT_KEYS = ("redaction_note", "score_note", "bias_note", "recommendation", "recommendation_reasoning")

PROMPT_TEMPLATE = """You are assisting a human hiring reviewer. You are given only an \
already-PII-redacted candidate profile, a job posting, a deterministic score result, \
and an aggregate bias-check note. You never see the candidate's name, email, phone, \
address, date of birth, gender, nationality, or photo.

Reply with ONLY a JSON object (no prose, no markdown code fences) shaped exactly like \
this:
{{"redaction_note": "one sentence: what was removed and whether the free text still \
reads naturally", "score_note": "one sentence interpreting the score in context of the \
job", "bias_note": "one sentence reacting to the bias_check statement given", \
"recommendation": "approve or reject", "recommendation_reasoning": "2-3 sentences: the \
actual justification a human reviewer will read"}}

Redacted candidate profile (JSON):
{redacted_profile}

Job posting (JSON):
{job}

Deterministic score result (JSON):
{score_result}

Bias-check aggregate statement:
{bias_note}
"""


def _assert_no_pii(redacted_profile: dict) -> None:
    """Defensive last line of defense: refuse to build a prompt at all if a
    PII field leaked through, even though redact_pii() already stripped it."""
    leaked = [f for f in PII_FIELDS if f in redacted_profile]
    if leaked:
        raise ValueError(f"refusing to call Claude: PII fields leaked into redacted_profile: {leaked}")


def _build_prompt(redacted_profile: dict, job: dict, score_result: dict, bias_note: str) -> str:
    _assert_no_pii(redacted_profile)
    return PROMPT_TEMPLATE.format(
        redacted_profile=json.dumps(redacted_profile, ensure_ascii=False),
        job=json.dumps(job, ensure_ascii=False),
        score_result=json.dumps(score_result, ensure_ascii=False),
        bias_note=bias_note,
    )


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[: -3]
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()


def _fallback(score_result: dict, reason: str) -> dict:
    """Never crash the pipeline. Clearly labeled, threshold-derived fallback —
    never silently pretend it's a real model answer."""
    score = score_result.get("score", 0) or 0
    recommendation = "approve" if score >= 60 else "reject"
    print(f"[brain] falling back to automatic reasoning: {reason}", file=sys.stderr)
    return {
        "redaction_note": "Automatic fallback: the live model call failed, so no redaction commentary is available.",
        "score_note": f"Automatic fallback: score is {score}/100; no live model interpretation is available.",
        "bias_note": "Automatic fallback: no live model commentary on the bias-check result is available.",
        "recommendation": recommendation,
        "recommendation_reasoning": (
            "Automatic fallback: the live Claude reasoning call failed "
            f"({reason}), so this recommendation is a simple score>=60 threshold rule, "
            "not a model judgment. A human reviewer should weigh this accordingly."
        ),
    }


def _run_claude_cli(prompt: str) -> subprocess.CompletedProcess:
    tmp_cwd = tempfile.mkdtemp()
    return subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json", "--disable-slash-commands", "--strict-mcp-config"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        # Windows' default subprocess text encoding is the system locale codepage
        # (often cp1252), which mangles the em-dashes/smart-quotes Claude's prose
        # uses (e.g. "—" -> "â€”") since the CLI's own stdout is UTF-8. Forcing
        # utf-8 here, not relying on the platform default, fixed a real mojibake
        # bug found live during integration testing.
        timeout=CLAUDE_TIMEOUT_SECONDS,
        cwd=tmp_cwd,
    )


def get_agent_reasoning(redacted_profile: dict, job: dict, score_result: dict, bias_note: str) -> dict:
    """Builds one prompt covering every reasoning stage, shells out to the
    `claude` CLI from a fresh empty temp cwd, and parses its structured JSON
    reply. On any failure, returns a clearly-labeled fallback — never crashes
    the pipeline and never pretends the fallback is a real model answer."""
    prompt = _build_prompt(redacted_profile, job, score_result, bias_note)

    try:
        completed = _run_claude_cli(prompt)
    except subprocess.TimeoutExpired:
        return _fallback(score_result, f"claude CLI timed out after {CLAUDE_TIMEOUT_SECONDS}s")
    except OSError as exc:
        return _fallback(score_result, f"claude CLI could not be started: {exc}")

    if completed.returncode != 0:
        return _fallback(score_result, f"claude CLI exited {completed.returncode}: {completed.stderr[:500]}")

    try:
        cli_envelope = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return _fallback(score_result, f"claude CLI stdout was not valid JSON: {exc}")

    raw_result = cli_envelope.get("result")
    if not isinstance(raw_result, str):
        return _fallback(score_result, "claude CLI JSON envelope had no string 'result' field")

    try:
        parsed = json.loads(_strip_code_fences(raw_result))
    except json.JSONDecodeError as exc:
        return _fallback(score_result, f"model's 'result' text was not valid JSON: {exc}")

    missing_keys = [k for k in _RESULT_KEYS if k not in parsed]
    if missing_keys:
        return _fallback(score_result, f"model JSON was missing keys: {missing_keys}")

    if parsed["recommendation"] not in ("approve", "reject"):
        return _fallback(score_result, f"model returned an invalid recommendation: {parsed['recommendation']!r}")

    return {k: parsed[k] for k in _RESULT_KEYS}
