import asyncio
from datetime import datetime
from typing import Any, Dict, Optional, TYPE_CHECKING
from .client import enable_jira_trigger, get_active_jira_user_id, normalize_trigger_response
from .processing import build_processed_event, format_event_alert
from ...logging_config import logger

if TYPE_CHECKING:
    from ...agents.interaction_agent.runtime import InteractionAgentRuntime

def resolve_interaction_runtime() -> "InteractionAgentRuntime":
    from ...agents.interaction_agent.runtime import InteractionAgentRuntime
    return InteractionAgentRuntime()

class CalendarWatcher:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._project_enabled = False
        self._issue_enabled = False

    async def start_project_trigger(self) -> None:
        async with self._lock:
            if self._project_enabled:
                return
            
            user_id = get_active_jira_user_id()
            if not user_id:
                logger.warning("Jira not connected; skipping trigger registration.")
                return

            try:
                result = enable_jira_trigger(
                    "JIRA_NEW_PROJECT_TRIGGER",
                    user_id,
                    arguments=None
                )
                
                normalized = normalize_trigger_response(result)
                
                if normalized.get("status") in ["ENABLED", "active", "SUCCESS"]:
                    self._project_enabled = True
                    logger.info("Jira project trigger registered successfully.")
            except Exception as e:
                logger.error(f"Failed to register jira project trigger: {e}")

    async def start_issue_trigger(self, project_key: str) -> None:
        async with self._lock:
            if self._issue_enabled:
                return
            
            user_id = get_active_jira_user_id()
            if not user_id:
                logger.warning("Jira not connected; skipping trigger registration.")
                return

            try:
                result = enable_jira_trigger(
                    "JIRA_NEW_ISSUE_TRIGGER",
                    user_id,
                    arguments={"project_key": project_key}
                )
                
                normalized = normalize_trigger_response(result)
                
                if normalized.get("status") in ["ENABLED", "active", "SUCCESS"]:
                    self._issue_enabled = True
                    logger.info("Jira issue trigger registered successfully.")
            except Exception as e:
                logger.error(f"Failed to register jira issue trigger: {e}")

_calendar_watcher_instance: Optional["CalendarWatcher"] = None

async def process_event(payload: Dict[str, Any]) -> None:
    data = normalize_trigger_response(payload)
    project = build_processed_event(data)
    
    if not project:
        logger.warning(f"Unknown jira project trigger payload: {data}")
        return

    logger.info(f"New Jira Project Created: {project.name}")
    
    alert_text = format_event_alert(project)
    runtime = resolve_interaction_runtime()
    await runtime.handle_agent_message(alert_text)

    new_issue_trigger = CalendarWatcher()
    await new_issue_trigger.start_issue_trigger(project.key)

async def process_issue_event(payload: Dict[str, Any]) -> None:
    data = normalize_trigger_response(payload)
    issue = build_processed_event(data)
    
    if not issue:
        logger.warning(f"Unknown jira issue trigger payload: {data}")
        return

    logger.info(f"New Jira Issue Created: {issue.name}")
    
    alert_text = format_event_alert(issue)
    runtime = resolve_interaction_runtime()
    await runtime.handle_agent_message(alert_text)

def get_calendar_watcher() -> CalendarWatcher:
    global _calendar_watcher_instance
    if _calendar_watcher_instance is None:
        _calendar_watcher_instance = CalendarWatcher()
    return _calendar_watcher_instance

__all__ = ["CalendarWatcher", "get_calendar_watcher"]