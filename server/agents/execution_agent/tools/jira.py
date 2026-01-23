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
        "description": "Create a new Jira issue (Bug, Task, Story, etc.) in a specified project. Supports rich text descriptions, assignments, sprints, and custom fields.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_key": {
                    "type": "string",
                    "description": "REQUIRED. The short uppercase project code (e.g., 'PROJ')."
                    },
                "summary": {
                    "type": "string",
                    "description": "REQUIRED. A concise title for the issue."
                    },
                "issue_type": {
                    "type": "string",
                    "description": "The type of issue (e.g., 'Bug', 'Task', 'Story'). Defaults to 'Task'.",
                    "default": "Task"
                    },
                "description": {
                    "type": "string",
                    "description": "Detailed notes. Supports Markdown (auto-converted) or ADF JSON objects.",
                    "default": None
                    },
                "priority": {
                    "type": "string",
                    "description": "Priority level name (e.g., 'High', 'Medium') or ID.",
                    "default": None
                    },
                "assignee": {
                    "type": "string",
                    "description": "The Account ID of the user. Takes precedence over assignee_name.",
                    "default": None
                    },
                "assignee_name": {
                    "type": "string",
                    "description": "Email or display name of the user to assign the issue to.",
                    "default": null
                    },
                "parent": {
                    "type": "string",
                    "description": "Parent issue key or ID. REQUIRED if creating a sub-task.",
                    "default": None
                    },
                "labels": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "List of tags to categorize the issue.",
                    "default": None
                    },
                "due_date": {
                    "type": "string",
                    "description": "Expected resolution date in YYYY-MM-DD format.",
                    "default": None
                    },
                "sprint_id": {
                    "type": "integer",
                    "description": "The numeric ID of the sprint to add this issue to.",
                    "default": None
                    },
                "components": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "List of existing component IDs.",
                    "default": None
                    },
                "fix_versions": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "List of version IDs where the fix is planned.",
                    "default": None
                    },
                "versions": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "List of affected version IDs.",
                    "default": None
                    },
                "environment": {
                    "type": "string",
                    "description": "Environment details (e.g., 'Production', 'Staging'). Supports Markdown.",
                    "default": None
                    },
                "reporter": {
                    "type": "string",
                    "description": "Account ID of the reporter. Defaults to the API user.",
                    "default": None
                    },
                "additional_properties": {
                    "type": "string",
                    "description": "JSON string for custom fields. Example: '{\"customfield_10104\": 5}'.",
                    "default": None
                    }
                },
            "required": ["project_key", "summary"],
            "additionalProperties": False
            }
        }
    },
    {
    "type": "function",
    "function": {
        "name": "jira_add_comment",
        "description": "Add a new comment to a Jira issue. Supports Markdown formatting for rich text, @mentions for users, and visibility restrictions for specific roles or groups.",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_id_or_key": {
                    "type": "string",
                    "description": "The key (e.g., 'PROJ-123') or numeric ID of the issue."
                    },
                "comment": {
                    "type": "string",
                    "description": "The comment text. Use Markdown for **bold**, *italics*, `code`, and [links](url). Mention users with @username or @\"Display Name\"."
                    },
                "visibility_type": {
                    "type": "string",
                    "description": "Restrict who can see the comment. Valid values: 'group' or 'role'. If used, 'visibility_value' must also be provided.",
                    "enum": ["group", "role"],
                    "default": None
                    },
                "visibility_value": {
                    "type": "string",
                    "description": "The specific group or role name allowed to view the comment (e.g., 'Administrator', 'Developers').",
                    "default": None
                    }
                },
            "required": ["issue_id_or_key", "comment"],
            "additionalProperties": False
            }
        }
    },
    {
    "type": "function",
    "function": {
        "name": "jira_update_comment",
        "description": "Updates the text, visibility, or properties of an existing comment on a Jira issue. Can also trigger or suppress user notifications.",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_id_or_key": {
                    "type": "string",
                    "description": "The key (e.g., 'PROJ-123') or numeric ID of the Jira issue."
                    },
                "comment_id": {
                    "type": "string",
                    "description": "The unique ID of the specific comment to be updated."
                    },
                "comment_text": {
                    "type": "string",
                    "description": "The new text for the comment. Supports formatting like *bold* and @mentions (e.g., @\"John Doe\")."
                    },
                "notify_users": {
                    "type": "boolean",
                    "description": "Whether to send notifications about this update. Defaults to True.",
                    "default": True
                    },
                "visibility_type": {
                    "type": "string",
                    "description": "Restrict visibility by 'group' or 'role'. If set, visibility_value is required.",
                    "enum": ["group", "role"],
                    "default": None
                    },
                "visibility_value": {
                    "type": "string",
                    "description": "The specific name of the group or role allowed to view the comment.",
                    "default": None
                    },
                "additional_properties": {
                    "type": "string",
                    "description": "A JSON string of custom key-value pairs to store metadata against the comment. Example: '{\"internal\": true}'.",
                    "default": None
                    }
                },
            "required": ["issue_id_or_key", "comment_id", "comment_text"],
            "additionalProperties": False
            }
        }
    },
    {
    "type": "function",
    "function": {
        "name": "jira_edit_issue",
        "description": "Updates an existing Jira issue. Supports direct updates to common fields (summary, description, assignee, etc.) and a 'fields' object for custom properties.",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_id_or_key": {
                    "type": "string",
                    "description": "The unique issue key (e.g., 'PROJ-123') or numeric issue ID."
                    },
                "summary": {
                    "type": "string",
                    "description": "The new headline/title for the issue."
                    },
                "description": {
                    "type": "string",
                    "description": "The new detailed description. Supports Markdown-style formatting."
                    },
                "priority": {
                    "type": "string",
                    "description": "The priority level name (e.g., 'High', 'Medium', 'Low')."
                    },
                "assignee": {
                    "type": "string",
                    "description": "The Jira Account ID of the user to assign the issue to."
                    },
                "assignee_name": {
                    "type": "string",
                    "description": "The email or display name of the user to assign. Used if 'assignee' ID is unknown."
                    },
                "duedate": {
                    "type": "string",
                    "description": "The due date in YYYY-MM-DD format."
                    },
                "fields": {
                    "type": "object",
                    "description": "A dictionary for updating custom fields or other properties not listed above. Example: {'customfield_10001': 'Value'}.",
                    "additionalProperties": True
                    }
                },
            "required": ["issue_id_or_key"],
            "additionalProperties": False
            }
        }
    },
    {
    "type": "function",
    "function": {
        "name": "jira_transition_issue",
        "description": "Transition a Jira issue to a new status (e.g., 'To Do' -> 'Done'). It can also update the assignee, add a comment, and set additional fields or resolutions in a single operation.",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_id_or_key": {
                    "type": "string",
                    "description": "The unique issue key (e.g., 'DEV-101') or numeric issue ID."
                    },
                "transition_id_or_name": {
                    "type": "string",
                    "description": "The name of the transition (e.g., 'Done', 'In Progress') or its numeric ID."
                    },
                "comment": {
                    "type": "string",
                    "description": "Optional Markdown-supported comment explaining the status change.",
                    "default": None
                    },
                "assignee": {
                    "type": "string",
                    "description": "Optional: Account ID of the user to assign the issue to during this transition.",
                    "default": None
                    },
                "assignee_name": {
                    "type": "string",
                    "description": "Optional: Email or display name of the assignee. Used only if 'assignee' (ID) is not provided.",
                    "default": None
                    },
                "resolution": {
                    "type": "string",
                    "description": "Optional resolution (e.g., 'Fixed', 'Done'). Use only if the transition screen allows it.",
                    "default": None
                    },
                "duedate": {
                    "type": "string",
                    "description": "Optional due date in YYYY-MM-DD format.",
                    "default": None
                    },
                "additional_fields": {
                    "type": "object",
                    "description": "Dictionary of extra fields/custom fields to update after the transition. Example: {'customfield_10001': 'High Priority'}.",
                    "default": None
                    }
                },
            "required": ["issue_id_or_key", "transition_id_or_name"],
            "additionalProperties": False
            }
        }
    },
    {
    "type": "function",
    "function": {
        "name": "jira_get_transitions",
        "description": "Retrieve available workflow transitions for a Jira issue. This is essential for knowing how an issue can be moved (e.g., from 'Open' to 'Done') and what fields must be filled out to do so.",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_id_or_key": {
                    "type": "string",
                    "description": "The ID (e.g., '10000') or key (e.g., 'PROJ-123') of the Jira issue."
                    },
                "expand": {
                    "type": "string",
                    "description": "Optional expansion properties. Use 'transitions.fields' to see the specific input fields required for each transition screen.",
                    "default": None
                    },
                "transition_id": {
                    "type": "string",
                    "description": "If provided, only returns details for this specific transition ID.",
                    "default": None
                    },
                "include_unavailable_transitions": {
                    "type": "boolean",
                    "description": "If true, returns transitions that are currently hidden or blocked by workflow conditions.",
                    "default": False
                    },
                "skip_remote_only_condition": {
                    "type": "boolean",
                    "description": "If true, conditions defined by remote apps will be ignored during evaluation.",
                    "default": False
                    },
                "sort_by_ops_bar_and_status": {
                    "type": "boolean",
                    "description": "If true, transitions are sorted as they appear in the Jira UI.",
                    "default": False
                    }
                },
            "required": ["issue_id_or_key"],
            "additionalProperties": False
            }
        }
    },
    {
    "type": "function",
    "function": {
        "name": "jira_get_all_projects",
        "description": "List all Jira projects with advanced filtering, sorting, and pagination. Allows searching by name/key and expanding details like lead or issue types.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Filter by user permission level. 'view' (default) for browse/admin, 'browse' for browse only, 'edit' for admin, or 'create' for issue creation permission.",
                    "enum": ["view", "browse", "edit", "create"],
                    "default": "view"
                },
                "query": {
                    "type": "string",
                    "description": "Filter projects by a case-insensitive query string that matches the project name or key."
                    },
                "maxResults": {
                    "type": "integer",
                    "description": "The maximum number of projects to return per page (Max: 100).",
                    "default": 50
                    },
                "startAt": {
                    "type": "integer",
                    "description": "The index of the first item to return (page offset).",
                    "default": 0
                    },
                "orderBy": {
                    "type": "string",
                    "description": "Field to sort results by (e.g., 'category', 'key', 'name', 'lastIssueUpdatedTime'). Prefix with '-' for descending order.",
                    "default": "name"
                    },
                "expand": {
                    "type": "string",
                    "description": "Comma-separated list of extra attributes to include: 'description', 'issueTypes', 'lead', 'projectKeys'."
                    },
                "status": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["live", "archived", "deleted"]
                    },
                    "description": "Filter results by project status."
                        },
                "categoryId": {
                    "type": "integer",
                    "description": "The ID of the project category to filter by."
                    },
                "properties": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "List of custom project property keys to include in the response."
                    },
                "name": {
                    "type": "string",
                    "description": "DEPRECATED: Use 'query' instead. Project name or part of it to filter results."
                    }
                },
            "additionalProperties": False,
            }
        }
    },
    {
    "type": "function",
    "function": {
        "name": "jira_get_project",
        "description": "Retrieve full details for a specific Jira project, including metadata like description, lead, and issue types.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id_or_key": {
                    "type": "string",
                    "description": "The unique project key (e.g., 'PROJ') or the numeric project ID (e.g., '10000') of the project to retrieve."
                },
                "expand": {
                    "type": "string",
                    "description": "Optional comma-separated list of fields to include in the response. Available options: description, issueTypes, lead, projectKeys, issueTypeHierarchy.",
                    "default": None
                    },
                "properties": {
                    "type": "string",
                    "description": "Optional comma-separated list of project property keys to include in the response (up to 100 keys).",
                    "default": None
                    }
                },
            "required": ["project_id_or_key"],
            "additionalProperties": False
            }
        }
    },
    {
    "type": "function",
    "function": {
        "name": "jira_find_users",
        "description": "Search for Jira users by name, email address, or account ID. Essential for resolving user identities before assigning issues or adding @mentions.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A search string matched against display names or email addresses (e.g., 'John Doe' or 'john@company.com'). Required if account_id is not provided.",
                    "default": None
                    },
                "account_id": {
                    "type": "string",
                    "description": "A specific Jira account ID to retrieve details for. Required if query is not provided.",
                    "default": None
                    },
                "active": {
                    "type": "boolean",
                    "description": "Filter by status. True returns only active users, False returns only inactive users. Defaults to True if omitted.",
                    "default": True
                    },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of users to return (default 50, max 1000).",
                    "default": 50
                    },
                "start_at": {
                    "type": "integer",
                    "description": "The starting index for pagination (0-based).",
                    "default": 0
                    }
                },
            "required": [],
            "additionalProperties": False
            }
        }
    },
]

_LOG_STORE = get_execution_agent_logs()

def get_schemas() -> List[Dict[str, Any]]:
    """Return Jira tool schemas."""
    return _SCHEMAS

def _execute(tool_name: str, composio_user_id: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a Jira tool and record the action for the journal."""
    # Filter out None values so we rely on API defaults
    payload = {k: v for k, v in arguments.items() if v is not None}
    payload_str = json.dumps(payload, ensure_ascii=False, sort_keys=True) if payload else "{}"
    
    try:
        # Note: tool_name is passed exactly as defined in the schema 'name' field
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

# --- Issue Management Functions ---

def jira_create_issue(
    project_key: str,
    summary: str,
    issue_type: str = "Task",
    description: Optional[str] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    assignee_name: Optional[str] = None,
    parent: Optional[str] = None,
    labels: Optional[List[str]] = None,
    due_date: Optional[str] = None,
    sprint_id: Optional[int] = None,
    components: Optional[List[str]] = None,
    fix_versions: Optional[List[str]] = None,
    versions: Optional[List[str]] = None,
    environment: Optional[str] = None,
    reporter: Optional[str] = None,
    additional_properties: Optional[str] = None
) -> Dict[str, Any]:
    arguments = {
        "project_key": project_key,
        "summary": summary,
        "issue_type": issue_type,
        "description": description,
        "priority": priority,
        "assignee": assignee,
        "assignee_name": assignee_name,
        "parent": parent,
        "labels": labels,
        "due_date": due_date,
        "sprint_id": sprint_id,
        "components": components,
        "fix_versions": fix_versions,
        "versions": versions,
        "environment": environment,
        "reporter": reporter,
        "additional_properties": additional_properties
    }
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected."}
    return _execute("jira_create_issue", uid, arguments)

def jira_edit_issue(
    issue_id_or_key: str,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    assignee_name: Optional[str] = None,
    duedate: Optional[str] = None,
    fields: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    arguments = {
        "issue_id_or_key": issue_id_or_key,
        "summary": summary,
        "description": description,
        "priority": priority,
        "assignee": assignee,
        "assignee_name": assignee_name,
        "duedate": duedate,
        "fields": fields
    }
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected."}
    return _execute("jira_edit_issue", uid, arguments)

def jira_transition_issue(
    issue_id_or_key: str,
    transition_id_or_name: str,
    comment: Optional[str] = None,
    assignee: Optional[str] = None,
    assignee_name: Optional[str] = None,
    resolution: Optional[str] = None,
    duedate: Optional[str] = None,
    additional_fields: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    arguments = {
        "issue_id_or_key": issue_id_or_key,
        "transition_id_or_name": transition_id_or_name,
        "comment": comment,
        "assignee": assignee,
        "assignee_name": assignee_name,
        "resolution": resolution,
        "duedate": duedate,
        "additional_fields": additional_fields
    }
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected."}
    return _execute("jira_transition_issue", uid, arguments)

def jira_get_transitions(
    issue_id_or_key: str,
    expand: Optional[str] = None,
    transition_id: Optional[str] = None,
    include_unavailable_transitions: bool = False,
    skip_remote_only_condition: bool = False,
    sort_by_ops_bar_and_status: bool = False
) -> Dict[str, Any]:
    arguments = {
        "issue_id_or_key": issue_id_or_key,
        "expand": expand,
        "transition_id": transition_id,
        "include_unavailable_transitions": include_unavailable_transitions,
        "skip_remote_only_condition": skip_remote_only_condition,
        "sort_by_ops_bar_and_status": sort_by_ops_bar_and_status
    }
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected."}
    return _execute("jira_get_transitions", uid, arguments)

# --- Comment Functions ---

def jira_add_comment(
    issue_id_or_key: str,
    comment: str,
    visibility_type: Optional[str] = None,
    visibility_value: Optional[str] = None
) -> Dict[str, Any]:
    arguments = {
        "issue_id_or_key": issue_id_or_key,
        "comment": comment,
        "visibility_type": visibility_type,
        "visibility_value": visibility_value
    }
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected."}
    return _execute("jira_add_comment", uid, arguments)

def jira_update_comment(
    issue_id_or_key: str,
    comment_id: str,
    comment_text: str,
    notify_users: bool = True,
    visibility_type: Optional[str] = None,
    visibility_value: Optional[str] = None,
    additional_properties: Optional[str] = None
) -> Dict[str, Any]:
    arguments = {
        "issue_id_or_key": issue_id_or_key,
        "comment_id": comment_id,
        "comment_text": comment_text,
        "notify_users": notify_users,
        "visibility_type": visibility_type,
        "visibility_value": visibility_value,
        "additional_properties": additional_properties
    }
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected."}
    return _execute("jira_update_comment", uid, arguments)

# --- Project & User Discovery ---

def jira_get_all_projects(
    action: str = "view",
    query: Optional[str] = None,
    maxResults: int = 50,
    startAt: int = 0,
    orderBy: str = "name",
    expand: Optional[str] = None,
    status: Optional[List[str]] = None,
    categoryId: Optional[int] = None,
    properties: Optional[List[str]] = None,
    name: Optional[str] = None
) -> Dict[str, Any]:
    arguments = {
        "action": action,
        "query": query,
        "maxResults": maxResults,
        "startAt": startAt,
        "orderBy": orderBy,
        "expand": expand,
        "status": status,
        "categoryId": categoryId,
        "properties": properties,
        "name": name
    }
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected."}
    return _execute("jira_get_all_projects", uid, arguments)

def jira_get_project(
    project_id_or_key: str,
    expand: Optional[str] = None,
    properties: Optional[str] = None
) -> Dict[str, Any]:
    arguments = {
        "project_id_or_key": project_id_or_key,
        "expand": expand,
        "properties": properties
    }
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected."}
    return _execute("jira_get_project", uid, arguments)

def jira_find_users(
    query: Optional[str] = None,
    account_id: Optional[str] = None,
    active: bool = True,
    max_results: int = 50,
    start_at: int = 0
) -> Dict[str, Any]:
    arguments = {
        "query": query,
        "account_id": account_id,
        "active": active,
        "max_results": max_results,
        "start_at": start_at
    }
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected."}
    return _execute("jira_find_users", uid, arguments)

def build_registry(agent_name: str) -> Dict[str, Callable[..., Any]]:
    return {
        "jira_create_issue": jira_create_issue,
        "jira_add_comment": jira_add_comment,
        "jira_update_comment": jira_update_comment,
        "jira_edit_issue": jira_edit_issue,
        "jira_transition_issue": jira_transition_issue,
        "jira_get_transitions": jira_get_transitions,
        "jira_get_all_projects": jira_get_all_projects,
        "jira_get_project": jira_get_project,
        "jira_find_users": jira_find_users,
    }

__all__ = ["build_registry", "get_schemas"]