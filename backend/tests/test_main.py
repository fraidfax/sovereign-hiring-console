"""Smoke tests for the FastAPI wiring layer: routes, validation, headers.

Never lets a real orchestrator run start (which would shell out to the real
`claude` CLI) — /api/run-agent is tested with orchestrator.run_agent
monkeypatched to a no-op.
"""

import pytest
from fastapi.testclient import TestClient

from app import orchestrator, store, tools
from app.main import app


@pytest.fixture(autouse=True)
def reset_store():
    store.load_seed_data()
    yield
    store.load_seed_data()


@pytest.fixture(autouse=True)
def isolate_audit_log(tmp_path, monkeypatch):
    # Keep tests from writing into the real backend/app/data/audit_log.jsonl.
    monkeypatch.setattr(tools, "AUDIT_LOG_PATH", str(tmp_path / "audit_log.jsonl"))


def test_get_job_returns_seed_job():
    with TestClient(app) as client:
        response = client.get("/api/job")
    assert response.status_code == 200
    assert response.json()["id"] == store.JOB["id"]


def test_get_candidates_returns_all_not_started_initially():
    with TestClient(app) as client:
        response = client.get("/api/candidates")
    body = response.json()
    assert len(body) == len(store.ORIGINAL_ORDER)
    assert all(c["status"] == "not_started" for c in body)


def test_security_headers_present_on_every_response():
    with TestClient(app) as client:
        response = client.get("/api/job")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_data_residency_shape():
    with TestClient(app) as client:
        response = client.get("/api/data-residency")
    body = response.json()
    assert body["pii_external_requests_total"] == 0
    assert body["external_services"][0]["receives_pii"] is False


def test_run_agent_route_starts_background_task_when_idle(monkeypatch):
    async def fake_run_agent():
        return None

    monkeypatch.setattr(orchestrator, "run_agent", fake_run_agent)
    with TestClient(app) as client:
        response = client.post("/api/run-agent")
    assert response.status_code == 202
    assert response.json() == {"status": "started"}


def test_run_agent_route_reports_already_running(monkeypatch):
    with TestClient(app) as client:
        # Set after entering: TestClient.__enter__ runs the app's lifespan
        # startup, which calls store.load_seed_data() and would otherwise
        # reset this flag back to False before the request is made.
        store.AGENT_RUNNING = True
        response = client.post("/api/run-agent")
    assert response.json() == {"status": "already_running"}


# --- /api/decide -----------------------------------------------------------

def test_decide_rejects_unknown_candidate():
    with TestClient(app) as client:
        response = client.post("/api/decide", json={"candidate_id": "nope", "decision": "approve", "actor": "HR"})
    assert response.status_code == 400
    assert "error" in response.json()


def test_decide_rejects_missing_actor():
    candidate_id = store.ORIGINAL_ORDER[0]
    with TestClient(app) as client:
        response = client.post("/api/decide", json={"candidate_id": candidate_id, "decision": "approve", "actor": ""})
    assert response.status_code == 400


def test_decide_rejects_invalid_decision_value():
    candidate_id = store.ORIGINAL_ORDER[0]
    with TestClient(app) as client:
        response = client.post("/api/decide", json={"candidate_id": candidate_id, "decision": "maybe", "actor": "HR"})
    assert response.status_code == 400


def test_decide_rejects_candidate_with_no_pending_recommendation():
    candidate_id = store.ORIGINAL_ORDER[0]  # still "not_started"
    with TestClient(app) as client:
        response = client.post("/api/decide", json={"candidate_id": candidate_id, "decision": "approve", "actor": "HR"})
    assert response.status_code == 400


def test_decide_accepting_the_recommendation_needs_no_reason():
    candidate_id = store.ORIGINAL_ORDER[0]

    with TestClient(app) as client:
        # Set after entering (see note in the already-running test above).
        store.PUBLIC[candidate_id]["status"] = "pending_review"
        store.PUBLIC[candidate_id]["recommendation"] = "approve"
        response = client.post("/api/decide", json={"candidate_id": candidate_id, "decision": "approve", "actor": "HR Lead"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["is_override"] is False
    assert body["decision_actor"] == "HR Lead"


def test_decide_overriding_the_recommendation_requires_a_reason():
    candidate_id = store.ORIGINAL_ORDER[0]

    with TestClient(app) as client:
        store.PUBLIC[candidate_id]["status"] = "pending_review"
        store.PUBLIC[candidate_id]["recommendation"] = "approve"
        no_reason = client.post("/api/decide", json={"candidate_id": candidate_id, "decision": "reject", "actor": "HR Lead"})
        assert no_reason.status_code == 400

        with_reason = client.post("/api/decide", json={
            "candidate_id": candidate_id, "decision": "reject", "actor": "HR Lead", "reason": "Interview raised concerns.",
        })

    assert with_reason.status_code == 200
    body = with_reason.json()
    assert body["status"] == "rejected"
    assert body["is_override"] is True
    assert body["decision_reason"] == "Interview raised concerns."


def test_audit_log_is_newest_first():
    tools.log_to_audit("human_decision", {"n": 1}, "2026-01-01T00:00:00Z")
    tools.log_to_audit("human_decision", {"n": 2}, "2026-01-01T00:00:01Z")

    with TestClient(app) as client:
        response = client.get("/api/audit-log")

    body = response.json()
    assert body[0]["n"] == 2
    assert body[1]["n"] == 1
