"""Internal Jira utilities for the search_jira task.

This module contains Jira functions that are internal to the search_jira task
and should not be exposed as public tools to execution agents.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from server.services.jira import execute_jira_tool, get_active_jira_user_id

# --- Tool Schemas for the Search Specialist ---

JIRA_SEARCH_JQL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "jira_search_issues_using_jql",
        "description": "Search Jira issues using JQL (Jira Query Language).",
        "parameters": {
            "type": "object",
            "properties": {
                "jql": {
                    "type": "string",
                    "description": "The JQL query string (e.g., 'project = \"DEV\" AND status = \"In Progress\"').",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max issues to return. Default is 10.",
                    "default": 10,
                },
            },
            "required": ["jql"],
            "additionalProperties": False,
        },
    },
}

JIRA_GET_ISSUE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "jira_get_issue",
        "description": "Get full details of a specific Jira issue by its key.",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_key": {
                    "type": "string", 
                    "description": "The Jira issue key (e.g., 'PROJ-123')."
                },
            },
            "required": ["issue_key"],
            "additionalProperties": False,
        },
    },
}

JIRA_LIST_COMMENTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "jira_list_comments",
        "description": "List all comments on a specific Jira issue.",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_key": {"type": "string", "description": "The Jira issue key."},
            },
            "required": ["issue_key"],
            "additionalProperties": False,
        },
    },
}

JIRA_LIST_PROJECTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "jira_list_projects",
        "description": "List all projects the user has access to. Useful for resolving project names to keys.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
}


# --- Internal Wrapper Functions ---

def jira_search_issues_using_jql(jql: str, max_results: int = 10) -> Dict[str, Any]:
    """Execute a JQL search through Composio."""
    composio_user_id = get_active_jira_user_id()
    if not composio_user_id:
        return {"error": "Jira not connected. Please connect Jira in settings first."}
    
    return execute_jira_tool(
        "JIRA_SEARCH_ISSUES_USING_JQL", 
        composio_user_id, 
        arguments={"jql": jql, "maxResults": max_results}
    )


def jira_get_issue(issue_key: str) -> Dict[str, Any]:
    """Fetch full issue details."""
    composio_user_id = get_active_jira_user_id()
    if not composio_user_id:
        return {"error": "Jira not connected."}
    
    return execute_jira_tool(
        "JIRA_GET_ISSUE", 
        composio_user_id, 
        arguments={"issue_id_or_key": issue_key}
    )


def jira_list_comments(issue_key: str) -> Dict[str, Any]:
    """Fetch comments for context."""
    composio_user_id = get_active_jira_user_id()
    if not composio_user_id:
        return {"error": "Jira not connected."}
    
    return execute_jira_tool(
        "JIRA_LIST_ISSUE_COMMENTS", 
        composio_user_id, 
        arguments={"issue_id_or_key": issue_key}
    )


def jira_list_projects() -> Dict[str, Any]:
    """Fetch available projects."""
    composio_user_id = get_active_jira_user_id()
    if not composio_user_id:
        return {"error": "Jira not connected."}
    
    return execute_jira_tool("JIRA_LIST_PROJECTS", composio_user_id)


__all__ = [
    "jira_search_issues_using_jql",
    "jira_get_issue",
    "jira_list_comments",
    "jira_list_projects",
    "JIRA_SEARCH_JQL_SCHEMA",
    "JIRA_GET_ISSUE_SCHEMA",
    "JIRA_LIST_COMMENTS_SCHEMA",
    "JIRA_LIST_PROJECTS_SCHEMA",
]