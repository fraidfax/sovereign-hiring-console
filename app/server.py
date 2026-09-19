"""Sovereign Hiring Console — stdlib HTTP server.

Thin integration layer: routes HTTP requests to app.redaction / app.scoring /
app.audit and serves the static recruiter console. No third-party
dependencies, no outbound network calls — everything the process needs lives
on local disk under app/data and app/static (see SPEC.md).

Importing this module has no side effects (no file reads, no server start):
`load_state()` and `httpd.serve_forever()` only run under `__main__`, so the
module stays safe to import from a test runner or another script.
"""
import argparse
import json
import mimetypes
import posixpath
import sys
import threading
import traceback
import urllib.parse
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
JOB_PATH = DATA_DIR / "job.json"
CANDIDATES_PATH = DATA_DIR / "candidates.json"
DECISIONS_PATH = DATA_DIR / "decisions.json"

# POST /api/decide only ever needs a handful of short string fields; a real
# cap avoids letting a bogus Content-Length force a large read() allocation.
MAX_BODY_BYTES = 64 * 1024

# This app has no inline <script>/<style> and loads nothing external (see
# app/static/*), so a strict same-origin CSP costs nothing and blocks a whole
# class of injection if `textContent`-only rendering (see app.js) is ever
# broken by a future edit. Defense in depth for the local demo; the sovereign
# Azure target in docs/architecture.md adds real network/auth controls on top.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # img-src allows data: for the inline SVG favicon only; everything else
    # (scripts, styles, fetch targets) stays same-origin only.
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:",
}

# `server.py` can be launched either as `py -3 -m app.server` (repo root on
# sys.path, package import works as-is) or as `py -3 app/server.py` (only
# app/ itself lands on sys.path). Support both without guessing which one the
# final README picks.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
try:
    from app import redaction, scoring, audit
except ImportError:
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))
    import redaction
    import scoring
    import audit

_lock = threading.Lock()


class State:
    """Mutable process state, populated once by load_state()."""

    def __init__(self):
        self.job = {}
        self.candidates_by_id = {}  # id -> raw candidate dict, PII included, server-only
        self.ranked = []  # computed public records, sorted score desc
        self.top3_ids = set()
        self.decisions = {}  # id -> {decision_status, decision_reason, decision_actor}
        self.logged_ai_rec_ids = set()


STATE = State()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    # ponytail: atomic replace so a crash mid-write can't corrupt
    # decisions.json; ceiling is a single-writer flat file, fine at ~14
    # candidates — upgrade to a real store if this ever needs concurrent writers.
    tmp.replace(path)


def load_state() -> State:
    """Reads job.json/candidates.json once and computes every candidate's
    redaction + score. Safe to call again (e.g. from a test or a REPL) —
    it just recomputes from disk and resets the ai_recommendation log guard."""
    job = _read_json(JOB_PATH, {})
    candidates = _read_json(CANDIDATES_PATH, [])

    ranked = []
    for candidate in candidates:
        redaction_result = redaction.redact_candidate(candidate)
        redacted_profile = redaction_result["redacted"]
        score_result = scoring.score_candidate(redacted_profile, job)
        ranked.append({
            "id": candidate["id"],
            "redacted_profile": redacted_profile,
            "removed_fields": redaction_result["removed_fields"],
            "scrubbed_spans": redaction_result["scrubbed_spans"],
            "score": score_result["score"],
            "explanation": score_result["explanation"],
            "matched_must_haves": score_result["matched_must_haves"],
            "missing_must_haves": score_result["missing_must_haves"],
            "matched_nice_to_haves": score_result["matched_nice_to_haves"],
        })
    ranked.sort(key=lambda r: r["score"], reverse=True)

    STATE.job = job
    STATE.candidates_by_id = {c["id"]: c for c in candidates}
    STATE.ranked = ranked
    STATE.top3_ids = {r["id"] for r in ranked[:3]}
    STATE.decisions = _read_json(DECISIONS_PATH, {})
    STATE.logged_ai_rec_ids = set()
    return STATE


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decision_fields(candidate_id: str) -> dict:
    d = STATE.decisions.get(candidate_id, {})
    return {
        "decision_status": d.get("decision_status", "pending"),
        "decision_reason": d.get("decision_reason"),
        "decision_actor": d.get("decision_actor"),
    }


def _candidate_record(ranked_entry: dict) -> dict:
    record = dict(ranked_entry)
    record.update(_decision_fields(ranked_entry["id"]))
    return record


def _log_ai_recommendations_once() -> None:
    with _lock:
        pending = [
            (rank, r) for rank, r in enumerate(STATE.ranked, start=1)
            if r["id"] not in STATE.logged_ai_rec_ids
        ]
        for rank, r in pending:
            audit.log_event("ai_recommendation", {
                "candidate_id": r["id"],
                "rank": rank,
                "score": r["score"],
                "matched_must_haves": r["matched_must_haves"],
                "missing_must_haves": r["missing_must_haves"],
                "matched_nice_to_haves": r["matched_nice_to_haves"],
                "explanation": r["explanation"],
            }, _now_iso())
            STATE.logged_ai_rec_ids.add(r["id"])


class Handler(BaseHTTPRequestHandler):
    # -- routing -------------------------------------------------------
    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        try:
            if path == "/":
                self._serve_static("index.html")
            elif path.startswith("/static/"):
                self._serve_static(path[len("/static/"):])
            elif path == "/api/job":
                self._send_json(HTTPStatus.OK, STATE.job)
            elif path == "/api/candidates":
                self._get_candidates()
            elif path == "/api/bias-check":
                self._get_bias_check()
            elif path == "/api/audit-log":
                self._send_json(HTTPStatus.OK, list(reversed(audit.read_audit_log())))
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "not found")
        except Exception:
            traceback.print_exc()
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal server error")

    def do_POST(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        try:
            if path == "/api/decide":
                self._post_decide()
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "not found")
        except Exception:
            traceback.print_exc()
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal server error")

    # -- GET handlers ----------------------------------------------------
    def _get_candidates(self) -> None:
        _log_ai_recommendations_once()
        self._send_json(HTTPStatus.OK, [_candidate_record(r) for r in STATE.ranked])

    def _get_bias_check(self) -> None:
        candidates_with_scores = [{"id": r["id"], "score": r["score"]} for r in STATE.ranked]
        self._send_json(HTTPStatus.OK, audit.bias_check(candidates_with_scores, STATE.candidates_by_id))

    def _serve_static(self, rel_path: str) -> None:
        rel_path = urllib.parse.unquote(rel_path)
        safe_rel = posixpath.normpath("/" + rel_path).lstrip("/")
        static_root = STATIC_DIR.resolve()
        file_path = (static_root / safe_rel).resolve()
        try:
            file_path.relative_to(static_root)
        except ValueError:
            return self._send_error(HTTPStatus.NOT_FOUND, "not found")
        if not file_path.is_file():
            return self._send_error(HTTPStatus.NOT_FOUND, "not found")

        content_type, _ = mimetypes.guess_type(str(file_path))
        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(data)

    # -- POST handlers ---------------------------------------------------
    def _post_decide(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length < 0 or length > MAX_BODY_BYTES:
            return self._send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body too large")
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return self._send_error(HTTPStatus.BAD_REQUEST, "invalid JSON body")
        if not isinstance(body, dict):
            return self._send_error(HTTPStatus.BAD_REQUEST, "body must be a JSON object")

        candidate_id = body.get("candidate_id")
        decision = body.get("decision")
        actor = body.get("actor")
        reason = body.get("reason")

        if not isinstance(candidate_id, str) or not candidate_id:
            return self._send_error(HTTPStatus.BAD_REQUEST, "candidate_id is required")
        if candidate_id not in STATE.candidates_by_id:
            return self._send_error(HTTPStatus.BAD_REQUEST, "unknown candidate_id")
        if decision not in ("approve", "reject"):
            return self._send_error(HTTPStatus.BAD_REQUEST, "decision must be 'approve' or 'reject'")
        if not isinstance(actor, str) or not actor.strip():
            return self._send_error(HTTPStatus.BAD_REQUEST, "actor is required")

        is_override = decision == "reject" and candidate_id in STATE.top3_ids
        reason_ok = isinstance(reason, str) and bool(reason.strip())
        if is_override and not reason_ok:
            return self._send_error(
                HTTPStatus.BAD_REQUEST,
                "reason is required to reject a top-3 (override) candidate",
            )

        actor = actor.strip()
        reason_value = reason.strip() if reason_ok else None
        decision_status = "approved" if decision == "approve" else "rejected"

        ranked_entry = next((r for r in STATE.ranked if r["id"] == candidate_id), None)
        if ranked_entry is None:
            # STATE.ranked and STATE.candidates_by_id are built together in
            # load_state() and must stay in lockstep; reaching here means that
            # invariant broke, which is a bug worth a loud, specific failure
            # rather than a generic StopIteration further down.
            return self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal server error")

        decision_record = {
            "decision_status": decision_status,
            "decision_reason": reason_value,
            "decision_actor": actor,
        }
        with _lock:
            # All-or-nothing: write the new decisions.json, then the audit
            # log entry, and only then update in-memory STATE. If the audit
            # write fails, roll decisions.json back to its previous content
            # before re-raising, so a 500 never leaves disk state, audit log,
            # and in-memory state disagreeing about whether this decision
            # actually happened.
            previous_decisions = STATE.decisions
            pending_decisions = {**previous_decisions, candidate_id: decision_record}
            _write_json(DECISIONS_PATH, pending_decisions)
            try:
                audit.log_event("human_decision", {
                    "candidate_id": candidate_id,
                    "decision": decision,
                    "actor": actor,
                    "reason": reason_value,
                    "override": is_override,
                    "score": ranked_entry["score"],
                }, _now_iso())
            except Exception:
                _write_json(DECISIONS_PATH, previous_decisions)
                raise
            STATE.decisions = pending_decisions

        self._send_json(HTTPStatus.OK, _candidate_record(ranked_entry))

    # -- response helpers --------------------------------------------------
    def _send_security_headers(self) -> None:
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)

    def _send_json(self, status: HTTPStatus, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json(status, {"error": message})


def build_server(host: str, port: int) -> ThreadingHTTPServer:
    load_state()
    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sovereign Hiring Console server")
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="bind address (default 127.0.0.1; pass 0.0.0.0 to let other devices on "
             "your network reach it — there is no auth on this demo server)",
    )
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    httpd = build_server(args.host, args.port)
    print(f"Sovereign Hiring Console listening on http://{args.host}:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
