"""Shared Jira issue normalization and cleaning utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

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

class JiraContentCleaner:
    """Clean and extract readable text from Jira API responses."""

    def clean_text(self, text: Optional[str]) -> str:
        if not text:
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
    fields = item.get("fields", {})
    if not fields:
        return None
    
    cleaner = cleaner or JiraContentCleaner()
    
    # --- FIXED: Correct logic for updated_dt ---
    updated_dt: Optional[datetime] = None
    updated_raw = fields.get("updated")
    
    if updated_raw:
        try:
            # Jira strings look like "2024-05-20T10:00:00.000+0000"
            # We normalize the offset and parse
            dt_str = updated_raw.replace('Z', '+00:00')
            dt = datetime.fromisoformat(dt_str)
            updated_dt = convert_to_user_timezone(dt)
        except Exception as exc:
            logger.debug(f"Failed to parse Jira timestamp: {updated_raw}", extra={"error": str(exc)})
            # Fallback to current time if parsing fails
            updated_dt = convert_to_user_timezone(datetime.now(timezone.utc))
    # -------------------------------------------

    return ProcessedJiraIssue(
        id=str(item.get("id", "")),
        key=item.get("key", ""),
        query=query,
        summary=fields.get("summary", "No Summary"),
        status=fields.get("status", {}).get("name", "Unknown"),
        priority=fields.get("priority", {}).get("name"),
        issuetype=fields.get("issuetype", {}).get("name", "Task"),
        updated=updated_dt,
        clean_description=cleaner.clean_text(fields.get("description")),
        assignee=fields.get("assignee", {}).get("displayName") if fields.get("assignee") else "Unassigned"
    )

def parse_jira_search_response(
    raw_result: Any, 
    query: str, 
    cleaner: Optional[JiraContentCleaner] = None
) -> List[ProcessedJiraIssue]:
    """Helper to handle Composio's wrapped search response."""
    issues: List[ProcessedJiraIssue] = []
    
    # Handle both list responses and dict/data responses from Composio
    data = []
    if isinstance(raw_result, dict):
        data = raw_result.get("data", [])
    elif isinstance(raw_result, list):
        data = raw_result

    for item in data:
        if processed := build_processed_issue(item, query, cleaner=cleaner):
            issues.append(processed)
    return issues