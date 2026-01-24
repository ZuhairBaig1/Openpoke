from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..config import Settings, get_settings
from ..models import JiraConnectPayload, JiraDisconnectPayload, JiraStatusPayload
from ..services import jira_disconnect_account, jira_fetch_status, jira_initiate_connect

router = APIRouter(prefix="/jira", tags=["jira"])


@router.post("/connect")
# Initiate Jira OAuth connection flow through Composio
async def jira_connect(payload: JiraConnectPayload, settings: Settings = Depends(get_settings)) -> JSONResponse:
    return jira_initiate_connect(payload, settings)


@router.post("/status")
# Check the current Jira connection status and user information
async def jira_status(payload: JiraStatusPayload) -> JSONResponse:
    return jira_fetch_status(payload)


@router.post("/disconnect")
# Disconnect Jira account and clear cached profile data
async def jira_disconnect(payload: JiraDisconnectPayload) -> JSONResponse:
    return jira_disconnect_account(payload)

@router.get("/debug_env")
async def debug_env(settings: Settings = Depends(get_settings)):
    import os
    return {
        "env_var": os.getenv("COMPOSIO_JIRA_AUTH_CONFIG_ID"),
        "settings_var": settings.composio_jira_auth_config_id,
        "env_keys_with_composio": [k for k in os.environ.keys() if "COMPOSIO" in k]
    }