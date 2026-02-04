"""Background watcher that surfaces Jira updates via AI classification."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from .client import execute_jira_tool, get_active_jira_user_id
from .processing import JiraContentCleaner, ProcessedJiraIssue, parse_jira_search_response
from .seen_store import JiraSeenStore
# We assume this function is defined in your classifier file
from .importance_classifier import classify_jira_changes 
from ...logging_config import logger

if TYPE_CHECKING:
    from ...agents.interaction_agent.runtime import InteractionAgentRuntime

def _resolve_interaction_runtime() -> "InteractionAgentRuntime":
    from ...agents.interaction_agent.runtime import InteractionAgentRuntime
    return InteractionAgentRuntime()

DEFAULT_POLL_INTERVAL_SECONDS = 120.0
DEFAULT_MAX_RESULTS = 100
DEFAULT_SEEN_LIMIT = 1000

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_DEFAULT_SEEN_PATH = _DATA_DIR / "jira_seen.json"
_watcher_instance: Optional[ImportantIssueWatcher] = None

class ImportantIssueWatcher:
    """Polls Jira and uses an AI Classifier to determine notification worthiness."""

    def __init__(
        self,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        *,
        seen_store: Optional[JiraSeenStore] = None,
    ) -> None:
        self._poll_interval = poll_interval_seconds
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._seen_store = seen_store or JiraSeenStore(_DEFAULT_SEEN_PATH, DEFAULT_SEEN_LIMIT)
        self._cleaner = JiraContentCleaner() 

    # ... [start/stop/run methods remain identical to previous versions] ...
    async def start(self) -> None:
        async with self._lock:
            if self._task and not self._task.done(): return
            self._running = True
            self._task = asyncio.create_task(self._run(), name="jira-ai-watcher")
            logger.info("Jira watcher started")

    async def stop(self) -> None:
        async with self._lock:
            self._running = False
            if self._task:
                self._task.cancel()
                try: await self._task
                except asyncio.CancelledError: pass
                self._task = None

    async def _run(self) -> None:
        while self._running:
            try: await self._poll_once()
            except Exception as exc: logger.exception("Watcher poll failed", extra={"error": str(exc)})
            await asyncio.sleep(self._poll_interval)

    async def _poll_once(self) -> None:
        composio_user_id = get_active_jira_user_id()
        if not composio_user_id:
            logger.debug("Jira not connected; skipping importance poll")
            return

        # 1. Fetch Issues (No time cutoff)
        jql = "assignee = currentUser() OR watcher = currentUser() OR reporter = currentUser() ORDER BY updated DESC"
        
        try:
            raw_result = execute_jira_tool(
                "JIRA_SEARCH_FOR_ISSUES_USING_JQL_GET", 
                composio_user_id, 
                arguments={"jql": jql, "maxResults": DEFAULT_MAX_RESULTS}
            )
            # Ensure your parser extracts 'duedate' into the issue object fields
            issues = parse_jira_search_response(raw_result, query=jql, cleaner=self._cleaner)
        except Exception as exc:
            logger.warning("Failed to fetch Jira issues", extra={"error": str(exc)})
            return

        if not issues:
            return

        # 2. Check for Soft Start (First run with no persistent data)
        # If true, we will strictly SAVE only, never READ/COMPARE.
        is_soft_start = self._seen_store.is_empty()

        for issue in issues:
            # Safely extract due date (it might be None/Empty in Jira)
            raw_due_date = issue.due_date
            
            # Generate current snapshot
            current_snapshot = {
                "assignee": issue.assignee,
                "priority": issue.priority,
                "status": issue.status,
                "due_date": raw_due_date if raw_due_date else "None",
                "last_seen_comment_id": "0" 
            }

            # 3. Soft Start & Initialization Logic
            if is_soft_start:
                # Seed the comment ID so next run doesn't alert on old comments
                current_snapshot["last_seen_comment_id"] = await self._get_latest_comment_id(issue.key, composio_user_id)
                self._seen_store.save_snapshot(issue.key, current_snapshot)
                continue

            # 4. Fetch Old Snapshot
            old_snapshot = self._seen_store.get_snapshot(issue.key)
            if not old_snapshot:
                # New issue detected during normal operation (not soft start)
                # We save it and treat it as "newly discovered"
                current_snapshot["last_seen_comment_id"] = await self._get_latest_comment_id(issue.key, composio_user_id)
                self._seen_store.save_snapshot(issue.key, current_snapshot)
                # Optional: You could alert here "New Issue Discovered", 
                # but typically we wait for changes.
                continue

            # 5. Detect Changes (The "Diffing" Phase)
            detected_changes = {}

            # A. Field Changes
            for field in ["assignee", "priority", "status", "due_date"]:
                old_val = old_snapshot.get(field)
                new_val = current_snapshot[field]
                if old_val != new_val:
                    detected_changes[field] = {"old": old_val, "new": new_val}

            # B. Mention Changes
            last_id = old_snapshot.get("last_seen_comment_id", "0")
            mention_detected, latest_id, mention_text = await self._check_new_mentions(issue.key, last_id, composio_user_id)
            current_snapshot["last_seen_comment_id"] = latest_id

            if mention_detected:
                detected_changes["mention"] = {"text": mention_text}

            # 6. AI Classification
            if detected_changes:
                classification = await classify_jira_changes(issue, detected_changes)
                
                # Check 1: Did the system fail? (None)
                if classification is None:
                    logger.debug(f"Classifier unavailable for {issue.key}; skipping this cycle.")
                    continue 

                # Check 2: Did the AI decide it's important? (True/False)
                if classification.get("is_worthy"):
                    await self._dispatch_classified_alert(issue, classification)
            
            # 7. Update Store
            self._seen_store.save_snapshot(issue.key, current_snapshot)

        if is_soft_start:
            logger.info("Jira Watcher soft start complete. Seen file populated.")

    async def _dispatch_classified_alert(self, issue: ProcessedJiraIssue, classification: Dict[str, Any]) -> None:
        """Constructs a message based on the AI's structured analysis."""
        runtime = _resolve_interaction_runtime()
        
        # We filter the changes list to only show what the AI deemed 'High' or 'Medium' importance
        # or simply list all valid reasons provided by the model.
        changes = classification.get("changes", [])
        bullet_points = []
        
        for change in changes:
            # Example format: "• Due Date: Deadline moved up by 2 days"
            field_name = change.get("field", "Update").replace("_", " ").title()
            reason = change.get("reason", "Changed")
            bullet_points.append(f"• **{field_name}**: {reason}")

        bullets_text = "\n".join(bullet_points)
        summary_header = classification.get("summary_header", "Jira Update")
        
        alert_text = (
            f"🔔 **{summary_header}: {issue.key}**\n"
            f"{issue.summary}\n\n"
            f"**Analysis:**\n{bullets_text}\n"
            f"---\n"
            f"Status: {issue.status} | Assignee: {issue.assignee}"
        )
        await runtime.handle_agent_message(alert_text)

    async def _get_latest_comment_id(self, issue_key: str, user_id: str) -> str:
        try:
            res = execute_jira_tool("JIRA_GET_ISSUE_COMMENTS", user_id, arguments={"issue_key": issue_key})
            comments = res.get("data", []) if isinstance(res, dict) else []
            if not comments: return "0"
            return str(max(int(c.get("id", 0)) for c in comments))
        except: return "0"

    async def _check_new_mentions(self, issue_key: str, last_id: str, user_id: str) -> tuple[bool, str, str]:
        """Returns (Found?, New_Max_ID, Fragment_Text)"""
        try:
            res = execute_jira_tool("JIRA_GET_ISSUE_COMMENTS", user_id, arguments={"issue_key": issue_key})
            comments = res.get("data", []) if isinstance(res, dict) else []
            
            my_info = execute_jira_tool("JIRA_GET_MY_SELF", user_id, arguments={})
            my_account_id = my_info.get("accountId", "")

            mention_found = False
            mention_text = ""
            max_id = int(last_id)

            for c in comments:
                c_id = int(c.get("id", 0))
                # Only look at comments newer than what we've seen
                if c_id > int(last_id):
                    body = c.get("body", "")
                    if my_account_id and my_account_id in body:
                        mention_found = True
                        mention_text = body[:100] + "..." # Capture snippet for the LLM
                    if c_id > max_id:
                        max_id = c_id
            
            return mention_found, str(max_id), mention_text
        except Exception as exc:
            logger.error(f"Comment check failed for {issue_key}", extra={"error": str(exc)})
            return False, last_id, ""

def get_important_issue_watcher() -> ImportantIssueWatcher:
    global _watcher_instance
    if _watcher_instance is None:
        _watcher_instance = ImportantIssueWatcher()
    return _watcher_instance

__all__ = ["ImportantIssueWatcher", "get_important_issue_watcher"]