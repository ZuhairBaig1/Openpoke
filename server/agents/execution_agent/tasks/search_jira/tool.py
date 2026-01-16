"""Jira search task implementation."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from server.config import get_settings
from server.logging_config import logger
from server.openrouter_client import request_chat_completion
from server.services.execution import get_execution_agent_logs
from server.services.jira import (
    execute_jira_tool,
    get_active_jira_user_id,
)
from .jira_internal import (
    JIRA_SEARCH_JQL_SCHEMA,
    JIRA_GET_ISSUE_SCHEMA,
    JIRA_LIST_COMMENTS_SCHEMA,
    JIRA_LIST_PROJECTS_SCHEMA,
)
from .schemas import (
    JiraSearchIssue,
    JiraSearchToolResult,
    TaskJiraSearchPayload,
    COMPLETE_TOOL_NAME,
    SEARCH_TOOL_NAME,
    TASK_TOOL_NAME,
    get_completion_schema,
)
from .system_prompt import get_system_prompt

# Constants
MAX_LLM_ITERATIONS = 10
ERROR_JIRA_NOT_CONNECTED = "Jira not connected. Please connect Jira in settings first."
ERROR_OPENROUTER_NOT_CONFIGURED = "OpenRouter API key not configured. Set OPENROUTER_API_KEY."
ERROR_EMPTY_QUERY = "search_query must not be empty"
ERROR_JQL_REQUIRED = "jql parameter is required"
ERROR_KEYS_REQUIRED = "issue_keys parameter is required"
ERROR_KEYS_MUST_BE_LIST = "issue_keys must be provided as a list"
ERROR_TOOL_ARGUMENTS_INVALID = "Tool arguments must be an object"
ERROR_ITERATION_LIMIT = "Jira search orchestrator exceeded iteration limit"

_COMPLETION_TOOL_SCHEMA = get_completion_schema()
_LOG_STORE = get_execution_agent_logs()

class JiraContentCleaner:
    """Cleans Jira text for LLM consumption, matching Gmail's EmailTextCleaner pattern."""
    def clean(self, text: Optional[str]) -> str:
        if not text: return ""
        # Remove ADF/Jira macro artifacts
        cleaned = re.sub(r'\{[^}]+\}', '', text) 
        cleaned = re.sub(r'\[~accountid:[^\]]+\]', '[User]', cleaned)
        return cleaned[:1000].strip()

_CONTENT_CLEANER = JiraContentCleaner()

# --- Standardized Helpers (Mirroring Gmail) ---

def _create_error_response(call_id: str, query: Optional[str], error: str) -> Tuple[str, str]:
    result = JiraSearchToolResult(status="error", query=query, error=error)
    return (call_id, _safe_json_dumps(result.model_dump(exclude_none=True)))

def _create_success_response(call_id: str, data: Dict[str, Any]) -> Tuple[str, str]:
    return (call_id, _safe_json_dumps(data))

def _validate_search_query(search_query: str) -> Optional[str]:
    if not (search_query or "").strip(): return ERROR_EMPTY_QUERY
    return None

def _validate_openrouter_config() -> Tuple[Optional[str], Optional[str]]:
    settings = get_settings()
    api_key = settings.openrouter_api_key
    if not api_key: return None, ERROR_OPENROUTER_NOT_CONFIGURED
    return api_key, settings.execution_agent_search_model

# --- Registry ---

def build_registry(agent_name: str) -> Dict[str, Callable[..., Any]]:
    return {
        TASK_TOOL_NAME: task_jira_search
        }

# --- Main Task Orchestrator ---

async def task_jira_search(search_query: str) -> Any:
    """Run an agentic Jira search for the provided query."""
    logger.info(f"[JIRA_SEARCH] Starting search for: '{search_query}'")
    
    cleaned_query = (search_query or "").strip()
    if error := _validate_search_query(cleaned_query):
        return {"error": error}
    
    composio_user_id = get_active_jira_user_id()
    if not composio_user_id:
        return {"error": ERROR_JIRA_NOT_CONNECTED}
    
    api_key, model_or_error = _validate_openrouter_config()
    if not api_key:
        return {"error": model_or_error}
    
    try:
        result = await _run_jira_search(
            search_query=cleaned_query,
            composio_user_id=composio_user_id,
            model=model_or_error,
            api_key=api_key,
        )
        return result
    except Exception as exc:
        logger.exception(f"[JIRA_SEARCH] Search failed: {exc}")
        return {"error": f"Jira search failed: {exc}"}

async def _run_jira_search(
    *,
    search_query: str,
    composio_user_id: str,
    model: str,
    api_key: str,
) -> List[Dict[str, Any]]:
    """Execute the main Jira search orchestration loop (The Specialist)."""
    messages: List[Dict[str, Any]] = [
        {"role": "user", "content": f"Please help me find Jira issues: {search_query}"}
    ]
    jql_queries: List[str] = []
    found_issues: Dict[str, JiraSearchIssue] = {}
    selected_keys: Optional[List[str]] = None
    
    # Internal tools provided to the specialist
    available_tools = [
        JIRA_SEARCH_JQL_SCHEMA,
        JIRA_GET_ISSUE_SCHEMA,
        JIRA_LIST_COMMENTS_SCHEMA,
        JIRA_LIST_PROJECTS_SCHEMA,
        _COMPLETION_TOOL_SCHEMA
    ]

    for iteration in range(MAX_LLM_ITERATIONS):
        response = await request_chat_completion(
            model=model,
            messages=messages,
            system=get_system_prompt(),
            api_key=api_key,
            tools=available_tools,
        )
        
        assistant = response.get("choices", [{}])[0].get("message", {})
        tool_calls = assistant.get("tool_calls") or []
        messages.append(assistant)
        
        if not tool_calls: break
        
        tool_responses, completed_keys = await _execute_tool_calls(
            tool_calls=tool_calls,
            jql_queries=jql_queries,
            found_issues=found_issues,
            composio_user_id=composio_user_id,
        )
        
        for call_id, content in tool_responses:
            messages.append({"role": "tool", "tool_call_id": call_id, "content": content})
        
        if completed_keys is not None:
            selected_keys = completed_keys
            break
    else:
        raise RuntimeError(ERROR_ITERATION_LIMIT)
    
    return _build_response(jql_queries, found_issues, selected_keys or [])

async def _execute_tool_calls(
    *,
    tool_calls: List[Dict[str, Any]],
    jql_queries: List[str],
    found_issues: Dict[str, JiraSearchIssue],
    composio_user_id: str,
) -> Tuple[List[Tuple[str, str]], Optional[List[str]]]:
    responses: List[Tuple[str, str]] = []
    completion_keys: Optional[List[str]] = None

    for call in tool_calls:
        call_id = call.get("id")
        function = call.get("function", {})
        name = function.get("name")
        arguments, parse_error = _parse_arguments(function.get("arguments", {}))

        if parse_error:
            responses.append(_create_error_response(call_id, None, parse_error))
            continue

        # 1. Handle Completion
        if name == COMPLETE_TOOL_NAME:
            keys, response_data = _handle_completion_tool(arguments)
            responses.append(_create_success_response(call_id, response_data))
            if keys is not None: completion_keys = keys

        # 2. Handle JQL Search (The SEARCH_TOOL_NAME equivalent)
        elif name == SEARCH_TOOL_NAME:
            jql = arguments.get("jql", "")
            jql_queries.append(jql)
            result_model = await _perform_jql_search(
                arguments=arguments,
                found_issues=found_issues,
                composio_user_id=composio_user_id
            )
            responses.append(_create_success_response(call_id, result_model.model_dump(exclude_none=True)))

        # 3. Handle Other Internal Tools via execute_jira_tool directly
        elif name in ["jira_get_issue", "jira_list_comments", "jira_list_projects"]:
            # Standardizing argument mapping for Composio
            if name == "jira_get_issue":
                args = {"issue_id_or_key": arguments.get("issue_key")}
            elif name == "jira_list_comments":
                args = {"issue_id_or_key": arguments.get("issue_key")}
            else: # list_projects
                args = {}

            raw_result = execute_jira_tool(name.upper(), composio_user_id, arguments=args)
            
            # If it's a get_issue call, we want to update our found_issues pool
            if name == "jira_get_issue" and "id" in raw_result:
                _map_raw_to_issue(raw_result, "direct_fetch", found_issues)
                
            responses.append(_create_success_response(call_id, raw_result))

    return responses, completion_keys

async def _perform_jql_search(
    *,
    arguments: Dict[str, Any],
    found_issues: Dict[str, JiraSearchIssue],
    composio_user_id: str,
) -> JiraSearchToolResult:
    """Executes search and maps results, mirroring Gmail's _perform_search."""
    jql = (arguments.get("jql") or "").strip()
    if not jql:
        return JiraSearchToolResult(status="error", error=ERROR_JQL_REQUIRED)

    _LOG_STORE.record_action(TASK_TOOL_NAME, description=f"Jira JQL Search: {jql}")

    try:
        raw_result = execute_jira_tool(
            "JIRA_SEARCH_ISSUES_USING_JQL",
            composio_user_id,
            arguments={"jql": jql, "maxResults": arguments.get("max_results", 10)}
        )
        
        # Handle standard Composio data wrapping
        raw_issues = raw_result.get("data", []) if isinstance(raw_result, dict) else []
        
        parsed_issues = []
        for item in raw_issues:
            issue = _map_raw_to_issue(item, jql, found_issues)
            if issue: parsed_issues.append(issue)

        return JiraSearchToolResult(
            status="success",
            query=jql,
            result_count=len(parsed_issues),
            issues=parsed_issues,
        )
    except Exception as exc:
        return JiraSearchToolResult(status="error", query=jql, error=str(exc))

def _map_raw_to_issue(item: Dict[str, Any], query: str, found_issues: Dict[str, JiraSearchIssue]) -> Optional[JiraSearchIssue]:
    """Converts raw Jira API JSON to our structured JiraSearchIssue schema."""
    fields = item.get("fields", {})
    if not fields: return None
    
    issue = JiraSearchIssue(
        id=str(item.get("id", "")),
        key=item.get("key", ""),
        query=query,
        summary=fields.get("summary", ""),
        status=fields.get("status", {}).get("name", "Unknown"),
        priority=fields.get("priority", {}).get("name"),
        type=fields.get("issuetype", {}).get("name", "Task"),
        updated=fields.get("updated"),
        description_text=_CONTENT_CLEANER.clean(fields.get("description")),
    )
    found_issues[issue.key] = issue
    return issue

def _build_response(queries: List[str], found: Dict[str, JiraSearchIssue], selected: List[str]) -> Dict[str, Any]:
    """
    Builds the final response payload.
    Uses TaskJiraSearchPayload to ensure the output structure matches the Gmail specialist.
    """
    # Deduplicate keys while maintaining order
    unique_keys = list(dict.fromkeys([k.strip() for k in selected if k and k.strip()]))
    
    # Map keys back to our rich Issue objects
    selected_issues = [found[k] for k in unique_keys if k in found]
    
    _LOG_STORE.record_action(
        TASK_TOOL_NAME, 
        description=f"{TASK_TOOL_NAME} completed | queries={len(set(queries))} | issues={len(selected_issues)}"
    )

    # Wrap the list in the Pydantic Payload model before dumping to dict
    return TaskJiraSearchPayload(issues=selected_issues).model_dump(exclude_none=True)

def _parse_arguments(raw_args: Any) -> Tuple[Dict[str, Any], Optional[str]]:
    if isinstance(raw_args, dict): return raw_args, None
    try: return json.loads(raw_args), None
    except: return {}, ERROR_TOOL_ARGUMENTS_INVALID

def _handle_completion_tool(args: Dict[str, Any]) -> Tuple[Optional[List[str]], Dict[str, Any]]:
    keys = args.get("issue_keys")
    if keys is None: return None, {"status": "error", "error": ERROR_KEYS_REQUIRED}
    if not isinstance(keys, list): return None, {"status": "error", "error": ERROR_KEYS_MUST_BE_LIST}
    clean_keys = [str(k).strip() for k in keys if str(k).strip()]
    return clean_keys, {"status": "success", "issue_keys": clean_keys}

def _safe_json_dumps(payload: Any) -> str:
    try: return json.dumps(payload, ensure_ascii=False)
    except: return json.dumps({"repr": repr(payload)})

__all__ = ["build_registry", "task_jira_search"]