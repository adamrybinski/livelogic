"""LiveLogic - TimelineEvent schema for audit trail and versioning."""

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of timeline events."""

    ASSERT = "assert"
    RETRACT = "retract"
    CONFLICT_WARNING = "conflict_warning"
    ERROR = "error"
    SESSION_START = "session_start"
    SESSION_END = "session_end"


class TimelineEvent(BaseModel):
    """Atomic entry in the reasoning timeline.

    This is the foundational schema for version control and audit trail.
    All state changes in the system are recorded as TimelineEvents.
    """

    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="ISO 8601 timestamp of the event",
    )
    event_type: EventType = Field(..., description="Type of timeline event")
    version_id: str = Field(
        default="v1",
        description="Hash or semantic version of rule-set active at this moment",
    )
    session_id: str = Field(..., description="Unique session identifier")
    payload: dict[str, Any] = Field(..., description="Event-specific data (facts, rules, explanation)")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Who/what triggered the change (for audit trail)",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "timestamp": "2026-04-06T10:00:00Z",
                    "event_type": "assert",
                    "version_id": "v1",
                    "session_id": "demo-1",
                    "payload": {"facts": "user(john). access_event(john, db_server, read, \"192.168.1.50\", t1)."},
                    "metadata": {"confidence": 0.95},
                }
            ]
        }
    }


class AssertPayload(BaseModel):
    """Payload for ASSERT events."""

    facts: str = Field(..., description="ASP facts being asserted")


class RetractPayload(BaseModel):
    """Payload for RETRACT events."""

    retracted_fact: str = Field(..., description="Fact that was removed")


class ConflictWarningPayload(BaseModel):
    """Payload for CONFLICT_WARNING events."""

    conflict_pairs: list[list[str]] = Field(
        default_factory=list,
        description="Pairs of conflicting facts",
    )
    explanation: str = Field(..., description="Human-readable conflict explanation")
    new_facts: str = Field(..., description="Facts that would cause conflict")


class ErrorPayload(BaseModel):
    """Payload for ERROR events."""

    error: str = Field(..., description="Error message")
    confidence: float = Field(default=0.0, description="Confidence score at time of error")