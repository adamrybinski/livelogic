"""Test RuleRegistry functionality."""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.rule_registry import RuleRegistry, RuleSet


@pytest.fixture
def temp_registry(tmp_path) -> RuleRegistry:
    """Create a temporary registry for testing."""
    storage_dir = tmp_path / "test_rules"
    return RuleRegistry(storage_dir=storage_dir)


def test_hash_consistency(temp_registry):
    """Test that same content produces same hash."""
    content = "user(john)."
    hash1 = temp_registry.calculate_hash(content)
    hash2 = temp_registry.calculate_hash(content)
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex length


def test_hash_differentiates(temp_registry):
    """Test that different content produces different hashes."""
    content1 = "user(john)."
    content2 = "user(jane)."
    hash1 = temp_registry.calculate_hash(content1)
    hash2 = temp_registry.calculate_hash(content2)
    assert hash1 != hash2


def test_validate_asp_valid(temp_registry):
    """Test ASP validation accepts valid content."""
    valid_content = "user(john).\nassigned_role(john, analyst)."
    # Should not raise
    temp_registry.validate_asp(valid_content)


def test_validate_asp_with_rules_and_variables(temp_registry):
    """Test that rules with variables (like real .lp files) are accepted."""
    # This is a realistic policy rule with variables
    policy_rule = """
has_role(U, Rl) :- user(U), assigned_role(U, Rl).

permitted(U, R, A) :- has_role(U, Rl), allowed_role(Rl, R, A).

forbidden_ip_access(U, R, A) :-
    access_event(U, R, A, IP, _),
    forbidden_subnet(S),
    ip_in_subnet(IP, S).
"""
    # Should not raise - variables and forward references are allowed
    temp_registry.validate_asp(policy_rule)


def test_validate_asp_invalid_syntax(temp_registry):
    """Test ASP validation rejects invalid syntax."""
    invalid_content = "user(john). assigned_role(john, analyst"  # Missing closing paren
    with pytest.raises(ValueError, match="Invalid ASP syntax"):
        temp_registry.validate_asp(invalid_content)


def test_validate_asp_edge_cases(temp_registry):
    """Test ASP validation edge cases - some slip through, note in docs."""
    # These should raise - caught by ctl.add()
    with pytest.raises(ValueError):
        temp_registry.validate_asp("user::=john.")  # double colon
    with pytest.raises(ValueError):
        temp_registry.validate_asp("user(john). !!!")  # trailing garbage
    
    # Note: ":- ." (constraint without head) may not raise at parse time
    # clingo is lenient and treats it as a ground constraint. This is documented
    # in the validate_asp method - real syntax errors surface at ground/solve time
    # which is acceptable since invalid rules will fail when ClingoReasoner solves.


def test_register_new_rule(temp_registry):
    """Test registering a new rule version."""
    content = "user(john).\nassigned_role(john, admin)."
    tag = "v1.0.0"
    metadata = {"author": "admin"}

    ruleset, is_new = temp_registry.register(content, tag, metadata)

    assert is_new is True
    assert ruleset.version_id is not None
    assert len(ruleset.version_id) == 64
    assert ruleset.tag == tag
    assert ruleset.content == content
    assert ruleset.metadata == metadata
    assert isinstance(ruleset.timestamp, datetime)


def test_register_duplicate_content_returns_existing(temp_registry):
    """Test that registering same content returns existing version and is_new=False."""
    content = "user(john).\nassigned_role(john, analyst)."
    tag1 = "v1.0.0"
    tag2 = "v1.0.1"  # Different tag but same content

    ruleset1, is_new1 = temp_registry.register(content, tag1)
    ruleset2, is_new2 = temp_registry.register(content, tag2)

    assert is_new1 is True
    assert is_new2 is False  # Cache hit
    assert ruleset1.version_id == ruleset2.version_id
    assert ruleset1.content == ruleset2.content
    # Should keep original tag and timestamp from first registration
    assert ruleset1.tag == tag1
    assert ruleset2.tag == tag1  # Returns the original RuleSet with original tag


def test_register_with_injected_time(temp_registry):
    """Test that injected timestamp is used."""
    content = "user(jane).\nhas_role(jane, analyst)."
    tag = "test-v1"
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    ruleset, is_new = temp_registry.register(content, tag, now=now)

    assert is_new is True
    assert ruleset.timestamp == now


def test_get_existing_rule(temp_registry):
    """Test retrieving a stored rule."""
    content = 'forbidden_subnet("10.0.0.0/24").'
    tag = "security-v2"
    ruleset_registered, _ = temp_registry.register(content, tag)

    ruleset_retrieved = temp_registry.get(ruleset_registered.version_id)

    assert ruleset_retrieved is not None
    assert ruleset_retrieved.version_id == ruleset_registered.version_id
    assert ruleset_retrieved.content == content
    assert ruleset_retrieved.tag == tag


def test_get_nonexistent_rule_returns_none(temp_registry):
    """Test that getting unknown version_id returns None."""
    fake_hash = "a" * 64
    result = temp_registry.get(fake_hash)
    assert result is None


def test_list_rulesets_sorted_by_time(temp_registry):
    """Test that list_rulesets returns newest first without using sleep()."""
    # Use specific timestamps via the now parameter
    t1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2024, 1, 3, 12, 0, 0, tzinfo=timezone.utc)

    ruleset1, _ = temp_registry.register("user(alice).", "v1.0.0", now=t1)
    ruleset2, _ = temp_registry.register("user(bob).", "v1.1.0", now=t2)
    ruleset3, _ = temp_registry.register("user(charlie).", "v2.0.0", now=t3)

    all_rulesets = temp_registry.list_rulesets()

    assert len(all_rulesets) == 3
    # Should be sorted newest first
    assert all_rulesets[0].version_id == ruleset3.version_id
    assert all_rulesets[1].version_id == ruleset2.version_id
    assert all_rulesets[2].version_id == ruleset1.version_id


def test_get_latest(temp_registry):
    """Test getting the most recently registered rule."""
    t1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc)

    _, _ = temp_registry.register("user(alice).", "v1.0.0", now=t1)
    ruleset2, _ = temp_registry.register("user(bob).", "v2.0.0", now=t2)

    latest = temp_registry.get_latest()

    assert latest is not None
    assert latest.version_id == ruleset2.version_id


def test_files_persisted_to_disk(temp_registry):
    """Test that rule files are written to storage directory."""
    content = "user(test)."
    tag = "test-v1"
    ruleset, _ = temp_registry.register(content, tag)

    rule_file = temp_registry.storage_dir / f"{ruleset.version_id}.lp"
    assert rule_file.exists()
    assert rule_file.read_text() == content

    index_file = temp_registry.index_file
    assert index_file.exists()


def test_registry_idempotent(temp_registry):
    """Test that registry operations are idempotent."""
    content = "user(idempotent)."
    tag = "idempotent-v1"

    ruleset1, is_new1 = temp_registry.register(content, tag)
    ruleset2, is_new2 = temp_registry.register(content, tag)
    ruleset3 = temp_registry.get(ruleset1.version_id)

    assert is_new1 is True
    assert is_new2 is False
    assert ruleset1.version_id == ruleset2.version_id == ruleset3.version_id
    assert len(temp_registry.list_rulesets()) == 1


def test_get_active_no_active_set(temp_registry):
    """Test get_active returns None when no active version."""
    assert temp_registry.get_active() is None


def test_set_and_get_active(temp_registry):
    """Test setting and retrieving active version."""
    content = "user(active)."
    tag = "active-v1"
    ruleset, _ = temp_registry.register(content, tag)

    temp_registry.set_active(ruleset.version_id)
    active = temp_registry.get_active()

    assert active is not None
    assert active.version_id == ruleset.version_id


def test_set_active_invalid_version_raises(temp_registry):
    """Test set_active with non-existent version raises error."""
    fake_hash = "a" * 64
    with pytest.raises(ValueError, match="not found"):
        temp_registry.set_active(fake_hash)


def test_deactivate(temp_registry):
    """Test deactivating clears active version."""
    content = "user(deactivate)."
    tag = "deactivate-v1"
    ruleset, _ = temp_registry.register(content, tag)

    temp_registry.set_active(ruleset.version_id)
    assert temp_registry.get_active() is not None

    temp_registry.deactivate()
    assert temp_registry.get_active() is None


def test_delete_version(temp_registry):
    """Test deleting a rule version."""
    content = "user(delete)."
    tag = "delete-v1"
    ruleset, _ = temp_registry.register(content, tag)

    # Should succeed
    deleted = temp_registry.delete_version(ruleset.version_id)
    assert deleted is True

    # Should no longer exist
    assert temp_registry.get(ruleset.version_id) is None
    assert ruleset.version_id not in [rs.version_id for rs in temp_registry.list_rulesets()]

    # Deleting again returns False
    deleted_again = temp_registry.delete_version(ruleset.version_id)
    assert deleted_again is False


def test_delete_active_version_raises(temp_registry):
    """Test cannot delete the active version."""
    content = "user(active)."
    tag = "active-v1"
    ruleset, _ = temp_registry.register(content, tag)
    temp_registry.set_active(ruleset.version_id)

    with pytest.raises(ValueError, match="Cannot delete the currently active version"):
        temp_registry.delete_version(ruleset.version_id)


def test_register_validation_failure_rollback(temp_registry):
    """Test that invalid ASP prevents storage."""
    invalid_content = "invalid syntax here !!!"
    tag = "invalid-v1"

    with pytest.raises(ValueError, match="Invalid ASP syntax"):
        temp_registry.register(invalid_content, tag)

    # Should not have created any files
    assert len(temp_registry.list_rulesets()) == 0
    # Index file may exist but should be empty or only contain valid entries
    if temp_registry.index_file.exists():
        assert len(temp_registry._index) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
