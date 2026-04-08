"""Test FactTimeline functionality."""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.fact_timeline import FactTimeline, TimelineEvent


@pytest.fixture
def temp_timeline(tmp_path) -> FactTimeline:
    """Create a temporary timeline for testing."""
    db_path = tmp_path / "test_timeline.db"
    return FactTimeline(db_path=db_path)


def test_database_created(temp_timeline):
    """Test that database file is created."""
    assert temp_timeline.db_path.exists()


def test_assert_fact_creates_event(temp_timeline):
    """Test asserting a fact creates an event and returns an ID."""
    session_id = "session1"
    predicate = "user(john)"
    rule_version_id = "a" * 64  # SHA-256 placeholder

    event_id = temp_timeline.assert_fact(session_id, predicate, rule_version_id)

    assert event_id is not None
    assert len(event_id) == 36  # UUID format
    
    # Verify the fact is in active facts
    facts = temp_timeline.get_facts(session_id)
    assert predicate in facts


def test_assert_and_retrieve_fact(temp_timeline):
    """Test that an asserted fact can be retrieved."""
    session_id = "session1"
    predicate = "assigned_role(john, admin)"
    rule_version_id = "b" * 64

    temp_timeline.assert_fact(session_id, predicate, rule_version_id)
    facts = temp_timeline.get_facts(session_id)

    assert predicate in facts
    assert len(facts) == 1


def test_assert_multiple_facts(temp_timeline):
    """Test asserting multiple facts."""
    session_id = "session1"
    facts_to_assert = [
        ("user(alice)", "v1"),
        ("user(bob)", "v2"),
        ("assigned_role(alice, admin)", "v1"),
    ]
    
    for predicate, rule_version_id in facts_to_assert:
        temp_timeline.assert_fact(session_id, predicate, rule_version_id)
    
    active_facts = temp_timeline.get_facts(session_id)
    assert len(active_facts) == 3
    for predicate, _ in facts_to_assert:
        assert predicate in active_facts


def test_retract_fact_removes_from_active(temp_timeline):
    """Test that retracting a fact removes it from active facts."""
    session_id = "session1"
    predicate = "user(john)"
    rule_version_id = "a" * 64

    temp_timeline.assert_fact(session_id, predicate, rule_version_id)
    assert predicate in temp_timeline.get_facts(session_id)

    # Retract the fact
    result = temp_timeline.retract_fact(session_id, predicate, rule_version_id)
    assert result is True
    
    # Fact should no longer be active
    facts = temp_timeline.get_facts(session_id)
    assert predicate not in facts
    assert len(facts) == 0


def test_retract_remains_in_audit_log(temp_timeline):
    """Test that retracted facts still appear in the audit log."""
    session_id = "session1"
    predicate = "user(john)"
    rule_version_id = "a" * 64

    event_id = temp_timeline.assert_fact(session_id, predicate, rule_version_id)
    events_before = temp_timeline.get_events(session_id)
    assert len(events_before) == 1
    assert events_before[0].event_type == "FACT_ASSERTED"

    temp_timeline.retract_fact(session_id, predicate, rule_version_id)
    events_after = temp_timeline.get_events(session_id)
    assert len(events_after) == 2
    assert events_after[0].event_type == "FACT_ASSERTED"
    assert events_after[1].event_type == "FACT_RETRACTED"
    assert events_after[1].predicate == predicate


def test_retract_non_existent_fact_returns_false(temp_timeline):
    """Test that retracting a non-existent fact returns False and does not insert."""
    session_id = "session1"
    predicate = "user(john)"
    rule_version_id = "a" * 64

    # Try to retract without asserting first
    result = temp_timeline.retract_fact(session_id, predicate, rule_version_id)
    assert result is False

    # No events should be recorded
    events = temp_timeline.get_events(session_id)
    assert len(events) == 0

    facts = temp_timeline.get_facts(session_id)
    assert len(facts) == 0


def test_retract_exact_match_required(temp_timeline):
    """Test that retraction requires exact predicate match."""
    session_id = "session1"
    predicate1 = "user(john)"
    predicate2 = "user(jane)"
    rule_version_id = "a" * 64

    # Assert one fact
    temp_timeline.assert_fact(session_id, predicate1, rule_version_id)
    
    # Try to retract different fact
    result = temp_timeline.retract_fact(session_id, predicate2, rule_version_id)
    assert result is False
    
    # Original fact should still be active
    facts = temp_timeline.get_facts(session_id)
    assert predicate1 in facts
    assert len(facts) == 1


def test_retract_with_different_rule_version(temp_timeline):
    """Test that retraction requires matching rule_version_id."""
    session_id = "session1"
    predicate = "user(john)"
    rule_v1 = "a" * 64
    rule_v2 = "b" * 64

    # Assert with v1
    temp_timeline.assert_fact(session_id, predicate, rule_v1)
    
    # Try to retract with v2
    result = temp_timeline.retract_fact(session_id, predicate, rule_v2)
    assert result is False
    
    # Fact should still be active (retraction didn't count)
    facts = temp_timeline.get_facts(session_id)
    assert predicate in facts


def test_get_facts_with_timestamp_cutoff(temp_timeline):
    """Test that up_to parameter correctly filters facts by timestamp."""
    session_id = "session1"
    rule_version_id = "a" * 64
    
    # Create timestamps
    t1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2024, 1, 3, 12, 0, 0, tzinfo=timezone.utc)

    # Assert facts at different times
    temp_timeline.assert_fact(session_id, "user(alice)", rule_version_id, t1)
    temp_timeline.assert_fact(session_id, "user(bob)", rule_version_id, t2)
    temp_timeline.assert_fact(session_id, "user(charlie)", rule_version_id, t3)

    # Get all facts (no cutoff)
    all_facts = temp_timeline.get_facts(session_id)
    assert len(all_facts) == 3

    # Get facts up to t2 (exclusive of events after)
    facts_up_to_t2 = temp_timeline.get_facts(session_id, up_to=t2)
    assert len(facts_up_to_t2) == 2
    assert "user(alice)" in facts_up_to_t2
    assert "user(bob)" in facts_up_to_t2
    assert "user(charlie)" not in facts_up_to_t2

    # Get facts up to t3 should include all
    facts_up_to_t3 = temp_timeline.get_facts(session_id, up_to=t3)
    assert len(facts_up_to_t3) == 3


def test_get_facts_cutoff_includes_asserted_before_retracted(temp_timeline):
    """Test that a fact asserted before up_to and retracted after is excluded."""
    session_id = "session1"
    predicate = "user(john)"
    rule_version_id = "a" * 64

    t1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2024, 1, 3, 12, 0, 0, tzinfo=timezone.utc)

    # Assert at t1
    temp_timeline.assert_fact(session_id, predicate, rule_version_id, t1)
    # Retract at t3
    temp_timeline.retract_fact(session_id, predicate, rule_version_id, t3)

    # Up to t2 (before retraction) should include the fact
    facts_before_retract = temp_timeline.get_facts(session_id, up_to=t2)
    assert predicate in facts_before_retract

    # Up to t3 (at/after retraction) should exclude the fact
    facts_after_retract = temp_timeline.get_facts(session_id, up_to=t3)
    assert predicate not in facts_after_retract


def test_rule_version_id_stored_and_retrievable(temp_timeline):
    """Test that rule_version_id is correctly stored and can be queried."""
    session_id = "session1"
    predicate = "user(john)"
    rule_v1 = "a" * 64
    rule_v2 = "b" * 64

    # Assert with different rule versions
    temp_timeline.assert_fact(session_id, predicate, rule_v1, t1 := datetime(2024, 1, 1, tzinfo=timezone.utc))
    temp_timeline.assert_fact(session_id, predicate, rule_v2, t2 := datetime(2024, 1, 2, tzinfo=timezone.utc))

    # Get events for specific rule version
    events_v1 = temp_timeline.get_events(session_id, rule_version_id=rule_v1)
    assert len(events_v1) == 1
    assert events_v1[0].rule_version_id == rule_v1
    assert events_v1[0].predicate == predicate

    events_v2 = temp_timeline.get_events(session_id, rule_version_id=rule_v2)
    assert len(events_v2) == 1
    assert events_v2[0].rule_version_id == rule_v2

    # Get all events
    all_events = temp_timeline.get_events(session_id)
    assert len(all_events) == 2


def test_get_events_returns_timeline_event_objects(temp_timeline):
    """Test that get_events returns TimelineEvent objects with correct types."""
    session_id = "session1"
    predicate = "user(alice)"
    rule_version_id = "a" * 64

    temp_timeline.assert_fact(session_id, predicate, rule_version_id)

    events = temp_timeline.get_events(session_id)
    assert len(events) == 1
    event = events[0]

    assert isinstance(event, TimelineEvent)
    assert isinstance(event.id, str)
    assert event.session_id == session_id
    assert event.event_type == "FACT_ASSERTED"
    assert event.predicate == predicate
    assert event.rule_version_id == rule_version_id
    assert isinstance(event.timestamp, datetime)


def test_get_events_sorted_by_timestamp_asc(temp_timeline):
    """Test that events are returned sorted by timestamp ascending."""
    session_id = "session1"
    rule_version_id = "a" * 64

    t1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2024, 1, 3, 12, 0, 0, tzinfo=timezone.utc)

    # Create events out of order
    temp_timeline.assert_fact(session_id, "fact3", rule_version_id, t3)
    temp_timeline.assert_fact(session_id, "fact1", rule_version_id, t1)
    temp_timeline.assert_fact(session_id, "fact2", rule_version_id, t2)

    events = temp_timeline.get_events(session_id)
    
    assert len(events) == 3
    timestamps = [e.timestamp for e in events]
    assert timestamps == sorted(timestamps)
    assert events[0].predicate == "fact1"
    assert events[1].predicate == "fact2"
    assert events[2].predicate == "fact3"


def test_get_events_with_up_to_cutoff(temp_timeline):
    """Test that get_events respects up_to parameter."""
    session_id = "session1"
    rule_version_id = "a" * 64

    t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2024, 1, 2, tzinfo=timezone.utc)
    t3 = datetime(2024, 1, 3, tzinfo=timezone.utc)

    temp_timeline.assert_fact(session_id, "fact1", rule_version_id, t1)
    temp_timeline.assert_fact(session_id, "fact2", rule_version_id, t2)
    temp_timeline.assert_fact(session_id, "fact3", rule_version_id, t3)

    events_up_to_t2 = temp_timeline.get_events(session_id, up_to=t2)
    assert len(events_up_to_t2) == 2
    assert {e.predicate for e in events_up_to_t2} == {"fact1", "fact2"}


def test_get_events_with_rule_version_filter(temp_timeline):
    """Test that get_events correctly filters by rule_version_id."""
    session_id = "session1"
    rule_v1 = "a" * 64
    rule_v2 = "b" * 64

    t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2024, 1, 2, tzinfo=timezone.utc)

    temp_timeline.assert_fact(session_id, "fact_v1", rule_v1, t1)
    temp_timeline.assert_fact(session_id, "fact_v2", rule_v2, t2)

    events_v1 = temp_timeline.get_events(session_id, rule_version_id=rule_v1)
    assert len(events_v1) == 1
    assert events_v1[0].rule_version_id == rule_v1
    assert events_v1[0].predicate == "fact_v1"

    events_v2 = temp_timeline.get_events(session_id, rule_version_id=rule_v2)
    assert len(events_v2) == 1
    assert events_v2[0].rule_version_id == rule_v2


def test_multiple_sessions_isolated(temp_timeline):
    """Test that different sessions have separate fact stores."""
    rule_version_id = "a" * 64

    # Session 1 facts
    temp_timeline.assert_fact("session1", "user(alice)", rule_version_id)
    temp_timeline.assert_fact("session1", "user(bob)", rule_version_id)

    # Session 2 facts
    temp_timeline.assert_fact("session2", "user(charlie)", rule_version_id)
    temp_timeline.assert_fact("session2", "user(dave)", rule_version_id)

    facts1 = temp_timeline.get_facts("session1")
    facts2 = temp_timeline.get_facts("session2")

    assert len(facts1) == 2
    assert "user(alice)" in facts1
    assert "user(bob)" in facts1

    assert len(facts2) == 2
    assert "user(charlie)" in facts2
    assert "user(dave)" in facts2


def test_append_only_behavior(temp_timeline):
    """Test that events are never updated or deleted, only appended."""
    session_id = "session1"
    rule_version_id = "a" * 64

    temp_timeline.assert_fact(session_id, "user(john)", rule_version_id)
    
    initial_events = temp_timeline.get_events(session_id)
    initial_count = len(initial_events)
    initial_event_id = initial_events[0].id

    # Retract
    temp_timeline.retract_fact(session_id, "user(john)", rule_version_id)

    # Original assertion should still be there
    events = temp_timeline.get_events(session_id)
    assert len(events) == initial_count + 1
    assert any(e.id == initial_event_id and e.event_type == "FACT_ASSERTED" for e in events)
    assert any(e.event_type == "FACT_RETRACTED" for e in events)


def test_retract_same_fact_multiple_times(temp_timeline):
    """Test that retracting the same fact twice only records one retraction."""
    session_id = "session1"
    predicate = "user(john)"
    rule_version_id = "a" * 64

    # Assert once
    temp_timeline.assert_fact(session_id, predicate, rule_version_id)
    
    # Retract twice
    result1 = temp_timeline.retract_fact(session_id, predicate, rule_version_id)
    result2 = temp_timeline.retract_fact(session_id, predicate, rule_version_id)
    
    assert result1 is True
    assert result2 is False  # Second retraction should fail
    
    # Only one retraction event should be recorded
    events = temp_timeline.get_events(session_id)
    assert len(events) == 2  # 1 assert + 1 retract
    retract_events = [e for e in events if e.event_type == "FACT_RETRACTED"]
    assert len(retract_events) == 1


def test_re_assert_after_retraction(temp_timeline):
    """Test that a fact can be re-asserted after retraction."""
    session_id = "session1"
    predicate = "user(john)"
    rule_version_id = "a" * 64

    # Assert, retract, then assert again
    temp_timeline.assert_fact(session_id, predicate, rule_version_id)
    temp_timeline.retract_fact(session_id, predicate, rule_version_id)
    
    # Fact should not be active after retraction
    facts = temp_timeline.get_facts(session_id)
    assert predicate not in facts

    # Assert again
    temp_timeline.assert_fact(session_id, predicate, rule_version_id)
    
    # Fact should be active again
    facts = temp_timeline.get_facts(session_id)
    assert predicate in facts
    
    # Audit log should show 2 assertions and 1 retraction
    events = temp_timeline.get_events(session_id)
    assert_events = [e for e in events if e.event_type == "FACT_ASSERTED"]
    retract_events = [e for e in events if e.event_type == "FACT_RETRACTED"]
    assert len(assert_events) == 2
    assert len(retract_events) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
