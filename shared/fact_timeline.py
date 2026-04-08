"""LiveLogic - FactTimeline service for append-only event logging."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TimelineEvent(BaseModel):
    """Represents a fact lifecycle event in the timeline.

    Attributes:
        id: Unique UUID for this event (auto-generated if not provided)
        session_id: Identifier for the reasoning session
        event_type: Type of event (FACT_ASSERTED or FACT_RETRACTED)
        predicate: The ASP fact predicate string (e.g., "user(john)")
        timestamp: ISO 8601 timestamp when this event occurred
        rule_version_id: SHA-256 hash of the rule version that asserted this fact
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique UUID for this event")
    session_id: str = Field(..., description="Session identifier")
    event_type: Literal["FACT_ASSERTED", "FACT_RETRACTED"] = Field(
        ..., description="Type of event"
    )
    predicate: str = Field(..., description="Fact predicate string")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Event timestamp",
    )
    rule_version_id: str = Field(
        ..., description="SHA-256 hash of the rule version"
    )


class FactTimeline:
    """Append-only event log for fact assertions and retractions.

    Stores events in SQLite with immutable, append-only semantics.
    Provides methods to query active facts (asserted but not retracted)
    and to audit the full event history.

    Storage layout:
        storage/timeline.db (configurable via db_path)
    """

    def __init__(self, db_path: Path | str = "storage/timeline.db") -> None:
        """Initialize the timeline with a SQLite database path.

        Args:
            db_path: Path to SQLite database file. Defaults to "storage/timeline.db"
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create the timeline_events table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS timeline_events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL CHECK (event_type IN ('FACT_ASSERTED', 'FACT_RETRACTED')),
                    predicate TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    rule_version_id TEXT NOT NULL
                )
            """
            )
            # Indexes for query performance
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_id ON timeline_events(session_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON timeline_events(timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_predicate_time ON timeline_events(session_id, predicate, timestamp DESC)"
            )
            conn.commit()

    def assert_fact(
        self,
        session_id: str,
        predicate: str,
        rule_version_id: str,
        timestamp: Optional[datetime] = None,
    ) -> str:
        """Record a fact assertion event.

        Args:
            session_id: Session identifier
            predicate: Fact predicate string (e.g., "user(john)")
            rule_version_id: SHA-256 hash of the rule version
            timestamp: Event timestamp (injected for testing); defaults to current UTC time

        Returns:
            UUID of the created event
        """
        event_id = str(uuid.uuid4())
        event_time = timestamp or datetime.now(timezone.utc)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO timeline_events 
                (id, session_id, event_type, predicate, timestamp, rule_version_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    session_id,
                    "FACT_ASSERTED",
                    predicate,
                    event_time.isoformat(),
                    rule_version_id,
                ),
            )
            conn.commit()

        return event_id

    def retract_fact(
        self,
        session_id: str,
        predicate: str,
        rule_version_id: str,
        timestamp: Optional[datetime] = None,
    ) -> bool:
        """Record a fact retraction event only if the predicate was previously asserted.

        Retraction is only recorded if the latest event for the given
        (session_id, predicate, rule_version_id) combination prior to this
        retraction is a FACT_ASSERTED. This ensures that each retraction
        "undoes" one assertion, and double-retractions without an intervening
        assertion fail.

        Args:
            session_id: Session identifier
            predicate: Fact predicate string to retract (must match assertion exactly)
            rule_version_id: SHA-256 hash of the rule version
            timestamp: Event timestamp (injected for testing); defaults to current UTC time

        Returns:
            True if retraction was recorded, False if no matching assertion found
        """
        event_time = timestamp or datetime.now(timezone.utc)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Check the latest event for this combination before this retraction
            cursor.execute(
                """
                SELECT event_type FROM timeline_events
                WHERE session_id = ?
                  AND predicate = ?
                  AND rule_version_id = ?
                  AND timestamp <= ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (session_id, predicate, rule_version_id, event_time.isoformat())
            )
            row = cursor.fetchone()
            if row is None or row[0] != "FACT_ASSERTED":
                return False

            # Insert the retraction event
            event_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO timeline_events 
                (id, session_id, event_type, predicate, timestamp, rule_version_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    session_id,
                    "FACT_RETRACTED",
                    predicate,
                    event_time.isoformat(),
                    rule_version_id,
                ),
            )
            conn.commit()

        return True

    def get_facts(self, session_id: str, up_to: Optional[datetime] = None) -> list[str]:
        """Get active (non-retracted) facts for a session.

        Active facts are those whose most recent event (up to the optional cutoff)
        for their (predicate, rule_version_id) combination is an assertion.
        The result is returned as Clingo-ready predicate strings.

        Args:
            session_id: Session identifier
            up_to: Optional timestamp cutoff; only events at or before this time are considered

        Returns:
            List of active fact predicate strings (order not guaranteed)
        """
        events = self.get_events(session_id, up_to=up_to)
        # Track latest event type per (predicate, rule_version_id)
        latest_state: dict[tuple[str, str], str] = {}
        for event in events:
            key = (event.predicate, event.rule_version_id)
            latest_state[key] = event.event_type

        # A predicate is active if any of its combinations has latest state as FACT_ASSERTED
        active_predicates: set[str] = set()
        for (predicate, _), state in latest_state.items():
            if state == "FACT_ASSERTED":
                active_predicates.add(predicate)

        return list(active_predicates)

    def get_events(
        self,
        session_id: str,
        rule_version_id: Optional[str] = None,
        up_to: Optional[datetime] = None,
    ) -> list[TimelineEvent]:
        """Retrieve timeline events with optional filtering.

        Args:
            session_id: Session identifier (required)
            rule_version_id: Optional filter to only events from this rule version
            up_to: Optional timestamp cutoff; only events at or before this time

        Returns:
            List of TimelineEvent objects sorted by timestamp ascending
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            query = """
                SELECT id, session_id, event_type, predicate, timestamp, rule_version_id
                FROM timeline_events
                WHERE session_id = ?
            """
            params = [session_id]

            if rule_version_id is not None:
                query += " AND rule_version_id = ?"
                params.append(rule_version_id)

            if up_to is not None:
                query += " AND timestamp <= ?"
                params.append(up_to.isoformat())

            query += " ORDER BY timestamp ASC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            events = []
            for row in rows:
                event = TimelineEvent(
                    id=row[0],
                    session_id=row[1],
                    event_type=row[2],
                    predicate=row[3],
                    timestamp=datetime.fromisoformat(row[4]),
                    rule_version_id=row[5],
                )
                events.append(event)

            return events
