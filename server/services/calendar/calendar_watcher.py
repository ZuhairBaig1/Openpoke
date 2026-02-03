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
    
    if "responseStatus" in data or "response_status" in data:
        status = data.get("responseStatus") or data.get("response_status")
        attendee = data.get("attendee_email") or data.get("email") or "Unknown Attendee"
        logger.debug(f"Calendar RSVP Received: {event_title} | Status: {status}")
        await dispatch_alert(type="rsvp", title=event_title, person=attendee, status=status)
    
    elif "minutes_before_start" in data or "time_until_start" in data or "start" in data:
        meeting_link = data.get("hangoutLink") or data.get("hangout_link") or data.get("meeting_link")
        location = data.get("location")
        start_time = data.get("start", {}).get("dateTime") or data.get("start_time")
        
        logger.debug(f"Calendar Starting Soon: {event_title}")
        await dispatch_alert(
            type="starting_soon",
            title=event_title,
            meeting_link=meeting_link,
            location=location,
            start_time=start_time
        )
    else:
        logger.warning(f"Unknown calendar trigger payload: {data}")


async def dispatch_alert(
    type: str,
    title: str,
    person: Optional[str] = None,
    status: Optional[str] = None,
    meeting_link: Optional[str] = None,
    location: Optional[str] = None,
    start_time: Optional[str] = None
) -> None:
    runtime = resolve_interaction_runtime()
    
    if type == "rsvp":
        alert_text = (
            f"**Calendar Alert: RSVP Change**\n"
            f"Status of event **{title}** has changed to **{status}** by **{person}**\n"
            f"---\n"
            f"Source: Google Calendar"
        )
    elif type == "starting_soon":
        alert_text = f"**Calendar Alert: Event Starting Soon**\n"
        alert_text += f"The event **{title}** is starting soon"
        if start_time:
            alert_text += f" at {start_time}"
        alert_text += ".\n"
        
        if location:
            alert_text += f"**Location:** {location}\n"
        if meeting_link:
            alert_text += f"**Meeting Link:** [Join Meeting]({meeting_link})\n"
            
        alert_text += f"---\nSource: Google Calendar"
    else:
        alert_text = f"**Calendar Alert**\n{title}\n---\nSource: Google Calendar"

    await runtime.handle_agent_message(alert_text)


def get_calendar_watcher() -> CalendarWatcher:
    global _calendar_watcher_instance
    if _calendar_watcher_instance is None:
        _calendar_watcher_instance = CalendarWatcher()
    return _calendar_watcher_instance

__all__ = ["CalendarWatcher", "get_calendar_watcher"]



    

    
    
