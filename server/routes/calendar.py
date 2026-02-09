from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..config import Settings, get_settings
from ..models import CalendarConnectPayload, CalendarDisconnectPayload, CalendarStatusPayload
from ..services.calendar import disconnect_calendar_account, fetch_calendar_status, initiate_calendar_connect, process_event

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.post("/connect")
# Initiate Jira OAuth connection flow through Composio
async def calendar_connect(payload: CalendarConnectPayload, settings: Settings = Depends(get_settings)) -> JSONResponse:
    return initiate_calendar_connect(payload, settings)


@router.post("/status")
# Check the current Jira connection status and user information
async def calendar_status(payload: CalendarStatusPayload) -> JSONResponse:
    return fetch_calendar_status(payload)


@router.post("/disconnect")
# Disconnect Jira account and clear cached profile data
async def calendar_disconnect(payload: CalendarDisconnectPayload) -> JSONResponse:
    return disconnect_calendar_account(payload)


@router.post("/webhook_response")
async def calendar_webhook(payload: dict) -> None:
    return await process_event(payload)
