import unittest

from app.redaction import PII_FIELDS, redact_candidate


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
        "skills": ["python", "sql"],
        "education": "BSc Computer Science",
        "work_history": "Jamie Rivera led backend projects; she shipped three releases on time.",
        "cover_letter_excerpt": "I'm 34 and aged 29 mentally; they said Rivera was reliable.",
    }
    base.update(overrides)
    return base


class TestRedactCandidate(unittest.TestCase):
    def test_pii_fields_fully_removed(self):
        result = redact_candidate(_candidate())
        redacted = result["redacted"]
        for field in PII_FIELDS:
            self.assertNotIn(field, redacted)
        # non-PII fields survive
        self.assertEqual(redacted["id"], "cand-01")
        self.assertEqual(redacted["years_experience"], 5)

    def test_name_mention_in_free_text_is_scrubbed(self):
        result = redact_candidate(_candidate())
        redacted = result["redacted"]
        for field in ("work_history", "cover_letter_excerpt"):
            self.assertNotRegex(redacted[field], r"\bJamie\b")
            self.assertNotRegex(redacted[field], r"\bRivera\b")
        self.assertIn("[REDACTED]", redacted["work_history"])
        name_spans = [s["original"] for s in result["scrubbed_spans"] if s["original"] in ("Jamie", "Rivera")]
        self.assertTrue(name_spans, "expected at least one name span to be recorded")

    def test_age_mention_is_scrubbed(self):
        result = redact_candidate(_candidate())
        redacted = result["redacted"]
        self.assertNotRegex(redacted["cover_letter_excerpt"], r"\b34\b")
        self.assertNotRegex(redacted["cover_letter_excerpt"], r"\baged 29\b")
        age_spans = [
            s for s in result["scrubbed_spans"]
            if s["field"] == "cover_letter_excerpt" and any(c.isdigit() for c in s["original"])
        ]
        self.assertTrue(age_spans, "expected at least one age span to be recorded")

    def test_pronoun_is_scrubbed(self):
        result = redact_candidate(_candidate())
        redacted = result["redacted"]
        self.assertNotRegex(redacted["work_history"], r"\bshe\b", )
        self.assertNotRegex(redacted["cover_letter_excerpt"], r"\bthey\b")
        pronoun_spans = [
            s["original"].lower() for s in result["scrubbed_spans"]
            if s["original"].lower() in ("he", "him", "his", "she", "her", "they", "them", "their")
        ]
        self.assertTrue(pronoun_spans, "expected at least one pronoun span to be recorded")

    def test_no_free_text_leakage_still_reports_removed_fields(self):
        clean = _candidate(
            work_history="Built distributed systems and mentored junior engineers on call rotations.",
            cover_letter_excerpt="Excited about the mission and the team's engineering culture.",
        )
        result = redact_candidate(clean)
        self.assertEqual(result["scrubbed_spans"], [])
        self.assertTrue(result["removed_fields"])
        self.assertEqual(set(result["removed_fields"]), set(PII_FIELDS))


if __name__ == "__main__":
    unittest.main()
