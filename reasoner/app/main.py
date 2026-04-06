"""LiveLogic Reasoner - FastAPI service."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .orchestrator import ReasoningOrchestrator, SessionStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LP_PATH = Path(__file__).resolve().parent.parent / "asp" / "security.lp"

app = FastAPI(title="LiveLogic Reasoner", version="0.1.0")
orchestrator = ReasoningOrchestrator(lp_path=str(LP_PATH))


class ReasonRequest(BaseModel):
    session_id: str
    transcript: str


class RetractRequest(BaseModel):
    session_id: str
    fact: str


class ReasonResponse(BaseModel):
    status: str
    response: str
    trace: list[dict[str, Any]]
    suggested_retraction: str = ""
    confidence: float = 0.0


@app.post("/reason", response_model=ReasonResponse)
async def reason(req: ReasonRequest) -> ReasonResponse:
    result = await orchestrator.reason(req.session_id, req.transcript)
    return ReasonResponse(
        status=result.status,
        response=result.response,
        trace=result.trace,
        suggested_retraction=result.suggested_retraction,
        confidence=result.confidence,
    )


@app.post("/retract", response_model=ReasonResponse)
async def retract(req: RetractRequest) -> ReasonResponse:
    result = await orchestrator.retract(req.session_id, req.fact)
    return ReasonResponse(
        status=result.status,
        response=result.response,
        trace=result.trace,
        suggested_retraction=result.suggested_retraction,
        confidence=result.confidence,
    )


@app.get("/trace/{session_id}")
async def get_trace(session_id: str) -> list[dict[str, Any]]:
    return orchestrator.store.get_traces(session_id)


@app.get("/sessions/{session_id}/state")
async def get_session_state(session_id: str) -> dict[str, Any]:
    session = orchestrator.store.get_session(session_id)
    if not session["facts"]:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
