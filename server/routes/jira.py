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
    from pathlib import Path
    
    # Locate .env manually
    search_path = Path(__file__).resolve().parent
    env_path = None
    for _ in range(4):
        candidate = search_path / ".env"
        if candidate.is_file():
            env_path = candidate
            break
        search_path = search_path.parent
        
    keys_in_file = []
    if env_path:
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    keys_in_file.append(line.split("=", 1)[0].strip())
        except Exception as e:
            keys_in_file = [f"Error reading file: {str(e)}"]

    return {
        "env_path": str(env_path) if env_path else "Not Found",
        "keys_in_file": keys_in_file,
        "env_var": os.getenv("COMPOSIO_JIRA_AUTH_CONFIG_ID"),
        "settings_var": settings.composio_jira_auth_config_id,
        "os_environ_keys": [k for k in os.environ.keys() if "COMPOSIO" in k]
    }