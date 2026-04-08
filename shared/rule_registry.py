"""LiveLogic - RuleRegistry service for immutable rule versioning."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import clingo
from pydantic import BaseModel, Field


class RuleSet(BaseModel):
    """Immutable snapshot of a collection of ASP rules.

    Attributes:
        version_id: SHA-256 hash of the rule content (unique fingerprint)
        timestamp: ISO 8601 timestamp when this version was registered
        tag: Human-readable version identifier (e.g., "v1.0.0", "security-rules-2024")
        content: The actual ASP rule content (.lp file text)
        metadata: Optional metadata about this rule version (author, changelog, etc.)
    """

    version_id: str = Field(
        ...,
        description="SHA-256 hash of rule content (unique fingerprint)",
        pattern=r"^[a-f0-9]{64}$",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="ISO 8601 timestamp when this version was registered",
    )
    tag: str = Field(..., description="Human-readable version identifier")
    content: str = Field(..., description="ASP rule content (.lp file text)")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Optional metadata (author, changelog, etc.)"
    )


class RegistryEntry(BaseModel):
    """Internal representation of a registry index entry."""

    timestamp: str  # ISO format
    tag: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuleRegistry:
    """Manages immutable rule snapshots with hash-based versioning.

    The registry ensures that every version of your logic files is stored
    permanently with a unique fingerprint (SHA-256). This enables:
    - Audit fidelity: timeline events reference exact rule versions
    - Reproducibility: any past state can be reconstructed
    - Safety: instant rollback by loading previous hashes

    Storage layout:
        storage/rules/
            {sha256_hash}.lp    # Rule content files
            index.json          # Metadata index (version_id -> tag, timestamp, metadata)
            active.json         # Currently active version ID
    """

    def __init__(self, storage_dir: Path | str = "storage/rules") -> None:
        """Initialize the registry with a storage directory.

        Args:
            storage_dir: Path to directory where rule files and index are stored.
                        Defaults to "storage/rules" relative to workspace.
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.storage_dir / "index.json"
        self.active_file = self.storage_dir / "active.json"
        self._index = self._load_index()
        self._active_version_id: str | None = self._load_active()

    def _load_index(self) -> dict[str, RegistryEntry]:
        """Load the registry index from disk."""
        if self.index_file.exists():
            try:
                with open(self.index_file, "r") as f:
                    data = json.load(f)
                    return {k: RegistryEntry(**v) for k, v in data.items()}
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def _save_index(self) -> None:
        """Save the registry index to disk with file locking."""
        index_dict = {k: v.model_dump() for k, v in self._index.items()}
        with open(self.index_file, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(index_dict, f, indent=2)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _load_active(self) -> str | None:
        """Load the active version ID from disk."""
        if self.active_file.exists():
            try:
                with open(self.active_file, "r") as f:
                    data = json.load(f)
                    return data.get("active_version_id")
            except (json.JSONDecodeError, IOError):
                return None
        return None

    def _save_active(self) -> None:
        """Save the active version ID to disk."""
        with open(self.active_file, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump({"active_version_id": self._active_version_id}, f, indent=2)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def calculate_hash(self, content: str) -> str:
        """Compute SHA-256 hash of rule content.

        Args:
            content: Raw ASP rule text

        Returns:
            64-character hexadecimal SHA-256 hash
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def validate_asp(self, content: str) -> None:
        """Validate ASP syntax using clingo.Control without grounding.

        Only parses the program to check for syntax errors. Does not attempt
        to resolve predicates or ground rules, so rules with variables and
        forward references are allowed.

        Args:
            content: ASP rule text to validate

        Raises:
            ValueError: If the ASP content has syntax errors
        """
        try:
            ctl = clingo.Control(["--warn=none"])
            ctl.add("base", [], content)
            # Only add, do not ground - grounding requires all predicates to be defined
        except Exception as e:
            raise ValueError(f"Invalid ASP syntax: {e}") from e

    def register(
        self,
        content: str,
        tag: str,
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> tuple[RuleSet, bool]:
        """Register a new rule version if not already present.

        Args:
            content: ASP rule content to store
            tag: Human-readable version tag (e.g., "v1.0.0")
            metadata: Optional metadata dictionary
            now: Timestamp to use (injected for testing); defaults to current UTC time

        Returns:
            Tuple of (RuleSet, is_new) where is_new=True if a new version was created,
            False if existing content was retrieved

        Raises:
            ValueError: If ASP content fails validation
        """
        # Validate ASP syntax before persisting
        self.validate_asp(content)

        version_id = self.calculate_hash(content)
        timestamp = now or datetime.now(timezone.utc)

        # Check if this exact content already exists (idempotent)
        if version_id in self._index:
            existing = self.get(version_id)
            if existing is not None:
                return existing, False
            # If index says it exists but file is missing, fall through to recreate

        # Persist rule content to file
        rule_file = self.storage_dir / f"{version_id}.lp"
        rule_file.write_text(content, encoding="utf-8")

        # Update index
        self._index[version_id] = RegistryEntry(
            timestamp=timestamp.isoformat(),
            tag=tag,
            metadata=metadata or {},
        )
        self._save_index()

        ruleset = RuleSet(
            version_id=version_id,
            timestamp=timestamp,
            tag=tag,
            content=content,
            metadata=metadata or {},
        )

        return ruleset, True

    def get(self, version_id: str) -> RuleSet | None:
        """Retrieve a rule set by version ID.

        Args:
            version_id: SHA-256 hash of the desired rule version

        Returns:
            RuleSet if found, None otherwise
        """
        if version_id not in self._index:
            return None

        rule_file = self.storage_dir / f"{version_id}.lp"
        if not rule_file.exists():
            return None

        content = rule_file.read_text(encoding="utf-8")
        index_entry = self._index[version_id]

        return RuleSet(
            version_id=version_id,
            timestamp=datetime.fromisoformat(index_entry.timestamp),
            tag=index_entry.tag,
            content=content,
            metadata=index_entry.metadata,
        )

    def list_rulesets(self) -> list[RuleSet]:
        """List all registered rule sets (newest first).

        Returns:
            List of RuleSet objects sorted by timestamp descending
        """
        rulesets = []
        for version_id, entry in self._index.items():
            rule_file = self.storage_dir / f"{version_id}.lp"
            if rule_file.exists():
                content = rule_file.read_text(encoding="utf-8")
                ruleset = RuleSet(
                    version_id=version_id,
                    timestamp=datetime.fromisoformat(entry.timestamp),
                    tag=entry.tag,
                    content=content,
                    metadata=entry.metadata,
                )
                rulesets.append(ruleset)

        return sorted(rulesets, key=lambda r: r.timestamp, reverse=True)

    def get_latest(self) -> RuleSet | None:
        """Get the most recently registered rule set."""
        rulesets = self.list_rulesets()
        return rulesets[0] if rulesets else None

    def get_active(self) -> RuleSet | None:
        """Get the currently active rule set.

        Returns:
            RuleSet if an active version is set, None otherwise
        """
        if self._active_version_id is None:
            return None
        return self.get(self._active_version_id)

    def set_active(self, version_id: str) -> None:
        """Set the active rule version.

        Args:
            version_id: SHA-256 hash of the rule version to activate

        Raises:
            ValueError: If the version ID does not exist in the registry
        """
        if version_id not in self._index:
            raise ValueError(f"Version {version_id} not found in registry")
        self._active_version_id = version_id
        self._save_active()

    def deactivate(self) -> None:
        """Clear the active version (no active ruleset)."""
        self._active_version_id = None
        self._save_active()

    def delete_version(self, version_id: str) -> bool:
        """Permanently delete a rule version from the registry.

        Args:
            version_id: SHA-256 hash of the rule version to delete

        Returns:
            True if deleted, False if not found

        Note:
            Cannot delete the currently active version. Deactivate first.
        """
        if version_id == self._active_version_id:
            raise ValueError("Cannot delete the currently active version. Deactivate first.")

        if version_id not in self._index:
            return False

        # Remove from index and delete file
        del self._index[version_id]
        self._save_index()

        rule_file = self.storage_dir / f"{version_id}.lp"
        if rule_file.exists():
            rule_file.unlink()

        return True
