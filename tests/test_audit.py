"""Tests for app/audit.py: log_event, read_audit_log, bias_check."""

import json
import os
import tempfile
import unittest

from app import audit


class AuditLogTempPathMixin:
    """Points audit.AUDIT_LOG_PATH at a fresh tempdir per test, so tests never
    touch the real app/data/audit_log.jsonl."""

    def setUp(self):
        self._orig_path = audit.AUDIT_LOG_PATH
        self._tmpdir = tempfile.TemporaryDirectory()
        audit.AUDIT_LOG_PATH = os.path.join(self._tmpdir.name, "audit_log.jsonl")

    def tearDown(self):
        audit.AUDIT_LOG_PATH = self._orig_path
        self._tmpdir.cleanup()


class TestLogEvent(AuditLogTempPathMixin, unittest.TestCase):
    def test_appends_and_returns_record(self):
        # Act
        record = audit.log_event(
            "ai_recommendation", {"candidate_id": "cand-01", "score": 82.5}, "2026-09-20T10:00:00Z"
        )

        # Assert: return value
        self.assertEqual(
            record,
            {
                "ts": "2026-09-20T10:00:00Z",
                "event": "ai_recommendation",
                "candidate_id": "cand-01",
                "score": 82.5,
            },
        )

        # Assert: on-disk line matches
        with open(audit.AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), record)

    def test_creates_file_and_parent_dir_when_absent(self):
        # Arrange: point at a path whose directory doesn't exist yet
        nested = os.path.join(self._tmpdir.name, "nested", "audit_log.jsonl")
        audit.AUDIT_LOG_PATH = nested
        self.assertFalse(os.path.exists(nested))

        # Act
        audit.log_event("human_decision", {"candidate_id": "cand-02"}, "2026-09-20T10:05:00Z")

        # Assert
        self.assertTrue(os.path.exists(nested))

    def test_second_call_appends_not_overwrites(self):
        # Act
        audit.log_event("ai_recommendation", {"candidate_id": "cand-01"}, "2026-09-20T10:00:00Z")
        audit.log_event("human_decision", {"candidate_id": "cand-01"}, "2026-09-20T10:01:00Z")

        # Assert
        with open(audit.AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 2)


class TestReadAuditLog(AuditLogTempPathMixin, unittest.TestCase):
    def test_returns_empty_list_when_file_absent(self):
        # Arrange: AUDIT_LOG_PATH points into a real (empty) tempdir but the
        # file itself was never created.
        self.assertFalse(os.path.exists(audit.AUDIT_LOG_PATH))

        # Act / Assert
        self.assertEqual(audit.read_audit_log(), [])

    def test_returns_records_in_file_order(self):
        # Arrange
        audit.log_event("ai_recommendation", {"candidate_id": "cand-01"}, "2026-09-20T10:00:00Z")
        audit.log_event("ai_recommendation", {"candidate_id": "cand-02"}, "2026-09-20T10:00:01Z")
        audit.log_event("human_decision", {"candidate_id": "cand-01"}, "2026-09-20T10:05:00Z")

        # Act
        records = audit.read_audit_log()

        # Assert: oldest first, exact file order preserved
        self.assertEqual(
            [r["ts"] for r in records],
            ["2026-09-20T10:00:00Z", "2026-09-20T10:00:01Z", "2026-09-20T10:05:00Z"],
        )
        self.assertEqual(
            [r["candidate_id"] for r in records], ["cand-01", "cand-02", "cand-01"]
        )


class TestBiasCheck(unittest.TestCase):
    def test_computes_per_group_averages_and_max_spread(self):
        # Arrange: synthetic input, two groups of 3 (>= MIN_GROUP_SIZE) with
        # distinct known averages
        candidates_with_scores = [
            {"id": "cand-01", "score": 80.0},
            {"id": "cand-02", "score": 90.0},
            {"id": "cand-03", "score": 70.0},
            {"id": "cand-04", "score": 50.0},
            {"id": "cand-05", "score": 60.0},
            {"id": "cand-06", "score": 40.0},
        ]
        unredacted_by_id = {
            "cand-01": {"gender": "female"},
            "cand-02": {"gender": "female"},
            "cand-03": {"gender": "female"},
            "cand-04": {"gender": "male"},
            "cand-05": {"gender": "male"},
            "cand-06": {"gender": "male"},
        }

        # Act
        result = audit.bias_check(candidates_with_scores, unredacted_by_id)

        # Assert
        self.assertEqual(
            result["groups"],
            {
                "female": {"n": 3, "avg_score": 80.0},
                "male": {"n": 3, "avg_score": 50.0},
            },
        )
        self.assertEqual(result["max_spread"], 30.0)
        self.assertIsInstance(result["statement"], str)
        self.assertIn("30.0", result["statement"])

    def test_single_group_has_zero_spread_and_no_crash(self):
        # Arrange
        candidates_with_scores = [{"id": "cand-01", "score": 70.0}]
        unredacted_by_id = {"cand-01": {"gender": "undisclosed"}}

        # Act
        result = audit.bias_check(candidates_with_scores, unredacted_by_id)

        # Assert
        self.assertEqual(result["max_spread"], 0.0)
        self.assertNotIn("undisclosed", result["groups"])
        self.assertEqual(result["groups"][audit.SUPPRESSED_LABEL]["n"], 1)
        self.assertIsNone(result["groups"][audit.SUPPRESSED_LABEL]["avg_score"])

    def test_groups_below_minimum_size_never_expose_an_individual_score(self):
        # Arrange: two singleton groups, the exact CRITICAL-severity scenario
        # this suppression exists to prevent (an n=1 group's avg_score IS a
        # specific candidate's exact score, re-identifying their gender).
        candidates_with_scores = [
            {"id": "cand-08", "score": 70.0},
            {"id": "cand-09", "score": 63.3},
        ]
        unredacted_by_id = {
            "cand-08": {"gender": "non_binary"},
            "cand-09": {"gender": "undisclosed"},
        }

        # Act
        result = audit.bias_check(candidates_with_scores, unredacted_by_id)

        # Assert: neither original small group label appears, and the
        # combined bucket withholds avg_score entirely
        self.assertNotIn("non_binary", result["groups"])
        self.assertNotIn("undisclosed", result["groups"])
        suppressed = result["groups"][audit.SUPPRESSED_LABEL]
        self.assertEqual(suppressed["n"], 2)
        self.assertIsNone(suppressed["avg_score"])
        self.assertIn("re-identif", result["statement"])

    def test_large_groups_reported_normally_alongside_a_suppressed_bucket(self):
        # Arrange: mirrors the shape of the real app/data/candidates.json —
        # two groups of 3+ and one singleton group
        candidates_with_scores = [
            {"id": f"cand-{i}", "score": s}
            for i, s in enumerate([80.0, 82.0, 78.0, 60.0, 62.0, 58.0, 90.0], start=1)
        ]
        unredacted_by_id = {
            "cand-1": {"gender": "female"},
            "cand-2": {"gender": "female"},
            "cand-3": {"gender": "female"},
            "cand-4": {"gender": "male"},
            "cand-5": {"gender": "male"},
            "cand-6": {"gender": "male"},
            "cand-7": {"gender": "non_binary"},
        }

        # Act
        result = audit.bias_check(candidates_with_scores, unredacted_by_id)

        # Assert: reportable groups keep their real averages; the singleton
        # is suppressed rather than dropped silently (n is still accounted for)
        self.assertEqual(result["groups"]["female"], {"n": 3, "avg_score": 80.0})
        self.assertEqual(result["groups"]["male"], {"n": 3, "avg_score": 60.0})
        self.assertNotIn("non_binary", result["groups"])
        self.assertEqual(result["groups"][audit.SUPPRESSED_LABEL]["n"], 1)
        self.assertEqual(result["max_spread"], 20.0)


if __name__ == "__main__":
    unittest.main()
