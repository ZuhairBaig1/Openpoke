"""Jira tool schemas and actions for the execution agent."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from server.services.execution import get_execution_agent_logs
from server.services.jira import execute_jira_tool, get_active_jira_user_id
from server.services.jira.processing import (
    JiraContentCleaner,
    build_processed_issue,
    parse_jira_search_response,
)
from server.logging_config import logger

_JIRA_AGENT_NAME = "jira-execution-agent"

_CONTENT_CLEANER = JiraContentCleaner()

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
                    "default": None
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
                    "description": "The comment text. Use Markdown for **bold**, *italics*, `code`, and [links](url). Mention users with @username or @\"Display Name\". DO NOT USE HTML TAGS (e.g. `<a>`, `<br>`)."
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
                    "description": "The new text for the comment. Supports formatting like *bold* and @mentions (e.g., @\"John Doe\"). DO NOT USE HTML TAGS (e.g. `<a>`, `<br>`)."
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
    {
    "type": "function",
    "function": {
        "name": "jira_search_for_issues_using_jql_post",
        "description": "Request model for enhanced JQL issue search via POST to /rest/api/3/search/jql. Supports eventual-consistency and pagination with nextPageToken. NOTE: This action is for Jira Cloud only.",
        "parameters": {
            "type": "object",
            "properties": {
                "jql": {
                    "type": "string",
                    "description": "The JQL (Jira Query Language) query string to use for the search. Must be bounded (e.g., 'project = KAN'). Provide either this 'jql' (for the first page) or 'nextPageToken'."
                },
                "nextPageToken": {
                    "type": "string",
                    "description": "Opaque token received from a previous response to continue pagination. Tokens expire quickly."
                },
                "max_results": {
                    "type": "integer",
                    "description": "The maximum number of issues to return per page."
                },
                "fields": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "A list of fields to return for each issue (e.g., 'summary', 'status', 'assignee', '*navigable')."
                },
                "expand": {
                    "type": "string",
                    "description": "A comma-separated list of entities to expand in the response (e.g., 'names', 'schema', 'transitions')."
                },
                "properties": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "A list of issue property keys to return for each issue."
                },
                "fields_by_keys": {
                    "type": "boolean",
                    "description": "If true, treats values in 'fields' as keys (e.g., 'customfield_10000')."
                },
                "reconcileIssues": {
                    "type": "array",
                    "items": {
                        "type": "integer"
                    },
                    "description": "List of issue IDs to reconcile for read-after-write consistency (maximum 50)."
                }
            },
            "required": [],
            "additionalProperties": False
        }
    }
},
{
"type": "function",
    "function": {
        "name": "jira_get_issue",
        "description": "Retrieve the full details of a specific Jira issue by its key or ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_id_or_key": {
                    "type": "string",
                    "description": "The unique key (e.g., 'PROJ-123') or numeric ID (e.g., '10000') of the issue to retrieve."
                },
                "expand": {
                    "type": "string",
                    "description": "Comma-separated list of extra sections to include. Use 'changelog' for history, 'renderedFields' for HTML, 'transitions' for workflow options."
                },
                "fields": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "List of specific field names or IDs to return (e.g., ['summary', 'status', 'assignee']). Leaving this empty returns all standard fields."
                },
                "fields_by_keys": {
                    "type": "boolean",
                    "description": "Set to True if the items in 'fields' are names (like 'summary') rather than internal IDs. Default is False.",
                    "default": False
                },
                "properties": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "List of specific issue property keys (metadata) to retrieve."
                },
                "update_history": {
                    "type": "boolean",
                    "description": "If True, this view will be added to the user's 'Recently Viewed' history in Jira. Default is False.",
                    "default": False
                }
            },
            "required": [
                "issue_id_or_key"
            ],
            "additionalProperties": False
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "jira_list_issue_comments",
        "description": "Retrieve all comments from a specific Jira issue, sorted by creation date.",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_id_or_key": {
                    "type": "string",
                    "description": "The unique key (e.g., 'PROJ-123') or numeric ID (e.g., '10000') of the Jira issue."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of comments to return per page. Jira limits this to ~100. Default is 50.",
                    "default": 50,
                    "maximum": 100
                },
                "start_at": {
                    "type": "integer",
                    "description": "The index of the first comment to return (0-based). Use for pagination.",
                    "default": 0
                },
                "order_by": {
                    "type": "string",
                    "description": "Sort order for comments. Currently only supports 'created' (oldest to newest).",
                    "enum": ["created"]
                },
                "expand": {
                    "type": "string",
                    "description": "Use 'renderedBody' to include the HTML formatted version of the comment text.",
                    "enum": ["renderedBody"]
                }
            },
            "required": [
                "issue_id_or_key"
            ],
            "additionalProperties": False
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "jira_delete_comment",
        "description": "Delete a specific comment from a Jira issue using the issue key/ID and the comment ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "issueIdOrKey": {
                    "type": "string",
                    "description": "The ID (e.g., '10000') or key (e.g., 'PROJ-123') of the Jira issue from which the comment will be deleted."
                },
                "id": {
                    "type": "string",
                    "description": "The unique identifier of the comment to be deleted (e.g., '10001')."
                }
            },
            "required": [
                "issueIdOrKey",
                "id"
            ],
            "additionalProperties": False
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "jira_get_current_user",
        "description": "Retrieve details of the currently authenticated Jira user, optionally expanding specific properties like groups or application roles.",
        "parameters": {
            "type": "object",
            "properties": {
                "expand": {
                    "type": "string",
                    "description": "Comma-separated list of user properties to expand (e.g., 'groups,applicationRoles')."
                }
            },
            "required": [],
            "additionalProperties": False
        }
    }
}
]

_LOG_STORE = get_execution_agent_logs()

def get_schemas() -> List[Dict[str, Any]]:
    """Return Jira tool schemas."""
    return _SCHEMAS

def _execute(tool_name: str, composio_user_id: str, arguments: Dict[str, Any], version: Optional[str] = None) -> Dict[str, Any]:
    payload = {k: v for k, v in arguments.items() if v is not None}
    payload_str = json.dumps(payload, ensure_ascii=False, sort_keys=True) if payload else "{}"
    
    try:
        logger.info(f"PASSING ARGUMENTS TO EXECUTE JIRA TOOL: tool_name={tool_name}, composio_user_id={composio_user_id}, version={version}, arguments={payload}")
        result = execute_jira_tool(tool_name, composio_user_id, arguments=payload, version=version)
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
    logger.info(f"Active Jira user ID: {uid}, being passed to jira_create_issue")
    return _execute("jira_create_issue", uid, arguments, version="20260203_00")

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
    logger.info(f"Active Jira user ID: {uid}, being passed to jira_edit_issue")
    return _execute("jira_edit_issue", uid, arguments, version="20260203_00")

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
    logger.info(f"Active Jira user ID: {uid}, being passed to jira_transition_issue")
    return _execute("jira_transition_issue", uid, arguments, version="20260203_00")

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
    logger.info(f"Active Jira user ID: {uid}, being passed to jira_get_transitions")
    return _execute("jira_get_transitions", uid, arguments, version="20260203_00")

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
    logger.info(f"Active Jira user ID: {uid}, being passed to jira_add_comment")
    return _execute("jira_add_comment", uid, arguments, version="20260203_00")

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
    logger.info(f"Active Jira user ID: {uid}, being passed to jira_update_comment")
    return _execute("jira_update_comment", uid, arguments, version="20260203_00")

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
    logger.info(f"Active Jira user ID: {uid}, being passed to jira_get_all_projects")
    return _execute("jira_get_all_projects", uid, arguments, version="20260203_00")

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
    logger.info(f"Active Jira user ID: {uid}, being passed to jira_get_project")
    return _execute("jira_get_project", uid, arguments, version="20260203_00")

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
    logger.info(f"Active Jira user ID: {uid}, being passed to jira_find_users")
    return _execute("jira_find_users", uid, arguments, version="20260203_00")

def jira_search_for_issues_using_jql_post(
    jql: Optional[str] = None,
    next_page_token: Optional[str] = None,
    max_results: Optional[int] = None,
    fields: Optional[List[str]] = None,
    expand: Optional[str] = None,
    properties: Optional[List[str]] = None,
    fields_by_keys: bool = False,
    reconcile_issues: Optional[List[int]] = None,
) -> Dict[str, Any]:
    # If no fields are provided, default to a robust set to avoid empty payloads
    if not fields:
        fields = ["summary", "status", "assignee", "project", "key", "issuetype", "priority", "updated", "description", "reporter", "labels", "duedate", "browser_url"]

    arguments: Dict[str, Any] = {
        "jql": jql,
        "nextPageToken": next_page_token,
        "max_results": max_results,
        "fields": fields,
        "expand": expand,
        "properties": properties,
        "fields_by_keys": fields_by_keys,
        "reconcileIssues": reconcile_issues,
    }
    
    arguments = {k: v for k, v in arguments.items() if v is not None}

    logger.info(f"jira_search_for_issues_using_jql_post called. JQL provided: {bool(jql)}, Token provided: {bool(next_page_token)}")
    uid = get_active_jira_user_id()
    if not uid:
        return {"error": "Jira not connected. Please connect Jira in settings first."}
    
    logger.info(f"Arguments for jira_search_for_issues_using_jql_post: {arguments}")
    
    raw_result = _execute("JIRA_SEARCH_FOR_ISSUES_USING_JQL_POST", uid, arguments, version="20260203_00")

    processed_issues = parse_jira_search_response(raw_result, jql or "Search", cleaner=_CONTENT_CLEANER)
    
    data = raw_result.get("data", {}) if isinstance(raw_result, dict) else {}
    return {
        "issues": [issue.__dict__ for issue in processed_issues],
        "next_page_token": data.get("nextPageToken"),
        "is_last_page": data.get("isLast")
    }


def jira_get_issue(
    issue_id_or_key: str,
    expand: Optional[str] = None,
    fields: Optional[List[str]] = None,
    fields_by_keys: bool = False,
    properties: Optional[List[str]] = None,
    update_history: bool = False,
) -> Dict[str, Any]:
    # If no fields are provided, default to a robust set to avoid empty payloads
    if not fields:
        fields = ["summary", "status", "assignee", "project", "key", "issuetype", "priority", "updated", "description", "reporter", "labels", "duedate", "browser_url"]

    arguments: Dict[str, Any] = {
        "issue_id_or_key": issue_id_or_key,
        "expand": expand,
        "fields": fields,
        "fields_by_keys": fields_by_keys,
        "properties": properties,
        "update_history": update_history,
    }
    
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected. Please connect Jira in settings first."}

    logger.info(f"Arguments for jira_get_issue: {arguments}")
    raw_result = _execute("JIRA_GET_ISSUE", uid, arguments, version="20260203_00")
    
    if not isinstance(raw_result, dict):
        return {"error": "Unexpected response format from Jira."} # Added this line for error handling
    # Composio usually returns issue data directly or under "data"
    issue_data = raw_result.get("data", raw_result) if isinstance(raw_result, dict) else {}
    processed = build_processed_issue(issue_data, "", cleaner=_CONTENT_CLEANER)
    
    if processed:
        return processed.__dict__
    return raw_result



def jira_list_issue_comments(
    issue_id_or_key: str,
    max_results: int = 50,
    start_at: int = 0,
    order_by: Optional[str] = None,
    expand: Optional[str] = None,
) -> Dict[str, Any]:

    arguments: Dict[str, Any] = {
        "issue_id_or_key": issue_id_or_key,
        "max_results": max_results,
        "start_at": start_at,
        "order_by": order_by,
        "expand": expand,
    }

    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected. Please connect Jira in settings first."}

    logger.info(f"Arguments for jira_list_issue_comments: {arguments}")
    raw_result = _execute("jira_list_issue_comments", uid, arguments, version="20260203_00")
    
    # Process comments to clean bodies
    data = raw_result.get("data", raw_result) if isinstance(raw_result, dict) else {}
    comments = data.get("comments", []) if isinstance(data, dict) else []
    
    for comment in comments:
        if "body" in comment:
            comment["body"] = _CONTENT_CLEANER.clean_text(str(comment["body"]))
            
    return raw_result



def jira_delete_comment(
    issueIdOrKey: str,
    id: str,
) -> Dict[str, Any]:
    arguments: Dict[str, Any] = {
        "issue_id_or_key": issueIdOrKey,
        "id": id,
    }
    logger.info(f"jira_delete_comment called with issue_id_or_key: {issueIdOrKey} and id: {id}")
    uid = get_active_jira_user_id()
    if not uid: return {"error": "Jira not connected. Please connect Jira in settings first."}
    logger.info(f"Arguments for jira_delete_comment: {arguments}")
    return _execute("jira_delete_comment",uid,arguments, version="20260203_00")

def jira_get_current_user(
    expand: str = "groups,applicationRoles",
) -> Dict[str, Any]:
    arguments: Dict[str, Any] = {}
    if expand:
        arguments["expand"] = expand
        
    logger.info(f"jira_get_current_user called with expand: {expand}")
    uid = get_active_jira_user_id()
    
    if not uid: 
        return {"error": "Jira not connected. Please connect Jira in settings first."}
        
    logger.info(f"Arguments for jira_get_current_user: {arguments}")
    
    return _execute("JIRA_GET_CURRENT_USER", uid, arguments, version="20260203_00")

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
        "jira_delete_comment": jira_delete_comment,
        "jira_list_issue_comments": jira_list_issue_comments,
        "jira_get_issue": jira_get_issue,
        "jira_search_for_issues_using_jql_post": jira_search_for_issues_using_jql_post,
        "jira_get_current_user": jira_get_current_user
    }

__all__ = ["build_registry", "get_schemas"]