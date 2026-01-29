"""Internal Jira utilities for the search_jira task.

This module contains Jira functions that are internal to the search_jira task
and should not be exposed as public tools to execution agents.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from server.services.jira import execute_jira_tool, get_active_jira_user_id

from server.logging_config import logger

# --- Tool Schemas for the Search Specialist ---

JIRA_SEARCH_JQL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "jira_search_for_issues_using_jql_get",
        "description": "Search for Jira issues using JQL (Jira Query Language). Supports pagination and field filtering.",
        "parameters": {
            "type": "object",
            "properties": {
                "jql": {
                    "type": "string",
                    "description": "The JQL query string to filter issues (e.g., 'project = \"DEV\" AND status = \"In Progress\"'). Required unless using next_page_token."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of issues to return per page. Default is 50.",
                    "default": 50
                },
                "fields": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "List of specific fields to retrieve for each issue (e.g., ['summary', 'status', 'assignee']). specific fields reduces response size."
                },
                "next_page_token": {
                    "type": "string",
                    "description": "The token to retrieve the next page of results. Use this if a previous response included a next_page_token."
                },
                "expand": {
                    "type": "string",
                    "description": "Comma-separated list of entities to expand (e.g., 'renderedFields,names,schema,transitions,operations')."
                },
                "fields_by_keys": {
                    "type": "boolean",
                    "description": "Set to true to reference fields by their keys (e.g., 'customfield_10000') instead of IDs.",
                    "default": False                                    
                },
                "fail_fast": {
                    "type": "boolean",
                    "description": "If true, the search fails immediately if there is a partial error.",
                    "default": False
                },
                "properties": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "List of issue property keys (metadata) to retrieve."
                },
                "reconcile_issues": {
                    "type": "array",
                    "items": {
                        "type": "integer"
                    },
                    "description": "List of issue IDs to enable read-after-write reconciliation."
                }
            },
            "required": [
                "jql"
            ],
            "additionalProperties": False
        }
    }
}

JIRA_GET_ISSUE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "jira_get_issue",
        "description": "Retrieve the full details of a specific Jira issue by its key or ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_key": {
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
                "issue_key"
            ],
            "additionalProperties": False
        }
    }
}

JIRA_LIST_COMMENTS_SCHEMA = {
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
}

JIRA_LIST_PROJECTS_SCHEMA = {
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
    }

JIRA_GET_ALL_GROUPS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "jira_get_all_groups",
        "description": "Retrieve a list of all user groups available in the Jira instance. Useful for permissions auditing and group discovery.",
        "parameters": {
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "description": "The maximum number of groups to return per page. Used for pagination.",
                    "default": 50
                },
                "start_at": {
                    "type": "integer",
                    "description": "The index of the first item to return. Used for pagination to skip over groups already retrieved.",
                    "default": 0
                }
            },
            "required": [],
            "additionalProperties": False
        }
    }
}

JIRA_GET_GROUP_SCHEMA = {
    "type": "function",
    "function": {
        "name": "jira_get_group",
        "description": "Retrieve full details for a specific Jira group, such as 'site-admins' or 'developers'. essential for listing members within a group.",
        "parameters": {
            "type": "object",
            "properties": {
                "group_name": {
                    "type": "string",
                    "description": "The name of the group to retrieve (e.g., 'jira-software-users'). Either group_name or group_id must be provided."
                },
                "group_id": {
                    "type": "string",
                    "description": "The unique ID of the group to retrieve. Either group_name or group_id must be provided."
                },
                "expand": {
                    "type": "string",
                    "description": "List of entities to expand in the response. Pass 'users' to retrieve the list of members in this group."
                }
            },
            "required": [],
            "additionalProperties": False
        }
    }
}


# --- Internal Wrapper Functions ---

def jira_search_issues_using_jql(
    jql: str,
    max_results: int = 50,
    fields: Optional[List[str]] = None,
    next_page_token: Optional[str] = None,
    expand: Optional[str] = None,
    fields_by_keys: bool = False,
    fail_fast: bool = False,
    properties: Optional[List[str]] = None,
    reconcile_issues: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Search Jira issues using JQL with pagination and field filtering.
    """
    composio_user_id = get_active_jira_user_id()
    if not composio_user_id:
        return {"error": "Jira not connected. Please connect Jira in settings first."}
    logger.info(f"Active Jira user ID: {composio_user_id}, being passed to jira_search_issues_using_jql")

    arguments: Dict[str, Any] = {
        "jql": jql,
        "max_results": max_results,
        "fields": fields,
        "next_page_token": next_page_token,
        "expand": expand,
        "fields_by_keys": fields_by_keys,
        "fail_fast": fail_fast,
        "properties": properties,
        "reconcile_issues": reconcile_issues,
    }

    return execute_jira_tool(
        "JIRA_SEARCH_FOR_ISSUES_USING_JQL_GET",
        composio_user_id,
        arguments,
    )


def jira_get_issue(
    issue_key: str,
    expand: Optional[str] = None,
    fields: Optional[List[str]] = None,
    fields_by_keys: bool = False,
    properties: Optional[List[str]] = None,
    update_history: bool = False,
) -> Dict[str, Any]:
    """
    Retrieve full details for a specific Jira issue.
    """
    composio_user_id = get_active_jira_user_id()
    if not composio_user_id:
        return {"error": "Jira not connected. Please connect Jira in settings first."}
    logger.info(f"Active Jira user ID: {composio_user_id}, being passed to jira_get_issue")

    arguments: Dict[str, Any] = {
        "issue_key": issue_key,
        "expand": expand,
        "fields": fields,
        "fields_by_keys": fields_by_keys,
        "properties": properties,
        "update_history": update_history,
    }

    return execute_jira_tool(
        "JIRA_GET_ISSUE",
        composio_user_id,
        arguments,
    )



def jira_list_issue_comments(
    issue_id_or_key: str,
    max_results: int = 50,
    start_at: int = 0,
    order_by: Optional[str] = None,
    expand: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieve comments for a Jira issue.
    """
    composio_user_id = get_active_jira_user_id()
    if not composio_user_id:
        return {"error": "Jira not connected. Please connect Jira in settings first."}
    logger.info(f"Active Jira user ID: {composio_user_id}, being passed to jira_list_issue_comments")

    arguments: Dict[str, Any] = {
        "issue_id_or_key": issue_id_or_key,
        "max_results": max_results,
        "start_at": start_at,
        "order_by": order_by,
        "expand": expand,
    }

    return execute_jira_tool(
        "JIRA_LIST_ISSUE_COMMENTS",
        composio_user_id,
        arguments,
    )


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
    name: Optional[str] = None,  # deprecated
) -> Dict[str, Any]:
    """
    List Jira projects with filtering, sorting, and pagination.
    """
    composio_user_id = get_active_jira_user_id()
    if not composio_user_id:
        return {"error": "Jira not connected. Please connect Jira in settings first."}
    logger.info(f"Active Jira user ID: {composio_user_id}, being passed to jira_get_all_projects")

    arguments: Dict[str, Any] = {
        "action": action,
        "query": query,
        "maxResults": maxResults,
        "startAt": startAt,
        "orderBy": orderBy,
        "expand": expand,
        "status": status,
        "categoryId": categoryId,
        "properties": properties,
        "name": name,
    }

    return execute_jira_tool(
        "JIRA_GET_ALL_PROJECTS",
        composio_user_id,
        arguments,
    )

    def jira_get_all_groups(
        max_results: int = 50,
        start_at: int = 0,
    ) -> Dict[str, Any]:
        """
        Retrieve a list of all user groups available in the Jira instance.
        """
        composio_user_id = get_active_jira_user_id()
        if not composio_user_id:
            return {"error": "Jira not connected. Please connect Jira in settings first."}
        logger.info(f"Active Jira user ID: {composio_user_id}, being passed to jira_get_all_groups")

        arguments: Dict[str, Any] = {
            "max_results": max_results,
            "start_at": start_at,
        }

        return execute_jira_tool(
            "JIRA_GET_ALL_GROUPS",
            composio_user_id,
            arguments,
        )

    def jira_get_group(
        group_name: Optional[str] = None,
        group_id: Optional[str] = None,
        expand: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve full details for a specific Jira group, such as 'site-admins' or 'developers'. essential for listing members within a group.
        """
        composio_user_id = get_active_jira_user_id()
        if not composio_user_id:
            return {"error": "Jira not connected. Please connect Jira in settings first."}
        logger.info(f"Active Jira user ID: {composio_user_id}, being passed to jira_get_group")

        arguments: Dict[str, Any] = {
            "group_name": group_name,
            "group_id": group_id,
            "expand": expand,
        }

        return execute_jira_tool(
            "JIRA_GET_GROUP",
            composio_user_id,
            arguments,
        )




__all__ = [
    "jira_search_issues_using_jql",
    "jira_get_issue",
    "jira_list_issue_comments",
    "jira_get_all_projects",
    "JIRA_SEARCH_JQL_SCHEMA",
    "JIRA_GET_ISSUE_SCHEMA",
    "JIRA_LIST_ISSUE_COMMENTS_SCHEMA",
    "JIRA_GET_ALL_PROJECTS_SCHEMA",
    "JIRA_GET_GROUP_SCHEMA",
    "JIRA_GET_ALL_GROUPS_SCHEMA",
]