"""Persistence helper for tracking recently processed Jira issue keys."""

from __future__ import annotations

import json
import threading
from collections import deque
from pathlib import Path
from typing import Deque, Iterable, List, Optional, Set

from ...logging_config import logger

class JiraSeenStore:
    """Maintain a bounded set of Jira issue keys (e.g., 'PROJ-123') backed by a JSON file."""

    def __init__(self, path: Path, max_entries: int = 500) -> None:
        self._path = path
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: Deque[str] = deque()
        self._index: Set[str] = set()
        self._load()

    def is_seen(self, issue_key: str) -> bool:
        normalized = self._normalize(issue_key)
        if not normalized: return False
        with self._lock:
            return normalized in self._index

    def mark_seen(self, issue_keys: Iterable[str]) -> None:
        normalized_ids = [k for k in (self._normalize(k) for k in issue_keys) if k]
        if not normalized_ids: return

        with self._lock:
            for key in normalized_ids:
                if key in self._index:
                    try:
                        self._entries.remove(key)
                    except ValueError: pass
                else:
                    self._index.add(key)
                self._entries.append(key)

            self._prune_locked()
            self._persist_locked()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._index.clear()
            self._persist_locked()

    def _normalize(self, issue_key: Optional[str]) -> str:
        return str(issue_key).strip().upper() if issue_key else ""

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, list): return
            for raw_key in data[-self._max_entries :]:
                normalized = self._normalize(raw_key)
                if normalized and normalized not in self._index:
                    self._entries.append(normalized)
                    self._index.add(normalized)
        except FileNotFoundError: pass
        except Exception as exc:
            logger.warning("Failed to load Jira seen-store", extra={"error": str(exc)})

    def _prune_locked(self) -> None:
        while len(self._entries) > self._max_entries:
            oldest = self._entries.popleft()
            self._index.discard(oldest)

    def _persist_locked(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(list(self._entries)), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to persist Jira seen-store", extra={"error": str(exc)})

__all__ = ["JiraSeenStore"]