"""Calendar event normalization and formatting utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ProcessedCalendarEvent:
    """Normalized representation of a calendar event trigger."""

    type: str  # rsvp, starting_soon, deleted, updated
    title: str
    person: Optional[str] = None
    status: Optional[str] = None
    meeting_link: Optional[str] = None
    location: Optional[str] = None
    start_time: Optional[str] = None
    updated_fields: Optional[Dict[str, Any]] = None
    end_time: Optional[str] = None
    organizer_email: Optional[str] = None
    organizer_name: Optional[str] = None


def build_processed_event(data: Dict[str, Any]) -> Optional[ProcessedCalendarEvent]:
    event_title = data.get("summary") or data.get("event_summary") or "Untitled Event"

    if "responseStatus" in data or "response_status" in data:
        return ProcessedCalendarEvent(
            type="rsvp change",
            title=event_title,
            person=data.get("attendee_email") or data.get("email") or "Unknown Attendee",
            status=data.get("responseStatus") or data.get("response_status"),
        )

    if "cancelled_at" in data or data.get("status") == "cancelled":
        return ProcessedCalendarEvent(
            type="deleted",
            title=event_title,
        )

    if "updated_fields" in data:
        return ProcessedCalendarEvent(
            type="updated",
            title=event_title,
            updated_fields=data.get("updated_fields"),
        )

    if any(k in data for k in ("minutes_until_start", "minutes_before_start", "time_until_start", "start")):
        return ProcessedCalendarEvent(
            type="starting_soon",
            title=event_title,
            meeting_link=data.get("hangout_link") or data.get("hangoutLink") or data.get("meeting_link"),
            location=data.get("location"),
            start_time=data.get("start_time") or data.get("start", {}).get("dateTime"),
        )

    if "organizer_email" in data:
        return ProcessedCalendarEvent(
            type="created",
            title=event_title,
            organizer_email=data.get("organizer_email"),
            organizer_name=data.get("organizer_name"),
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

    if event.type == "deleted":
        return (
            f"**Calendar Alert: Event Deleted**\n"
            f"The event **{event.title}** has been deleted or canceled.\n"
            f"---\n"
            f"Source: Google Calendar"
        )

    if event.type == "updated":
        fields_str = ""
        if event.updated_fields:
            changed_fields = []
            for field, values in event.updated_fields.items():
                if isinstance(values, dict) and "new_value" in values:
                    changed_fields.append(f"- **{field}**: {values['new_value']}")
                else:
                    changed_fields.append(f"- **{field}**")
            fields_str = "\nUpdated fields:\n" + "\n".join(changed_fields) + "\n"

        return (
            f"**Calendar Alert: Event Updated**\n"
            f"The event **{event.title}** has been updated.{fields_str}"
            f"---\n"
            f"Source: Google Calendar"
        )

    if event.type == "created":
        return (
            f"**Calendar Alert: Event Created**\n"
            f"The event invite **{event.title}** has been made by **{event.organizer_name}** ({event.organizer_email}).\n"
            f"---\n"
            f"Source: Google Calendar"
        )

    return f"**Calendar Alert**\n{event.title}\n---\nSource: Google Calendar"
