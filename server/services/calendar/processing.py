"""Calendar event normalization and formatting utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ProcessedCalendarEvent:
    """Normalized representation of a calendar event trigger."""

    type: str
    title: str
    person: Optional[str] = None
    status: Optional[str] = None
    meeting_link: Optional[str] = None
    location: Optional[str] = None
    start_time: Optional[str] = None


def build_processed_event(data: Dict[str, Any]) -> Optional[ProcessedCalendarEvent]:
    event_title = data.get("summary") or data.get("event_summary") or "Untitled Event"

    if "responseStatus" in data or "response_status" in data:
        return ProcessedCalendarEvent(
            type="rsvp",
            title=event_title,
            person=data.get("attendee_email") or data.get("email") or "Unknown Attendee",
            status=data.get("responseStatus") or data.get("response_status"),
        )

    if "minutes_before_start" in data or "time_until_start" in data or "start" in data:
        return ProcessedCalendarEvent(
            type="starting_soon",
            title=event_title,
            meeting_link=data.get("hangoutLink") or data.get("hangout_link") or data.get("meeting_link"),
            location=data.get("location"),
            start_time=data.get("start", {}).get("dateTime") or data.get("start_time"),
        )

    return None


def format_event_alert(event: ProcessedCalendarEvent) -> str:
    if event.type == "rsvp":
        return (
            f"**Calendar Alert: RSVP Change**\n"
            f"Status of event **{event.title}** has changed to **{event.status}** by **{event.person}**\n"
            f"---\n"
            f"Source: Google Calendar"
        )

    if event.type == "starting_soon":
        alert_text = f"**Calendar Alert: Event Starting Soon**\n"
        alert_text += f"The event **{event.title}** is starting soon"
        if event.start_time:
            alert_text += f" at {event.start_time}"
        alert_text += ".\n"

        if event.location:
            alert_text += f"**Location:** {event.location}\n"
        if event.meeting_link:
            alert_text += f"**Meeting Link:** [Join Meeting]({event.meeting_link})\n"

        return alert_text + "---\nSource: Google Calendar"

    return f"**Calendar Alert**\n{event.title}\n---\nSource: Google Calendar"
