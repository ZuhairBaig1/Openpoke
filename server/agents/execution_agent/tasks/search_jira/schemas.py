"""Schemas for the Jira search task tools."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Tool names for the LLM to reference
TASK_TOOL_NAME = "task_jira_search"
SEARCH_TOOL_NAME = "jira_fetch_issues"
COMPLETE_TOOL_NAME = "return_jira_search_results"

_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": TASK_TOOL_NAME,
            "description": "Expand a raw Jira search request into targeted JQL or keyword queries to find specific issues.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_query": {
                        "type": "string",
                        "description": "Natural language request describing the Jira issues to find (e.g., 'Find all open bugs in the Mobile project').",
                    },
                },
                "required": ["search_query"],
                "additionalProperties": False,
            },
        },
    }
]


class JiraSearchIssue(BaseModel):
    """Clean representation of a Jira Issue optimized for LLM context."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    # Identifiers
    id: str  # Internal Jira ID
    key: str  # e.g., "PROJ-123" (The primary human identifier)
    query: str  # The search query/JQL that found this issue
    
    # Core Metadata
    summary: str  # Title of the issue
    status: str  # e.g., "To Do", "In Progress"
    priority: Optional[str] = "Medium"
    issue_type: str = Field(alias="type", default="Task")
    
    # People
    assignee: Optional[str] = None
    reporter: Optional[str] = None
    
    # Content
    updated: datetime
    description_text: str = Field(description="Cleaned, plain-text version of the issue description")
    
    # Comments (Critical for Jira context)
    latest_comment: Optional[str] = None


class JiraSearchToolResult(BaseModel):
    """Structured response for Jira search operations with error signaling."""

    status: Literal["success", "error"]
    query: Optional[str] = None
    result_count: Optional[int] = 0
    # Jira usually uses 'startAt' and 'maxResults' for pagination, 
    # but we'll stick to a next_token pattern for agent simplicity.
    next_page_token: Optional[str] = None 
    issues: List[JiraSearchIssue] = Field(default_factory=list)
    error: Optional[str] = None # Explicit field for error handling


class TaskJiraSearchPayload(BaseModel):
    """The final result package returned by the search specialist."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    issues: List[JiraSearchIssue]


_COMPLETION_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": COMPLETE_TOOL_NAME,
            "description": "Return the final list of relevant Jira issue keys found during the search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_keys": {
                        "type": "array",
                        "description": "List of Jira issue keys (e.g., ['DEV-1', 'DEV-2']) deemed relevant.",
                        "items": {"type": "string"},
                    },
                },
                "required": ["issue_keys"],
                "additionalProperties": False,
            },
        },
    }
]

def get_completion_schema() -> Dict[str, Any]:
    return _COMPLETION_SCHEMAS[0]


def get_schemas() -> List[Dict[str, Any]]:
    """Return the JSON schema for the Jira search task."""
    return _SCHEMAS


__all__ = [
    "JiraSearchIssue",
    "JiraSearchToolResult",
    "TaskJiraSearchPayload",
    "SEARCH_TOOL_NAME",
    "COMPLETE_TOOL_NAME",
    "TASK_TOOL_NAME",
    "get_completion_schema",
    "get_schemas",
]