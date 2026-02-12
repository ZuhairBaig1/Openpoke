from __future__ import annotations

from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import JSONResponse

from ..config import Settings, get_settings
from ..models import JiraConnectPayload, JiraDisconnectPayload, JiraStatusPayload
from ..services import jira_disconnect_account, jira_fetch_status, jira_initiate_connect

router = APIRouter(prefix="/jira", tags=["jira"])


@router.post("/connect")
# Initiate Jira OAuth connection flow through Composio
async def jira_connect(payload: JiraConnectPayload, settings: Settings = Depends(get_settings)) -> JSONResponse:
    return await jira_initiate_connect(payload, settings)


@router.post("/status")
# Check the current Jira connection status and user information
async def jira_status(payload: JiraStatusPayload, background_tasks: BackgroundTasks) -> JSONResponse:
    return await jira_fetch_status(payload, background_tasks)


@router.post("/disconnect")
# Disconnect Jira account and clear cached profile data
async def jira_disconnect(payload: JiraDisconnectPayload) -> JSONResponse:
    return await jira_disconnect_account(payload)

