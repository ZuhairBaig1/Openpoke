"""Jira tool schemas and actions for the execution agent."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from server.services.execution import get_execution_agent_logs
from server.services.jira import execute_jira_tool, get_active_jira_user_id

_JIRA_AGENT_NAME = "jira-execution-agent"

_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "jira_create_issue",
            "description": "Create a new Jira issue (Bug, Task, Story, etc.) in a specific project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_key": {"type": "string", "description": "The shorthand key for the project (e.g., 'PROJ')."},
                    "summary": {"type": "string", "description": "The title of the issue."},
                    "issue_type": {"type": "string", "description": "The type of issue (e.g., 'Bug', 'Task')."},
                    "description": {"type": "string", "description": "Detailed description of the issue."},
                },
                "required": ["project_key", "summary", "issue_type"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jira_add_comment",
            "description": "Add a new comment to an existing Jira issue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "The issue key (e.g., 'PROJ-123')."},
                    "body": {"type": "string", "description": "The text content of the comment."},
                },
                "required": ["issue_key", "body"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jira_update_issue",
            "description": "Update fields (priority, summary, assignee, due date) of an existing Jira issue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "The issue key (e.g., 'PROJ-123')."},
                    "fields": {
                        "type": "object", 
                        "description": (
                            "A dictionary of fields to update. "
                            "IMPORTANT FORMATTING RULES:\n"
                            "1. 'duedate': Use a simple string 'YYYY-MM-DD'.\n"
                            "2. 'priority': Use an object {'name': 'High'}.\n"
                            "3. 'assignee': Use an object {'id': 'accountId'}.\n"
                            "4. 'summary': Use a simple string."
                        )
                    },
                },
                "required": ["issue_key", "fields"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jira_transition_issue",
            "description": "Move a Jira issue to a new status (e.g., 'Done', 'In Progress').",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "The issue key (e.g., 'PROJ-123')."},
                    "transition": {"type": "string", "description": "The name or ID of the transition."},
                },
                "required": ["issue_key", "transition"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jira_get_available_transitions",
            "description": "Get a list of valid transitions (next possible statuses) for a specific issue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "The issue key (e.g., 'PROJ-123')."},
                },
                "required": ["issue_key"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jira_list_projects",
            "description": "List all Jira projects available to the authenticated user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recent": {"type": "integer", "description": "Optional: only return this many recently viewed projects."},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jira_get_project_details",
            "description": "Get detailed metadata about a specific project, including valid issue types.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id_or_key": {"type": "string", "description": "The project key or ID."},
                },
                "required": ["project_id_or_key"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jira_find_user",
            "description": "Search for Jira users by name or email to retrieve their accountId for assignments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The name or email of the user to search for."},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
]

_LOG_STORE = get_execution_agent_logs()

def get_schemas() -> List[Dict[str, Any]]:
    """Return Jira tool schemas."""
    return _SCHEMAS

def _execute(tool_name: str, composio_user_id: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a Jira tool and record the action for the journal."""
    payload = {k: v for k, v in arguments.items() if v is not None}
    payload_str = json.dumps(payload, ensure_ascii=False, sort_keys=True) if payload else "{}"
    try:
        result = execute_jira_tool(tool_name, composio_user_id, arguments=payload)
    except Exception as exc:
        _LOG_STORE.record_action(
            _JIRA_AGENT_NAME,
            description=f"{tool_name} failed | args={payload_str} | error={exc}",
        )
        raise

    _LOG_STORE.record_action(
        _JIRA_AGENT_NAME,
        description=f"{tool_name} succeeded | args={payload_str}",
    )
    return result

def jira_create_issue(project_key: str, summary: str, issue_type: str, description: Optional[str] = None) -> Dict[str, Any]:
    arguments = {"project_key": project_key, "summary": summary, "issue_type": issue_type, "description": description}
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected."}
    return _execute("JIRA_CREATE_ISSUE", uid, arguments)

def jira_add_comment(issue_key: str, body: str) -> Dict[str, Any]:
    arguments = {"issue_key": issue_key, "body": body}
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected."}
    return _execute("JIRA_ADD_COMMENT", uid, arguments)

def jira_update_issue(issue_key: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    arguments = {"issue_key": issue_key, "fields": fields}
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected."}
    return _execute("JIRA_UPDATE_ISSUE", uid, arguments)

def jira_transition_issue(issue_key: str, transition: str) -> Dict[str, Any]:
    arguments = {"issue_key": issue_key, "transition": transition}
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected."}
    return _execute("JIRA_TRANSITION_ISSUE", uid, arguments)

def jira_get_available_transitions(issue_key: str) -> Dict[str, Any]:
    arguments = {"issue_id_or_key": issue_key}
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected."}
    return _execute("JIRA_GET_ISSUE_TRANSITIONS", uid, arguments)

def jira_list_projects(recent: Optional[int] = None) -> Dict[str, Any]:
    arguments = {"recent": recent}
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected."}
    return _execute("JIRA_LIST_PROJECTS", uid, arguments)

def jira_get_project_details(project_id_or_key: str) -> Dict[str, Any]:
    arguments = {"project_id_or_key": project_id_or_key}
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected."}
    return _execute("JIRA_GET_PROJECT", uid, arguments)

def jira_find_user(query: str) -> Dict[str, Any]:
    arguments = {"query": query}
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected."}
    return _execute("JIRA_SEARCH_USERS", uid, arguments)

def build_registry(agent_name: str) -> Dict[str, Callable[..., Any]]:
    return {
        "jira_create_issue": jira_create_issue,
        "jira_add_comment": jira_add_comment,
        "jira_update_issue": jira_update_issue,
        "jira_transition_issue": jira_transition_issue,
        "jira_get_available_transitions": jira_get_available_transitions,
        "jira_list_projects": jira_list_projects,
        "jira_get_project_details": jira_get_project_details,
        "jira_find_user": jira_find_user,
    }

__all__ = ["build_registry", "get_schemas"]