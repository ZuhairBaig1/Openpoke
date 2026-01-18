"""Persistence helper for tracking Jira issue state snapshots."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List

from ...logging_config import logger

class JiraSeenStore:
    """Maintain a bounded map of Jira snapshots (Key -> State) backed by JSON."""

    def __init__(self, path: Path, max_entries: int = 1000) -> None:
        self._path = path
        self._max_entries = max_entries
        self._lock = threading.Lock()
        # Storage format: { "PROJ-123": {"status": "In Progress", "assignee": "...", ...} }
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        self._load()

    def is_empty(self) -> bool:
        """Returns True if no issues have been tracked yet (used for soft start)."""
        with self._lock:
            return len(self._snapshots) == 0

    def get_snapshot(self, issue_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve the last known state of an issue."""
        normalized = self._normalize(issue_key)
        with self._lock:
            return self._snapshots.get(normalized)

    def save_snapshot(self, issue_key: str, snapshot: Dict[str, Any]) -> None:
        """Save or update the state of an issue."""
        normalized = self._normalize(issue_key)
        with self._lock:
            # If it's a new entry and we are at capacity, remove the oldest (first) key
            if normalized not in self._snapshots and len(self._snapshots) >= self._max_entries:
                oldest_key = next(iter(self._snapshots))
                del self._snapshots[oldest_key]
            
            self._snapshots[normalized] = snapshot
            self._persist_locked()

    def get_all_keys(self) -> List[str]:
        """Returns all keys currently in the store."""
        with self._lock:
            return list(self._snapshots.keys())

    def clear(self) -> None:
        """Wipe all history."""
        with self._lock:
            self._snapshots.clear()
            self._persist_locked()

    def _normalize(self, issue_key: Optional[str]) -> str:
        return str(issue_key).strip().upper() if issue_key else ""

    def _load(self) -> None:
        """Load dict snapshots from disk."""
        if not self._path.exists():
            return
            
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._snapshots = data
            else:
                # Compatibility: If old file was a list, ignore it and start fresh
                logger.info("Jira seen-store format changed to snapshots; starting fresh.")
                self._snapshots = {}
        except Exception as exc:
            logger.warning("Failed to load Jira seen-store", extra={"error": str(exc)})

    def _persist_locked(self) -> None:
        """Write dict snapshots to disk."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._snapshots, indent=2), 
                encoding="utf-8"
            )
        except Exception as exc:
            logger.warning("Failed to persist Jira seen-store", extra={"error": str(exc)})

__all__ = ["JiraSeenStore"]