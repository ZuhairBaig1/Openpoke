"""Shared Jira issue normalization and cleaning utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ...logging_config import logger
from ...utils.timezones import convert_to_user_timezone

@dataclass(frozen=True)
class ProcessedJiraIssue:
    """Normalized Jira issue representation."""
    id: str
    key: str
    query: str
    summary: str
    status: str
    priority: Optional[str]
    issuetype: str
    updated: Optional[datetime]
    clean_description: str
    assignee: Optional[str]
    due_date: Optional[str] 
    browser_url: Optional[str] = None

class JiraContentCleaner:
    """Clean and extract readable text from Jira API responses."""

    def clean_text(self, text: Optional[str]) -> str:
        if not text:
            return ""
        
        # If it's a dict/list (ADF), we should probably not try to regex it as a string
        # but Composio usually converts to markdown. If it's still ADF, this will be messy.
        if not isinstance(text, str):
            try:
                text = str(text)
            except:
                return ""

        # 1. Remove Jira Macros/Wiki markup tags like {code}, {panel}
        text = re.sub(r'\{[^}]+\}', '', text)
        
        # 2. Replace Account IDs with a generic [User] placeholder
        text = re.sub(r'\[~accountid:[^\]]+\]', '[User]', text)
        
        # 3. Remove embedded image references
        text = re.sub(r'![^!]+\|thumbnail!', '', text)
        text = re.sub(r'![^!]+!', '', text)
        
        # 4. Standard whitespace cleanup
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()[:1500] 

def build_processed_issue(
    item: Dict[str, Any], 
    query: str, 
    cleaner: Optional[JiraContentCleaner] = None
) -> Optional[ProcessedJiraIssue]:
    """Map raw Jira API item to normalized ProcessedJiraIssue."""
    if not isinstance(item, dict):
        logger.warning(f"build_processed_issue received non-dict item: {type(item)}")
        return None

    # Handle both wrapped (fields) and flattened (root-level) structures
    fields = item.get("fields", {})
    if not isinstance(fields, dict) or not fields:
        # If 'fields' is missing, assume it's the flattened schema provided by the user
        fields = item
    
    cleaner = cleaner or JiraContentCleaner()
    
    # --- Timestamp Logic ---
    updated_dt: Optional[datetime] = None
    updated_raw = fields.get("updated")
    
    if updated_raw:
        try:
            # Jira strings look like "2024-05-20T10:00:00.000+0000"
            dt_str = updated_raw.replace('Z', '+00:00')
            dt = datetime.fromisoformat(dt_str)
            updated_dt = convert_to_user_timezone(dt)
        except Exception as exc:
            logger.debug(f"Failed to parse Jira timestamp: {updated_raw}", extra={"error": str(exc)})
            updated_dt = convert_to_user_timezone(datetime.now(timezone.utc))

    # --- Extract Fields ---
    raw_due = fields.get("due_date") or fields.get("duedate")
    
    # Status can be an object or a string
    status_obj = fields.get("status")
    status_name = "Unknown"
    if isinstance(status_obj, dict):
        status_name = status_obj.get("name", "Unknown")
    elif isinstance(status_obj, str):
        status_name = status_obj

    # Priority
    priority_obj = fields.get("priority")
    priority_name = None
    if isinstance(priority_obj, dict):
        priority_name = priority_obj.get("name")
    elif isinstance(priority_obj, str):
        priority_name = priority_obj

    # Issue Type
    type_obj = fields.get("issue_type") or fields.get("issuetype")
    type_name = "Task"
    if isinstance(type_obj, dict):
        type_name = type_obj.get("name", "Task")
    elif isinstance(type_obj, str):
        type_name = type_obj

    # Assignee
    assignee_obj = fields.get("assignee")
    assignee_name = "Unassigned"
    if isinstance(assignee_obj, dict):
        assignee_name = assignee_obj.get("display_name") or assignee_obj.get("displayName") or "Unassigned"
    elif isinstance(assignee_obj, str):
        assignee_name = assignee_obj

    return ProcessedJiraIssue(
        id=str(item.get("id", "")),
        key=item.get("key", ""),
        query=query,
        summary=fields.get("summary", "No Summary"),
        status=status_name,
        priority=priority_name,
        issuetype=type_name,
        updated=updated_dt,
        clean_description=cleaner.clean_text(fields.get("description")),
        assignee=assignee_name,
        due_date=raw_due,
        browser_url=fields.get("browser_url")
    )

def parse_jira_search_response(
    raw_result: Any, 
    query: str, 
    cleaner: Optional[JiraContentCleaner] = None
) -> List[ProcessedJiraIssue]:
    """Helper to handle Composio's wrapped search response."""
    issues: List[ProcessedJiraIssue] = []
    
    data = []
    if isinstance(raw_result, dict):
        # Composio usually returns data list directly or under "data" key
        if "data" in raw_result and isinstance(raw_result["data"], list):
            data = raw_result["data"]
        elif "data" in raw_result and isinstance(raw_result["data"], dict):
             # Sometimes it's nested like {'data': {'issues': [...]}}
             data = raw_result["data"].get("issues", [])
        elif "http_error" in raw_result or not raw_result.get("successful", True):
            # If it's an error dict from Composio, don't try to parse issues
            logger.warning(f"parse_jira_search_response received error result: {raw_result.get('error') or raw_result.get('http_error')}")
            return []
    elif isinstance(raw_result, list):
        data = raw_result

    if not isinstance(data, list):
        logger.warning(f"parse_jira_search_response failed to find issue list in: {type(raw_result)}")
        return []

    for item in data:
        processed = build_processed_issue(item, query, cleaner=cleaner)
        if processed:
            issues.append(processed)
    return issues


@dataclass(frozen=True)
class ProcessedJiraEvent:
    """Normalized representation of a Jira trigger."""

    type: str  # "issue_created", "project_created", "issue_updated", "unknown"
    title: str
    key: str
    description: Optional[str] = None
    reporter: Optional[str] = None
    assignee: Optional[str] = None
    url: Optional[str] = None
    status: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None


def build_processed_event(data: Dict[str, Any]) -> Optional[ProcessedJiraEvent]:
    # Check for Updated Issue Payload (Check this FIRST to distinguish from creation)
    if "updated_fields" in data and "issue_key" in data:
         return ProcessedJiraEvent(
            type="issue_updated",
            title=data.get("summary", "Untitled Issue"),
            key=data.get("issue_key", "UNKNOWN-KEY"),
            description=data.get("description"),
            reporter=data.get("reporter"),
            assignee=data.get("assignee"),
            raw_data=data
        )

    # Check for New Issue Payload
    if "issue_key" in data and "summary" in data and "project_name" not in data:
        return ProcessedJiraEvent(
            type="issue_created",
            title=data.get("summary", "Untitled Issue"),
            key=data.get("issue_key", "UNKNOWN-KEY"),
            description=data.get("description"),
            reporter=data.get("reporter"),
            assignee=data.get("assignee"),
            url=None,
            raw_data=data
        )

    # Check for New Project Payload
    if "project_key" in data and "project_name" in data:
        return ProcessedJiraEvent(
            type="project_created",
            title=data.get("project_name", "Untitled Project"),
            key=data.get("project_key", "UNKNOWN-KEY"),
            reporter=data.get("lead_name"),
            raw_data=data
        )

    return None


def format_event_alert(event: ProcessedJiraEvent) -> str:
    if event.type == "issue_created":
        alert_text = f"**Jira Alert: New Issue Created**\n"
        alert_text += f"**{event.key}**: {event.title}\n"
        if event.reporter:
            alert_text += f"**Reporter**: {event.reporter}\n"
        if event.assignee:
            alert_text += f"**Assignee**: {event.assignee}\n"
        if event.description:
            desc = event.description
            if len(desc) > 200:
                desc = desc[:197] + "..."
            alert_text += f"**Description**: {desc}\n"
            
        return alert_text + "---\nSource: Jira"

    if event.type == "project_created":
        alert_text = f"**Jira Alert: New Project Created**\n"
        alert_text += f"**{event.key}**: {event.title}\n"
        if event.reporter:
            alert_text += f"**Lead**: {event.reporter}\n"

        return alert_text + "---\nSource: Jira"
    
    if event.type == "issue_updated":
        alert_text = f"**Jira Alert: Issue Updated**\n"
        alert_text += f"**{event.key}**: {event.title}\n"
        if event.raw_data and "updated_fields" in event.raw_data:
             updated_fields = event.raw_data.get("updated_fields", {})
             if isinstance(updated_fields, dict):
                 alert_text += "**Changes:**\n"
                 for field, value in updated_fields.items():
                     display_val = str(value)
                     # Truncate long values
                     if len(display_val) > 100:
                         display_val = display_val[:97] + "..."
                     alert_text += f"- **{field}**: {display_val}\n"

        return alert_text + "---\nSource: Jira"

    return f"**Jira Alert**\nUnknown Event: {event.key}\n---\nSource: Jira"