import asyncio
from typing import Any, Dict, Optional, TYPE_CHECKING
from .client import enable_jira_trigger, get_active_jira_user_id, normalize_trigger_response, execute_jira_tool
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

    async def start_project_trigger(self, user_id: str) -> None:
        async with self._lock:
            if self.project_enabled:
                return
            
            if not user_id:
                logger.warning("No user_id provided; skipping trigger registration in jira_watcher.py")
                return

            try:
                logger.info(f"Registering JIRA_NEW_PROJECT_TRIGGER for user: {user_id}")
                result = enable_jira_trigger(
                    "JIRA_NEW_PROJECT_TRIGGER",
                    user_id,
                    arguments=None
                )

                normalized = normalize_trigger_response(result)
                logger.info(f"Jira project trigger registration result: {result}")
                
                if normalized.get("status") in ["ENABLED", "active", "SUCCESS"] or normalized.get("trigger_id"):
                    self.project_enabled = True
                    logger.info("Jira project trigger registered successfully, in jira_watcher.py")
                else:
                    logger.error(f"Jira project trigger NOT enabled. Status: {normalized.get('status')}")
            except Exception as e:
                logger.error(f"Failed to register jira project trigger: {e}, in jira_watcher.py")

    async def start_issue_trigger(self, project_key: str, user_id: str) -> None:
        async with self._lock:
            if self._issue_enabled_dict.get(project_key):
                return
            
            if not user_id:
                logger.warning(f"No user_id provided; skipping issue trigger registration for {project_key}")
                return

            try:
                logger.info(f"Registering JIRA_NEW_ISSUE_TRIGGER for {project_key} (user: {user_id})")
                result = enable_jira_trigger(
                    "JIRA_NEW_ISSUE_TRIGGER",
                    user_id,
                    arguments={"project_key": project_key}
                )
                
                normalized = normalize_trigger_response(result)
                logger.info(f"Jira issue trigger registration result for {project_key}: {result}")
                
                if normalized.get("status") in ["ENABLED", "active", "SUCCESS"] or normalized.get("trigger_id"):
                    self._issue_enabled_dict[project_key] = True
                    logger.info(f"Jira new issue trigger registered successfully for project {project_key}. in jira_watcher.py")
                else:
                    logger.error(f"Jira issue trigger NOT enabled for {project_key}. Status: {normalized.get('status')}")
            except Exception as e:
                logger.error(f"Failed to register jira issue trigger, in jira_watcher.py: {e}")


    async def start_update_issue_trigger(self, project_key: str, user_id: str) -> None:
        async with self._lock:
            if self._issue_update_dict.get(project_key):
                return
            
            if not user_id:
                logger.warning(f"No user_id provided; skipping update trigger registration for {project_key}")
                return

            try:
                logger.info(f"Registering JIRA_UPDATED_ISSUE_TRIGGER for {project_key} (user: {user_id})")
                result = enable_jira_trigger(
                    "JIRA_UPDATED_ISSUE_TRIGGER",
                    user_id,
                    arguments={"project_key": project_key}
                )
                
                normalized = normalize_trigger_response(result)
                
                if normalized.get("status") in ["ENABLED", "active", "SUCCESS"] or normalized.get("trigger_id"):
                    self._issue_update_dict[project_key] = True
                    logger.info(f"Jira issue update trigger registered successfully for project {project_key}, in jira_watcher.py")
            except Exception as e:
                logger.error(f"Failed to update jira issue trigger, in jira_watcher.py: {e}")



    async def ensure_all_triggers_initialized(self, user_id: str) -> None:
        """
        Ensures that the project trigger and issue triggers for all existing projects are started.
        This is called after a successful OAuth connection is detected.
        """
        # 1. Start Project Trigger
        await self.start_project_trigger(user_id)

        # 2. Get all projects and start issue/update triggers for each
        try:
            logger.info(f"Fetching all projects to initialize triggers for user: {user_id}")
            all_active_projects = execute_jira_tool(
                "JIRA_GET_ALL_PROJECTS",
                user_id,
                arguments={
                    "maxResults": 100,
                    "startAt": 0,
                    "orderBy": "name"
                }
            )
            
            # The structure of Composio response for JIRA_GET_ALL_PROJECTS:
            # result['data'] usually contains the actual response from Jira
            data = all_active_projects.get("data", {})
            if isinstance(data, list):
                project_list = data
            elif isinstance(data, dict):
                # Sometimes it might be wrapped in another 'data' or 'values' key
                project_list = data.get("data", {}).get("values", []) or data.get("values", []) or []
            else:
                project_list = []
 
            logger.info(f"Found {len(project_list)} projects to initialize: {[p.get('key') for p in project_list]}")
 
            for project in project_list:
                project_key = project.get("key")
                if project_key:
                    logger.info(f"Auto-starting triggers for project: {project_key}")
                    await self.start_issue_trigger(project_key, user_id)
                    await self.start_update_issue_trigger(project_key, user_id)
                    
        except Exception as e:
            logger.error(f"Failed to initialize all jira triggers: {e}", exc_info=True)



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

        # Use the global user id if available
        user_id = get_active_jira_user_id() or ""

        await self.start_issue_trigger(project.key, user_id)
        await self.start_update_issue_trigger(project.key, user_id)

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