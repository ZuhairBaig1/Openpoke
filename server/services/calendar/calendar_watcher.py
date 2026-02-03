import json
import asyncio
from uuid import UUID
from datetime import datetime
from typing import Any, Dict, Optional, TYPE_CHECKING
from .client import enable_calendar_trigger, get_active_calendar_user_id, dispatch_alert, normalize_trigger_response
from ...logging_config import logger

if TYPE_CHECKING:
    from ...agents.interaction_agent.runtime import InteractionAgentRuntime

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


def get_calendar_watcher() -> CalendarWatcher:
    global _calendar_watcher_instance
    if _calendar_watcher_instance is None:
        _calendar_watcher_instance = CalendarWatcher()
    return _calendar_watcher_instance

__all__ = ["CalendarWatcher", "get_calendar_watcher"]



    

    
    
