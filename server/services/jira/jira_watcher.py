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

class JiraWatcher:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._issue_enabled_dict: Dict[str, bool] = {}
        self._issue_update_dict: Dict[str, bool] = {}
        self.project_enabled: bool = False

    async def start_project_trigger(self) -> None:
        async with self._lock:
            if self.project_enabled:
                return
            
            user_id = get_active_jira_user_id()
            if not user_id:
                logger.warning("Jira not connected; skipping trigger registration, in jira_watcher.py")
                return

            try:
                result = enable_jira_trigger(
                    "JIRA_NEW_PROJECT_TRIGGER",
                    user_id,
                    arguments=None
                )

                normalized = normalize_trigger_response(result)
                
                if normalized.get("status") in ["ENABLED", "active", "SUCCESS"]:
                    self.project_enabled = True
                    logger.info("Jira project trigger registered successfully, in jira_watcher.py")
            except Exception as e:
                logger.error(f"Failed to register jira project trigger: {e}, in jira_watcher.py")

    async def start_issue_trigger(self, project_key: str) -> None:
        async with self._lock:
            if self._issue_enabled_dict.get(project_key):
                return
            
            user_id = get_active_jira_user_id()
            if not user_id:
                logger.warning("Jira not connected; skipping trigger registration. in jira_watcher.py")
                return

            try:
                result = enable_jira_trigger(
                    "JIRA_NEW_ISSUE_TRIGGER",
                    user_id,
                    arguments={"project_key": project_key}
                )
                
                normalized = normalize_trigger_response(result)
                
                if normalized.get("status") in ["ENABLED", "active", "SUCCESS"]:
                    self._issue_enabled_dict[project_key] = True
                    logger.info(f"Jira new issue trigger registered successfully for project {project_key}. in jira_watcher.py")
            except Exception as e:
                logger.error(f"Failed to register jira issue trigger, in jira_watcher.py: {e}")


    async def start_update_issue_trigger(self, project_key: str) -> None:
        async with self._lock:
            if self._issue_update_dict.get(project_key):
                return
            
            user_id = get_active_jira_user_id()
            if not user_id:
                logger.warning("Jira not connected; skipping trigger registration, in jira_watcher.py")
                return

            try:
                result = enable_jira_trigger(
                    "JIRA_UPDATED_ISSUE_TRIGGER",
                    user_id,
                    arguments={"project_key": project_key}
                )
                
                normalized = normalize_trigger_response(result)
                
                if normalized.get("status") in ["ENABLED", "active", "SUCCESS"]:
                    self._issue_update_dict[project_key] = True
                    logger.info(f"Jira issue update trigger registered successfully for project {project_key}, in jira_watcher.py")
            except Exception as e:
                logger.error(f"Failed to update jira issue trigger, in jira_watcher.py: {e}")



    async def process_project_payload(self, payload: Dict[str, Any]) -> None:
        data = normalize_trigger_response(payload)
        project = build_processed_event(data)
        
        if not project:
            logger.warning(f"Unknown jira project trigger payload: {data},  in jira_watcher.py")
            return

        logger.info(f"New Jira Project Created: {project.title},  in jira_watcher.py")
        
        alert_text = format_event_alert(project)
        runtime = resolve_interaction_runtime()
        await runtime.handle_agent_message(alert_text)

        await self.start_issue_trigger(project.key)
        await self.start_update_issue_trigger(project.key)

    async def process_issue_payload(self, payload: Dict[str, Any]) -> None:
        data = normalize_trigger_response(payload)
        issue = build_processed_event(data)
        
        if not issue:
            logger.warning(f"Unknown jira issue trigger payload: {data},  in jira_watcher.py")
            return

        logger.info(f"New Jira Issue Created: {issue.title},  in jira_watcher.py")
        
        alert_text = format_event_alert(issue)
        runtime = resolve_interaction_runtime()
        await runtime.handle_agent_message(alert_text)

    async def process_update_payload(self, payload: Dict[str, Any]) -> None:
        data = normalize_trigger_response(payload)
        updated_issue = build_processed_event(data)
        
        if not updated_issue:
            logger.warning(f"Unknown jira issue trigger payload: {data},  in jira_watcher.py")
            return

        logger.info(f"New Jira Issue Updated: {updated_issue.title},  in jira_watcher.py")
        
        alert_text = format_event_alert(updated_issue)
        runtime = resolve_interaction_runtime()
        await runtime.handle_agent_message(alert_text)

_jira_watcher_instance: Optional["JiraWatcher"] = None

def get_jira_watcher() -> JiraWatcher:
    global _jira_watcher_instance
    if _jira_watcher_instance is None:
        _jira_watcher_instance = JiraWatcher()
    return _jira_watcher_instance

__all__ = ["JiraWatcher", "get_jira_watcher"]