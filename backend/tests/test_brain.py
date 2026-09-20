import json
import subprocess
from unittest.mock import patch

from app import brain, tools

JOB = {"must_have_skills": ["Python"], "nice_to_have_skills": [], "min_years_experience": 2}

PII_CANDIDATE = {
    "id": "cand-99",
    "full_name": "Zara Al-Sayed",
    "email": "zara.alsayed@example.com",
    "phone": "+971-50-555-0134",
    "address": "Marina Walk, Dubai, UAE",
    "date_of_birth": "1990-01-01",
    "gender": "female",
    "nationality": "Emirati",
    "photo_placeholder": "avatar-ZA-99",
    "years_experience": 6,
    "skills": ["Python"],
    "education": "BSc, Zara Al-Sayed studied at AUS",
    "work_history": "Zara led a team.",
    "cover_letter_excerpt": "I'm excited to apply.",
}


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["claude"], returncode=returncode, stdout=stdout, stderr="")


def _cli_envelope(result_text: str) -> str:
    return json.dumps({"result": result_text})


def _valid_model_json():
    return {
        "redaction_note": "PII removed cleanly, text reads naturally.",
        "score_note": "Strong match on required skills.",
        "bias_note": "No concerning spread across groups.",
        "recommendation": "approve",
        "recommendation_reasoning": "Meets requirements. Good fit. Recommend advancing.",
    }


def test_happy_path_parses_correctly():
    redacted = tools.redact_pii(PII_CANDIDATE)["redacted"]
    score_result = tools.score_candidate(redacted, JOB)
    model_json = _valid_model_json()

    with patch.object(brain, "subprocess") as mock_subprocess:
        mock_subprocess.run.return_value = _completed(_cli_envelope(json.dumps(model_json)))
        mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired
        result = brain.get_agent_reasoning(redacted, JOB, score_result, "no spread")

    assert result == model_json


def test_cli_timeout_falls_back_cleanly():
    redacted = tools.redact_pii(PII_CANDIDATE)["redacted"]
    score_result = tools.score_candidate(redacted, JOB)

    with patch.object(brain, "subprocess") as mock_subprocess:
        mock_subprocess.run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=45)
        mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired
        result = brain.get_agent_reasoning(redacted, JOB, score_result, "no spread")

    assert result["recommendation"] in ("approve", "reject")
    assert "fallback" in result["recommendation_reasoning"].lower()


def test_cli_malformed_json_falls_back_cleanly():
    redacted = tools.redact_pii(PII_CANDIDATE)["redacted"]
    score_result = tools.score_candidate(redacted, JOB)

    with patch.object(brain, "subprocess") as mock_subprocess:
        mock_subprocess.run.return_value = _completed(_cli_envelope("not valid json {{{"))
        mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired
        result = brain.get_agent_reasoning(redacted, JOB, score_result, "no spread")

    assert result["recommendation"] in ("approve", "reject")
    assert "fallback" in result["recommendation_reasoning"].lower()


def test_cli_nonzero_exit_falls_back_cleanly():
    redacted = tools.redact_pii(PII_CANDIDATE)["redacted"]
    score_result = tools.score_candidate(redacted, JOB)

    with patch.object(brain, "subprocess") as mock_subprocess:
        mock_subprocess.run.return_value = _completed("", returncode=1)
        mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired
        result = brain.get_agent_reasoning(redacted, JOB, score_result, "no spread")

    assert result["recommendation"] in ("approve", "reject")
    assert "fallback" in result["recommendation_reasoning"].lower()


def test_model_json_wrapped_in_code_fences_is_parsed():
    redacted = tools.redact_pii(PII_CANDIDATE)["redacted"]
    score_result = tools.score_candidate(redacted, JOB)
    model_json = _valid_model_json()
    fenced = "```json\n" + json.dumps(model_json) + "\n```"

    with patch.object(brain, "subprocess") as mock_subprocess:
        mock_subprocess.run.return_value = _completed(_cli_envelope(fenced))
        mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired
        result = brain.get_agent_reasoning(redacted, JOB, score_result, "no spread")

    assert result == model_json


def test_prompt_never_contains_raw_pii_field_names_or_values():
    """Automated proof of the sovereignty claim: the literal prompt string
    handed to the subprocess must never contain any raw PII value from the
    fixture candidate."""
    redacted = tools.redact_pii(PII_CANDIDATE)["redacted"]
    score_result = tools.score_candidate(redacted, JOB)
    model_json = _valid_model_json()

    with patch.object(brain, "subprocess") as mock_subprocess:
        mock_subprocess.run.return_value = _completed(_cli_envelope(json.dumps(model_json)))
        mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired
        brain.get_agent_reasoning(redacted, JOB, score_result, "no spread")

        assert mock_subprocess.run.called
        call_args = mock_subprocess.run.call_args
        prompt_arg = call_args.args[0][2]  # ["claude", "-p", prompt, ...]

    raw_pii_values = [
        PII_CANDIDATE["full_name"], PII_CANDIDATE["email"], PII_CANDIDATE["phone"],
        PII_CANDIDATE["address"], PII_CANDIDATE["date_of_birth"], PII_CANDIDATE["gender"],
        PII_CANDIDATE["nationality"], PII_CANDIDATE["photo_placeholder"],
        "Zara", "Al-Sayed",
    ]
    for value in raw_pii_values:
        assert value not in prompt_arg, f"raw PII value {value!r} leaked into the Claude prompt"

    for field_name in tools.PII_FIELDS:
        assert f'"{field_name}"' not in prompt_arg


def test_pii_leak_in_redacted_profile_raises_before_calling_claude():
    """Defense-in-depth: even if a caller's redaction was buggy, brain.py
    refuses to build a prompt containing a PII field key at all."""
    leaked_profile = {"id": "cand-01", "full_name": "Should Not Be Here", "skills": ["Python"]}
    score_result = {"score": 80.0}

    with patch.object(brain, "subprocess") as mock_subprocess:
        try:
            brain.get_agent_reasoning(leaked_profile, JOB, score_result, "no spread")
            assert False, "expected ValueError to be raised"
        except ValueError:
            pass
        mock_subprocess.run.assert_not_called()
