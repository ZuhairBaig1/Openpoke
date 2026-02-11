from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..config import Settings, get_settings
from ..models import JiraConnectPayload, JiraDisconnectPayload, JiraStatusPayload
from ..services import get_jira_watcher, process_event
from ..logging_config import logger

router = APIRouter(tags=["webhook"])

jira_watcher_instance = get_jira_watcher()


@router.post("/webhook")
async def webhook(payload: dict) -> None:
    if payload.get("type") == "JIRA_NEW_PROJECT_TRIGGER":
        return await jira_watcher_instance.process_project_payload(payload = payload)
    elif payload.get("type") == "JIRA_NEW_ISSUE_TRIGGER":
        return await jira_watcher_instance.process_issue_payload(payload)
    elif payload.get("type") == "JIRA_UPDATED_ISSUE_TRIGGER":
        return await jira_watcher_instance.process_update_payload(payload)
    elif payload.get("type") == "GOOGLECALENDAR_ATTENDEE_RESPONSE_CHANGED_TRIGGER":
        return await process_event(payload)

    logger.warning(f"Unknown jira webhook payload: {payload}")