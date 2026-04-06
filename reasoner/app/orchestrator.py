"""LiveLogic Reasoner - SQLite session state and orchestration."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import dspy

from .clingo_reasoner import ClingoReasoner, SolveResult
from .dspy_pipeline import (
    CritiqueUnsat,
    ExtractSecurityFacts,
    InterpretAnswer,
    extract_facts_with_confidence,
)
from .models import EventType

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "sessions.db"
MAX_FACTS_PER_SESSION = 50


@dataclass
class ReasonResponse:
    """Structured response from the reasoning pipeline."""

    status: str  # "SAT", "UNSAT", "ERROR", "TIMEOUT"
    response: str
    trace: list[dict[str, Any]] = field(default_factory=list)
    suggested_retraction: str = ""
    confidence: float = 0.0


class SessionStore:
    """ACID SQLite session store."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    facts_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    turn INTEGER NOT NULL,
                    input_json TEXT NOT NULL,
                    output_json TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS timeline_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                )
                """
            )

    def get_session(self, session_id: str) -> dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, facts_json, created_at, updated_at FROM sessions WHERE id=?",
                (session_id,),
            ).fetchone()
        if row is None:
            now = time.time()
            return {
                "id": session_id,
                "facts": [],
                "created_at": now,
                "updated_at": now,
            }
        return {
            "id": row[0],
            "facts": json.loads(row[1]),
            "created_at": row[2],
            "updated_at": row[3],
        }

    def upsert_session(self, session_id: str, facts: list[str]) -> None:
        now = time.time()
        facts_json = json.dumps(facts)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, facts_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET facts_json=?, updated_at=?
                """,
                (session_id, facts_json, now, now, facts_json, now),
            )

    def add_fact(self, session_id: str, fact: str) -> list[str]:
        session = self.get_session(session_id)
        facts: list[str] = session["facts"]
        facts.append(fact)
        # LRU eviction
        if len(facts) > MAX_FACTS_PER_SESSION:
            facts = facts[-MAX_FACTS_PER_SESSION:]
        self.upsert_session(session_id, facts)
        return facts

    def retract_fact(self, session_id: str, fact: str) -> list[str]:
        session = self.get_session(session_id)
        facts: list[str] = session["facts"]
        if fact in facts:
            facts.remove(fact)
            self.upsert_session(session_id, facts)
        return facts

    def log_trace(
        self,
        session_id: str,
        turn: int,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO traces (session_id, turn, input_json, output_json, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    turn,
                    json.dumps(input_data),
                    json.dumps(output_data),
                    time.time(),
                ),
            )

    def get_traces(self, session_id: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT turn, input_json, output_json, timestamp FROM traces WHERE session_id=? ORDER BY turn",
                (session_id,),
            ).fetchall()
        return [
            {
                "turn": r[0],
                "input": json.loads(r[1]),
                "output": json.loads(r[2]),
                "timestamp": r[3],
            }
            for r in rows
        ]

    def log_event(
        self,
        session_id: str,
        event_type: str,
        version_id: str,
        payload: dict[str, Any],
        metadata: dict[str, Any],
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO timeline_events (session_id, timestamp, event_type, version_id, payload_json, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    time.time(),
                    event_type,
                    version_id,
                    json.dumps(payload),
                    json.dumps(metadata),
                ),
            )

    def get_timeline(self, session_id: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT timestamp, event_type, version_id, payload_json, metadata_json FROM timeline_events WHERE session_id=? ORDER BY timestamp",
                (session_id,),
            ).fetchall()
        return [
            {
                "timestamp": r[0],
                "event_type": r[1],
                "version_id": r[2],
                "payload": json.loads(r[3]),
                "metadata": json.loads(r[4]),
            }
            for r in rows
        ]


class ReasoningOrchestrator:
    """High-level pipeline: transcript → DSPy → Clingo → response."""

    def __init__(
        self,
        lp_path: str | None = None,
        store: SessionStore | None = None,
    ) -> None:
        self.reasoner = ClingoReasoner(lp_path=lp_path)
        self.store = store or SessionStore()
        self._extractor = dspy.Predict(ExtractSecurityFacts)
        self._critic = dspy.Predict(CritiqueUnsat)
        self._interpreter = dspy.Predict(InterpretAnswer)

    async def reason(
        self,
        session_id: str,
        transcript: str,
    ) -> ReasonResponse:
        trace: list[dict[str, Any]] = []

        # 1. Extract facts via DSPy
        facts_str, confidence = extract_facts_with_confidence(
            transcript, self._extractor
        )
        trace.append({"stage": "extract", "facts": facts_str, "confidence": confidence})

        if not facts_str.strip():
            self.store.log_event(
                session_id,
                EventType.ERROR.value,
                "v1",
                {"error": "Could not extract facts from transcript"},
                {"confidence": confidence},
            )
            return ReasonResponse(
                status="ERROR",
                response="I couldn't extract any logical facts from your input. Could you rephrase?",
                trace=trace,
                confidence=confidence,
            )

        # 2. Accumulate in session state (emit ASSERT event)
        all_facts = self.store.add_fact(session_id, facts_str.strip())
        self.store.log_event(
            session_id,
            EventType.ASSERT.value,
            "v1",
            {"facts": facts_str.strip(), "cumulative": all_facts},
            {"confidence": confidence},
        )
        facts_block = "\n".join(all_facts)

        # 3. Solve with Clingo
        result = await self.reasoner.solve(facts_block)
        trace.append(
            {
                "stage": "solve",
                "satisfiable": result.satisfiable,
                "unsatisfiable": result.unsatisfiable,
                "models": result.models,
                "error": result.error,
            }
        )

        if result.error:
            return ReasonResponse(
                status="ERROR",
                response=f"Solver error: {result.error}",
                trace=trace,
                confidence=confidence,
            )

        if result.timed_out:
            return ReasonResponse(
                status="TIMEOUT",
                response="The reasoning is taking longer than expected. Let me simplify the analysis...",
                trace=trace,
                confidence=confidence,
            )

        # 4. Handle UNSAT
        if result.unsatisfiable:
            core_result = await self.reasoner.check_unsat_core(facts_block)
            critique = self._critic(
                unsat_core=str(core_result.unsat_core),
                current_facts=facts_block,
            )
            explanation = getattr(critique, "explanation", "Unknown conflict detected.")
            retraction = getattr(critique, "suggested_retraction", "")
            trace.append({"stage": "critique", "explanation": explanation})

            self.store.log_event(
                session_id,
                EventType.CONFLICT_WARNING.value,
                "v1",
                {"unsat_core": core_result.unsat_core, "explanation": explanation},
                {"confidence": confidence, "suggested_retraction": retraction},
            )

            return ReasonResponse(
                status="UNSAT",
                response=explanation,
                trace=trace,
                suggested_retraction=retraction,
                confidence=confidence,
            )

        # 5. Interpret SAT models
        models_str = "\n".join(str(m) for m in result.models) if result.models else "No violations found."
        interpretation = self._interpreter(
            answer_sets=models_str,
            query_context=transcript,
        )
        response_text = getattr(interpretation, "response", "Analysis complete.")
        reasoning = getattr(interpretation, "reasoning_steps", "")
        trace.append({"stage": "interpret", "response": response_text, "reasoning": reasoning})

        self.store.log_event(
            session_id,
            EventType.ASSERT.value,
            "v1",
            {"result": "SAT", "models": len(result.models)},
            {"confidence": confidence},
        )

        return ReasonResponse(
            status="SAT",
            response=response_text,
            trace=trace,
            confidence=confidence,
        )

    async def retract(
        self,
        session_id: str,
        fact: str,
    ) -> ReasonResponse:
        remaining = self.store.retract_fact(session_id, fact)
        self.store.log_event(
            session_id,
            EventType.RETRACT.value,
            "v1",
            {"retracted_fact": fact},
            {},
        )
        if not remaining:
            return ReasonResponse(
                status="SAT",
                response="Fact retracted. No remaining facts to evaluate.",
            )
        return await self.reason("\n".join(remaining), session_id)
