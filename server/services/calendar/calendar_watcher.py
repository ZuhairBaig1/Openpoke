import asyncio
from datetime import datetime
from typing import Any, Dict, Optional, TYPE_CHECKING
from .client import enable_calendar_trigger, get_active_calendar_user_id, normalize_trigger_response
from .processing import build_processed_event, format_event_alert
from ...logging_config import logger

if TYPE_CHECKING:
    from ...agents.interaction_agent.runtime import InteractionAgentRuntime

def resolve_interaction_runtime() -> "InteractionAgentRuntime":
    from ...agents.interaction_agent.runtime import InteractionAgentRuntime
    return InteractionAgentRuntime()

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
    event = build_processed_event(data)
    
    if not event:
        logger.warning(f"Unknown calendar trigger payload: {data}")
        return

    logger.debug(f"Calendar Event Received: {event.type} | {event.title}")
    
    alert_text = format_event_alert(event)
    runtime = resolve_interaction_runtime()
    await runtime.handle_agent_message(alert_text)

def get_calendar_watcher() -> CalendarWatcher:
    global _calendar_watcher_instance
    if _calendar_watcher_instance is None:
        _calendar_watcher_instance = CalendarWatcher()
    return _calendar_watcher_instance

__all__ = ["CalendarWatcher", "get_calendar_watcher"]
