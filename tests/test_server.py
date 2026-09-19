"""Integration tests for app/server.py: starts a real server on an ephemeral
port and exercises it over real HTTP, per the code-reviewer's finding that
this file (all of the API's input validation) had zero automated coverage."""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from app import server


class ServerTestCase(unittest.TestCase):
    """Boots a real app.server instance against a private tempdir copy of the
    shipped job/candidates data, so tests never touch app/data/decisions.json
    or app/data/audit_log.jsonl."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp_data = Path(self._tmpdir.name)

        real_job = json.loads(server.JOB_PATH.read_text(encoding="utf-8"))
        real_candidates = json.loads(server.CANDIDATES_PATH.read_text(encoding="utf-8"))
        (tmp_data / "job.json").write_text(json.dumps(real_job), encoding="utf-8")
        (tmp_data / "candidates.json").write_text(json.dumps(real_candidates), encoding="utf-8")

        self._orig_job_path = server.JOB_PATH
        self._orig_candidates_path = server.CANDIDATES_PATH
        self._orig_decisions_path = server.DECISIONS_PATH
        self._orig_audit_path = server.audit.AUDIT_LOG_PATH
        server.JOB_PATH = tmp_data / "job.json"
        server.CANDIDATES_PATH = tmp_data / "candidates.json"
        server.DECISIONS_PATH = tmp_data / "decisions.json"
        server.audit.AUDIT_LOG_PATH = str(tmp_data / "audit_log.jsonl")

        self.httpd = server.build_server("127.0.0.1", 0)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        server.JOB_PATH = self._orig_job_path
        server.CANDIDATES_PATH = self._orig_candidates_path
        server.DECISIONS_PATH = self._orig_decisions_path
        server.audit.AUDIT_LOG_PATH = self._orig_audit_path
        self._tmpdir.cleanup()

    def _url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def _get(self, path):
        with urllib.request.urlopen(self._url(path)) as resp:
            return resp.status, json.loads(resp.read()), resp.headers

    def _post(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url(path), data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def _top3_candidate_id(self):
        _, candidates, _ = self._get("/api/candidates")
        return candidates[0]["id"]

    def _non_top3_candidate_id(self):
        _, candidates, _ = self._get("/api/candidates")
        return candidates[-1]["id"]

    # -- validation branches --------------------------------------------
    def test_decide_missing_actor_is_rejected(self):
        cand_id = self._non_top3_candidate_id()
        status, body = self._post("/api/decide", {"candidate_id": cand_id, "decision": "approve"})
        self.assertEqual(status, 400)
        self.assertIn("actor", body["error"])

    def test_decide_invalid_decision_value_is_rejected(self):
        cand_id = self._non_top3_candidate_id()
        status, body = self._post(
            "/api/decide", {"candidate_id": cand_id, "decision": "maybe", "actor": "Jane"}
        )
        self.assertEqual(status, 400)

    def test_decide_unknown_candidate_id_is_rejected(self):
        status, body = self._post(
            "/api/decide", {"candidate_id": "does-not-exist", "decision": "approve", "actor": "Jane"}
        )
        self.assertEqual(status, 400)
        self.assertIn("unknown", body["error"])

    def test_reject_top3_without_reason_is_rejected(self):
        cand_id = self._top3_candidate_id()
        status, body = self._post(
            "/api/decide", {"candidate_id": cand_id, "decision": "reject", "actor": "Jane"}
        )
        self.assertEqual(status, 400)
        self.assertIn("reason", body["error"])

    def test_reject_top3_with_reason_succeeds_and_persists(self):
        cand_id = self._top3_candidate_id()
        status, body = self._post(
            "/api/decide",
            {"candidate_id": cand_id, "decision": "reject", "actor": "Jane", "reason": "Panel decision."},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["decision_status"], "rejected")
        self.assertEqual(body["decision_reason"], "Panel decision.")

        # Re-fetching reflects the persisted decision, not just the response.
        _, candidates, _ = self._get("/api/candidates")
        updated = next(c for c in candidates if c["id"] == cand_id)
        self.assertEqual(updated["decision_status"], "rejected")

    def test_approve_non_top3_without_reason_succeeds(self):
        cand_id = self._non_top3_candidate_id()
        status, body = self._post(
            "/api/decide", {"candidate_id": cand_id, "decision": "approve", "actor": "Jane"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["decision_status"], "approved")

    # -- security headers -------------------------------------------------
    def test_json_responses_carry_security_headers(self):
        _, _, headers = self._get("/api/job")
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertIn("default-src 'self'", headers.get("Content-Security-Policy", ""))

    # -- the headline claim: PII never reaches the client -------------------
    def test_candidates_response_never_contains_pii_field_names_or_values(self):
        # This is the pitch's core claim ("show, not just claim, that PII
        # never reaches the scorer/client") checked at the actual HTTP
        # response boundary, not just against redact_candidate() in
        # isolation — a future edit that reintroduced a PII field into
        # _candidate_record()'s dict merge would be caught here.
        #
        # Note: the record legitimately NAMES stripped fields in
        # "removed_fields" (e.g. the string "full_name") to prove what was
        # removed — that's the feature, not a leak. What must never happen is
        # a PII field appearing as an actual KEY inside redacted_profile, or
        # any candidate's real PII VALUE appearing anywhere in the response.
        from app import redaction

        real_candidates = json.loads(server.CANDIDATES_PATH.read_text(encoding="utf-8"))
        _, body, _ = self._get("/api/candidates")
        raw_response = json.dumps(body)

        for record in body:
            profile_keys = set(record["redacted_profile"].keys())
            leaked_keys = profile_keys & set(redaction.PII_FIELDS)
            self.assertFalse(
                leaked_keys, f"candidate {record['id']}'s redacted_profile still has key(s) {leaked_keys}"
            )

        # gender/nationality are excluded here: they're short, common English
        # words ("Norwegian", "male") that can coincidentally appear in a
        # candidate's own legitimate, non-PII free text (e.g. "a Norwegian
        # energy provider" describing an employer) without that being a
        # redaction leak — unlike an email, phone number, address, or DOB,
        # which are specific enough that any appearance would be a real leak.
        unambiguous_pii_fields = [f for f in redaction.PII_FIELDS if f not in ("gender", "nationality")]
        for candidate in real_candidates:
            for field in unambiguous_pii_fields:
                value = candidate.get(field)
                if isinstance(value, str) and value:
                    self.assertNotIn(
                        value, raw_response,
                        f"candidate {candidate['id']}'s {field}={value!r} leaked into the API response",
                    )

    # -- bias-check never exposes a single-candidate score -----------------
    def test_bias_check_never_returns_a_group_smaller_than_three(self):
        _, bias, _ = self._get("/api/bias-check")
        for name, stats in bias["groups"].items():
            if name != server.audit.SUPPRESSED_LABEL:
                self.assertGreaterEqual(stats["n"], 3, f"group {name!r} leaks a small-n average")


if __name__ == "__main__":
    unittest.main()
