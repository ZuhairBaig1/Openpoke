"""LLM-powered classifier for determining important Jira updates."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, List

from .processing import ProcessedJiraIssue
from ...config import get_settings
from ...logging_config import logger
from ...openrouter_client import OpenRouterError, request_chat_completion


_TOOL_NAME = "assess_jira_update_importance"
_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": _TOOL_NAME,
        "description": (
            "Analyze changes to a Jira issue and decide if they are significant enough "
            "to proactively notify the user. Return a structured summary of the important changes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "is_worthy": {
                    "type": "boolean",
                    "description": (
                        "Set to true if the changes materially affect the user's workflow, "
                        "deadline, or require immediate attention. False for minor administrative noise."
                    ),
                },
                "summary_header": {
                    "type": "string",
                    "description": (
                        "A short, header for the notification (e.g., 'Urgent Deadline Shift', "
                        "'Task Completed', 'Priority Escalation')."
                    ),
                },
                "changes": {
                    "type": "array",
                    "description": "List of specific changes that justify the notification.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {
                                "type": "string",
                                "description": "The name of the field that changed (e.g., 'Due Date', 'Status')."
                            },
                            "reason": {
                                "type": "string",
                                "description": "A concise explanation of why this specific change is important."
                            },
                            "importance": {
                                "type": "string",
                                "enum": ["High", "Medium", "Low"],
                                "description": "The urgency level of this specific change."
                            }
                        },
                        "required": ["field", "reason", "importance"],
                    },
                },
            },
            "required": ["is_worthy"],
            "additionalProperties": False,
        },
    },
}

_SYSTEM_PROMPT = (
    "You are an intelligent Jira assistant. You review updates to Jira issues to determine if they "
    "warrant interrupting the user. "
    "The user is likely a developer or project manager. "
    "Key Rules for 'Important':\n"
    "1. DEADLINES: Due dates moving closer are URGENT. Moving away is INFO.\n"
    "2. STATUS: Moving to 'Done' or 'Blocked' is important. Moving to 'Backlog' is usually low priority.\n"
    "3. ASSIGNEE: Being assigned a ticket is CRITICAL. Being unassigned is IMPORTANT.\n"
    "4. MENTIONS: Direct mentions are always CRITICAL.\n"
    "5. PRIORITY: Escalation (Medium -> High) is important. De-escalation is info.\n"
    "Avoid notifying for trivial edits unless they fundamentally change the scope of the task."
)


def _format_jira_payload(issue: ProcessedJiraIssue, changes: Dict[str, Any]) -> str:
    """Constructs a prompt showing the Issue context and the specific Diff."""
    
    # 1. Base Issue Context
    issue_context = (
        f"Issue: [{issue.key}] {issue.summary}\n"
        f"Type: {issue.issuetype} | Current Status: {issue.status}\n"
        f"Description Snippet: {issue.clean_description[:200]}..."
    )

    diff_lines = []
    
    if "mention" in changes:
        text = changes["mention"].get("text", "")
        diff_lines.append(f"NEW MENTION: User was mentioned in a comment: \"{text}\"")

    field_diffs = {k: v for k, v in changes.items() if k != "mention"}
    
    for field, diff in field_diffs.items():
        old_val = diff.get("old", "None")
        new_val = diff.get("new", "None")
        diff_lines.append(f"Field '{field.upper()}' Changed: {old_val}  ->  {new_val}")

    return (
        f"{issue_context}\n\n"
        f"--- DETECTED CHANGES ---\n"
        + "\n".join(diff_lines)
    )


async def classify_jira_changes(issue: ProcessedJiraIssue, changes: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a structured dictionary with importance analysis.
    Return schema:
    {
        "is_worthy": bool,
        "summary_header": str,
        "changes": List[Dict] (field, reason, importance)
    }
    """
    settings = get_settings()
    api_key = settings.openrouter_api_key
    model = settings.jira_classifier_model 

    if not api_key:
        logger.warning("Skipping Jira importance check; OpenRouter API key missing")
        return None 

    user_payload = _format_jira_payload(issue, changes)
    messages = [{"role": "user", "content": user_payload}]

    try:
        response = await request_chat_completion(
            model=model,
            messages=messages,
            system=_SYSTEM_PROMPT,
            api_key=api_key,
            tools=[_TOOL_SCHEMA],
        )
    except Exception as exc:
        logger.error(f"Jira classification API call failed: {exc}", extra={"issue_key": issue.key})
        return None

    choice = (response.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    tool_calls = message.get("tool_calls") or []

    for tool_call in tool_calls:
        function_block = tool_call.get("function") or {}
        if function_block.get("name") != _TOOL_NAME:
            continue

        raw_arguments = function_block.get("arguments")
        arguments = _coerce_arguments(raw_arguments)
        
        if arguments is None:
            logger.warning("Jira classifier returned unparseable arguments", extra={"issue_key": issue.key})
            return None # System failure to parse AI output

        # SUCCESS: Return the valid AI decision
        return {
            "is_worthy": bool(arguments.get("is_worthy")),
            "summary_header": arguments.get("summary_header", "Jira Update"),
            "changes": arguments.get("changes", [])
        }

    # If the loop finishes without finding our tool call, the AI didn't follow the schema
    logger.debug("Jira classification produced no valid tool call", extra={"issue_key": issue.key})
    return None

def _coerce_arguments(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


__all__ = ["classify_jira_changes"]