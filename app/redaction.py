"""PII stripper and free-text scrubber for candidate records.

Contract: see SPEC.md -> `app/redaction.py` -> `redact_candidate()`.
Stdlib only (re, typing).
"""

import re
from typing import Any, Dict, List, Optional, Pattern

# Fields removed wholesale from the redacted candidate dict.
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

# Free-text fields that get a second-pass regex scrub.
FREE_TEXT_FIELDS = ("work_history", "cover_letter_excerpt", "education")

REPLACEMENT = "[REDACTED]"

_PRONOUNS = ("he", "him", "his", "she", "her", "they", "them", "their")
_PRONOUN_RE = re.compile(r"\b(?:" + "|".join(_PRONOUNS) + r")\b", re.IGNORECASE)

# Standalone age mentions: "32 years old", "29-year-old", "aged 29", "I'm 34",
# "I am 34". [\s-]+ (rather than \s+) so hyphenated phrasing is caught too.
_AGE_RE = re.compile(
    r"\b\d{1,3}[\s-]+years?[\s-]+old\b"
    r"|\baged\s+\d{1,3}\b"
    # [''’]? (not a bare ') so both a straight apostrophe and the curly
    # ’ that most phone/OS keyboards auto-substitute for "I'm" are caught.
    r"|\bI\s*(?:['’]m|\s+am)\s+\d{1,3}\b",
    re.IGNORECASE,
)


def _name_pattern(full_name: Any) -> Optional[Pattern]:
    """Whole-word, case-insensitive pattern matching any part of full_name,
    including each side of a hyphenated name segment (e.g. "Al-Sayed" yields
    "Al-Sayed", "Al", and "Sayed" as separate matchable parts, so a later bare
    mention of just one half still gets caught)."""
    if not isinstance(full_name, str):
        return None
    tokens = [p for p in re.split(r"\s+", full_name.strip()) if p]
    if not tokens:
        return None
    parts = set(tokens)
    for token in tokens:
        parts.update(p for p in token.split("-") if p)
    # Longest first so a part that is a substring of another can't shadow it
    # (harmless with \b boundaries, but keeps intent obvious).
    ordered = sorted(parts, key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(re.escape(p) for p in ordered) + r")\b", re.IGNORECASE)


def _scrub(pattern: Pattern, text: str, field: str, spans: List[Dict[str, str]]) -> str:
    def _replace(match: "re.Match") -> str:
        spans.append({"field": field, "original": match.group(0), "replacement": REPLACEMENT})
        return REPLACEMENT

    return pattern.sub(_replace, text)


def redact_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Strip PII fields and scrub free text for name/age/pronoun mentions.

    Returns {"redacted": {...}, "removed_fields": [...], "scrubbed_spans": [...]}.
    """
    redacted: Dict[str, Any] = {k: v for k, v in candidate.items() if k not in PII_FIELDS}
    removed_fields = [f for f in PII_FIELDS if f in candidate]
    scrubbed_spans: List[Dict[str, str]] = []

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
