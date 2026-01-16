"""Background watcher that surfaces critical Jira updates proactively."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from .client import execute_jira_tool, get_active_jira_user_id
from .processing import JiraContentCleaner, ProcessedJiraIssue, parse_jira_search_response
from .seen_store import JiraSeenStore
from ...logging_config import logger
from ...utils.timezones import convert_to_user_timezone

if TYPE_CHECKING:
    from ...agents.interaction_agent.runtime import InteractionAgentRuntime

def _resolve_interaction_runtime() -> "InteractionAgentRuntime":
    from ...agents.interaction_agent.runtime import InteractionAgentRuntime
    return InteractionAgentRuntime()

DEFAULT_POLL_INTERVAL_SECONDS = 120.0
DEFAULT_LOOKBACK_MINUTES = 20
DEFAULT_MAX_RESULTS = 25
DEFAULT_SEEN_LIMIT = 500

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_DEFAULT_SEEN_PATH = _DATA_DIR / "jira_seen.json"

class ImportantIssueWatcher:
    """Poll Jira for updates and surface them using double-verification (ID + Time)."""

    def __init__(
        self,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES,
        *,
        seen_store: Optional[JiraSeenStore] = None,
    ) -> None:
        self._poll_interval = poll_interval_seconds
        self._lookback_minutes = lookback_minutes
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._seen_store = seen_store or JiraSeenStore(_DEFAULT_SEEN_PATH, DEFAULT_SEEN_LIMIT)
        self._cleaner = JiraContentCleaner() 
        self._has_seeded_initial_snapshot = False
        self._last_poll_timestamp: Optional[datetime] = None

    async def start(self) -> None:
        async with self._lock:
            if self._task and not self._task.done():
                return
            self._running = True
            self._has_seeded_initial_snapshot = False
            self._last_poll_timestamp = None
            self._task = asyncio.create_task(self._run(), name="important-jira-watcher")
            logger.info(
                "Important Jira watcher started",
                extra={"interval_seconds": self._poll_interval, "lookback_minutes": self._lookback_minutes},
            )

    async def stop(self) -> None:
        async with self._lock:
            self._running = False
            if self._task:
                self._task.cancel()
                try: await self._task
                except asyncio.CancelledError: pass
                self._task = None
                logger.info("Important Jira watcher stopped")

    async def _run(self) -> None:
        while self._running:
            try:
                await self._poll_once()
            except Exception as exc:
                logger.exception("Important Jira watcher poll failed", extra={"error": str(exc)})
            await asyncio.sleep(self._poll_interval)

    def _complete_poll(self, user_now: datetime) -> None:
        self._last_poll_timestamp = user_now
        self._has_seeded_initial_snapshot = True

    async def _poll_once(self) -> None:
        poll_started_at = datetime.now(timezone.utc)
        user_now = convert_to_user_timezone(poll_started_at)
        
        first_poll = not self._has_seeded_initial_snapshot
        previous_poll_timestamp = self._last_poll_timestamp
        interval_cutoff = user_now - timedelta(seconds=self._poll_interval)
        
        cutoff_time = interval_cutoff
        if previous_poll_timestamp and previous_poll_timestamp > interval_cutoff:
            cutoff_time = previous_poll_timestamp

        composio_user_id = get_active_jira_user_id()
        if not composio_user_id:
            logger.debug("Jira not connected; skipping importance poll")
            return

        jql = (
            f"updated >= -{self._lookback_minutes}m AND "
            f"(assignee = currentUser() OR priority in (High, Highest)) "
            f"ORDER BY updated DESC"
        )

        try:
            raw_result = execute_jira_tool(
                "JIRA_SEARCH_ISSUES_USING_JQL", 
                composio_user_id, 
                arguments={"jql": jql, "maxResults": DEFAULT_MAX_RESULTS}
            )
            processed_issues = parse_jira_search_response(raw_result, query=jql, cleaner=self._cleaner)
        except Exception as exc:
            logger.warning(
                "Failed to fetch Jira issues for watcher",
                extra={"error": str(exc)},
            )
            return

        if not processed_issues:
            logger.debug("No recent Jira issues found for watcher")
            self._complete_poll(user_now)
            return

        if first_poll:
            self._seen_store.mark_seen(issue.key for issue in processed_issues)
            logger.info(
                "Important Jira watcher completed initial warmup",
                extra={"skipped_ids": len(processed_issues)},
            )
            self._complete_poll(user_now)
            return

        unseen_issues = [i for i in processed_issues if not self._seen_store.is_seen(i.key)]
        
        if not unseen_issues:
            logger.info(
                "Important Jira watcher check complete",
                extra={"issues_reviewed": 0, "surfaced": 0},
            )
            self._complete_poll(user_now)
            return

        unseen_issues.sort(key=lambda i: i.updated or datetime.min.replace(tzinfo=timezone.utc))

        eligible_issues: List[ProcessedJiraIssue] = []
        aged_issues: List[ProcessedJiraIssue] = []

        for issue in unseen_issues:
            issue_time = issue.updated or datetime.now(timezone.utc)
            if issue_time.tzinfo is None:
                issue_time = issue_time.replace(tzinfo=user_now.tzinfo)

            if issue_time < cutoff_time:
                aged_issues.append(issue)
                continue

            eligible_issues.append(issue)

        summaries_sent = 0
        processed_keys: List[str] = [i.key for i in aged_issues]

        for issue in eligible_issues:
            await self._dispatch_issue_alert(issue)
            processed_keys.append(issue.key)
            summaries_sent += 1

        if processed_keys:
            self._seen_store.mark_seen(processed_keys)

        logger.info(
            "Important Jira watcher check complete",
            extra={
                "issues_reviewed": len(unseen_issues),
                "surfaced": summaries_sent,
                "suppressed_for_age": len(aged_issues),
            },
        )
        self._complete_poll(user_now)

    async def _dispatch_issue_alert(self, issue: ProcessedJiraIssue) -> None:
        runtime = _resolve_interaction_runtime()
        prefix = "🚨 Priority" if issue.priority in ["High", "Highest"] else "📋 Task"
        alert_text = (
            f"Jira Watcher: {prefix} Update\n"
            f"**[{issue.key}] {issue.summary}**\n"
            f"Status: {issue.status} | Assignee: {issue.assignee}\n"
            f"Description: {issue.clean_description[:150]}..."
        )
        try:
            await runtime.handle_agent_message(alert_text)
        except Exception as exc:
            logger.error(
                "Failed to dispatch important Jira issue alert",
                extra={"error": str(exc)},
            )