import json
import asyncio
from uuid import UUID
from datetime import datetime
from typing import Any, Dict, Optional, TYPE_CHECKING
from .client import enable_calendar_trigger, get_active_calendar_user_id, normalize_trigger_response
from ...logging_config import logger

if TYPE_CHECKING:
    from ...agents.interaction_agent.runtime import InteractionAgentRuntime

def resolve_interaction_runtime() -> "InteractionAgentRuntime":
    get_interaction_runtime = InteractionAgentRuntime()
    return get_interaction_runtime

class CalendarWatcher:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._enabled = False

    async def start(self) -> None:
        async with self._lock:
            if self._enabled:
                return
            
            user_id = get_active_calendar_user_id()
            if not user_id:
                logger.warning("Calendar not connected; skipping trigger registration.")
                return

            try:
                result = enable_calendar_trigger(
                    "GOOGLECALENDAR_ATTENDEE_RESPONSE_CHANGED_TRIGGER",
                    user_id,
                    arguments={"calendarId": "primary"}
                )
                
                normalized = normalize_trigger_response(result)
                
                if normalized.get("status") in ["ENABLED", "active", "SUCCESS"]:
                    self._enabled = True
                    logger.info("Calendar RSVP trigger registered successfully.")
            except Exception as e:
                logger.error(f"Failed to register calendar trigger: {e}")

_calendar_watcher_instance: Optional["CalendarWatcher"] = None

async def process_event(payload: Dict[str, Any]) -> None:
    data = normalize_trigger_response(payload)
    
    event_title = data.get("summary") or data.get("event_summary") or "Untitled Event"
    status = data.get("responseStatus") or data.get("response_status")
    attendee = data.get("attendee_email") or data.get("email") or "Unknown Attendee"

    logger.debug(f"Calendar Event Received: {event_title} | Status: {status}")

    await dispatch_alert(event_title, attendee, status)


async def dispatch_alert(title: str, person: str, status: Optional[str] = None) -> None:
    runtime = resolve_interaction_runtime()
    
    alert_text = (
        f"**Calendar Alert: RSVP Change**\n"
        f"Status of event **{title}** has changed to **{status}** by **{person}**\n"
        f"---\n"
        f"Source: Google Calendar"
    )
    await runtime.handle_agent_message(alert_text)


def get_calendar_watcher() -> CalendarWatcher:
    global _calendar_watcher_instance
    if _calendar_watcher_instance is None:
        _calendar_watcher_instance = CalendarWatcher()
    return _calendar_watcher_instance

__all__ = ["CalendarWatcher", "get_calendar_watcher"]



    

    
    
