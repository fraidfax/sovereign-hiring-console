"""Sovereign Hiring Agent — FastAPI backend.

Run from inside backend/:
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app import orchestrator, store, tools

FRONTEND_ORIGIN = "http://localhost:3000"
# ponytail: a Content-Length check is the simplest correct guard against an
# oversized JSON body; it does not stop a chunked-encoding request that omits
# Content-Length. Upgrade path if that ever matters: an ASGI middleware that
# caps bytes read from the stream regardless of header.
MAX_DECIDE_BODY_BYTES = 8_192


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.load_seed_data()
    yield


app = FastAPI(title="Sovereign Hiring Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def security_headers_and_body_cap(request: Request, call_next):
    if request.url.path == "/api/decide" and request.method == "POST":
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > MAX_DECIDE_BODY_BYTES:
            return JSONResponse({"error": "request body too large"}, status_code=413)

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Log full detail server-side; never leak a stack trace to the client.
    print(f"[main] unhandled error on {request.method} {request.url.path}: {exc!r}")
    return JSONResponse({"error": "internal server error"}, status_code=500)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.get("/api/job")
async def get_job():
    return store.JOB


@app.get("/api/candidates")
async def get_candidates():
    return store.sorted_public_candidates()


@app.post("/api/run-agent", status_code=202)
async def run_agent_route():
    if store.AGENT_RUNNING:
        return JSONResponse({"status": "already_running"})
    asyncio.create_task(orchestrator.run_agent())
    return {"status": "started"}


@app.get("/api/agent-stream")
async def agent_stream():
    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()
        store.SUBSCRIBERS.append(queue)
        try:
            # Replay everything emitted so far so a reconnecting client (e.g.
            # a page refresh mid-demo) never loses events, then keep streaming.
            for event in list(store.EVENTS):
                yield f"data: {json.dumps(event)}\n\n"
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            store.SUBSCRIBERS.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/decide")
async def decide(request: Request):
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)

    candidate_id = body.get("candidate_id")
    decision = body.get("decision")
    actor = body.get("actor")
    reason = body.get("reason")

    if not candidate_id or candidate_id not in store.PUBLIC:
        return JSONResponse({"error": "unknown candidate_id"}, status_code=400)
    if decision not in ("approve", "reject"):
        return JSONResponse({"error": "decision must be 'approve' or 'reject'"}, status_code=400)
    if not actor or not isinstance(actor, str) or not actor.strip():
        return JSONResponse({"error": "actor is required"}, status_code=400)

    candidate = store.PUBLIC[candidate_id]
    if candidate["status"] != "pending_review":
        return JSONResponse({"error": "candidate has no pending recommendation to decide on"}, status_code=400)

    is_override = decision != candidate["recommendation"]
    if is_override and not (reason and isinstance(reason, str) and reason.strip()):
        return JSONResponse({"error": "reason is required when overriding the agent's recommendation"}, status_code=400)

    candidate["status"] = "approved" if decision == "approve" else "rejected"
    candidate["decision_actor"] = actor.strip()
    candidate["decision_reason"] = reason.strip() if reason else None
    candidate["is_override"] = is_override

    tools.log_to_audit("human_decision", {
        "candidate_id": candidate_id,
        "decision": candidate["status"],
        "actor": candidate["decision_actor"],
        "reason": candidate["decision_reason"],
        "is_override": is_override,
    }, _now_iso())

    return candidate


@app.get("/api/audit-log")
async def get_audit_log():
    return list(reversed(tools.read_audit_log()))


@app.get("/api/data-residency")
async def get_data_residency():
    return {
        "location": "This machine — localhost, no cloud deployment",
        "external_services": [
            {
                "name": "Claude (reasoning narration only)",
                "receives_pii": False,
                "note": (
                    "Only already-redacted profiles, scores, and aggregate bias statistics are "
                    "ever sent — never a name, email, phone, address, birth date, gender, "
                    "nationality, or photo."
                ),
            }
        ],
        "pii_external_requests_total": 0,
    }
