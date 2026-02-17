from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from server.services.execution import get_execution_agent_logs
from server.services.calendar.client import execute_calendar_tool, get_active_calendar_user_id

_CALENDAR_AGENT_NAME = "calendar-execution-agent"

_SCHEMAS: List[Dict[str, Any]] = [
    {
    "type": "function",
    "function": {
        "name": "googlecalendar_create_event",
        "description": "Creates a new Google Calendar event with support for attendees, recurrence, Google Meet links, and working locations. Requires 'start_datetime'.",
        "parameters": {
            "type": "object",
            "properties": {
                "calendar_id": {
                    "type": "string",
                    "default": "primary",
                    "description": "The calendar ID (e.g., 'primary' or 'user@example.com') where the event will be created.",
                },
                "summary": {
                    "type": "string",
                    "description": "The title or summary of the event.",
                },
                "description": {
                    "type": "string",
                    "description": "A description of the event (can contain HTML).",
                },
                "start_datetime": {
                    "type": "string",
                    "description": "REQUIRED. Event start time in ISO 8601 format (e.g., '2025-01-16T13:00:00').",
                },
                "event_duration_hour": {
                    "type": "integer",
                    "default": 0,
                    "description": "Duration of the event in hours.",
                },
                "event_duration_minutes": {
                    "type": "integer",
                    "default": 30,
                    "description": "Duration of the event in minutes (0-59).",
                },
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone identifier (e.g., 'America/New_York'). Required if start_datetime is naive.",
                },
                "attendees": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "List of attendee email addresses. Plain names are not allowed.",
                },
                "location": {
                    "type": "string",
                    "description": "Geographic location of the event as free-form text.",
                },
                "create_meeting_room": {
                    "type": "boolean",
                    "default": True,
                    "description": "If True, attempts to add a Google Meet link.",
                },
                "recurrence": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "List of RRULE lines for recurring events (e.g., ['RRULE:FREQ=WEEKLY;COUNT=10']).",
                },
                "send_updates": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to send email notifications to attendees.",
                },
                "visibility": {
                    "type": "string",
                    "enum": ["default", "public", "private", "confidential"],
                    "default": "default",
                    "description": "Visibility of the event.",
                },
                "transparency": {
                    "type": "string",
                    "enum": ["opaque", "transparent"],
                    "default": "opaque",
                    "description": "Whether the event blocks time ('opaque') or is free ('transparent').",
                },
                "exclude_organizer": {
                    "type": "boolean",
                    "default": False,
                    "description": "If True, the organizer is not added as an attendee.",
                },
                "guests_can_modify": {
                    "type": "boolean",
                    "default": False,
                    "description": "If True, guests can modify the event.",
                },
                "eventType": {
                    "type": "string",
                    "enum": ["default", "birthday", "focusTime", "outOfOffice", "workingLocation"],
                    "default": "default",
                    "description": "The type of event (e.g., 'default', 'outOfOffice').",
                },
                "outOfOfficeProperties": {
                    "type": "object",
                    "description": "Properties for outOfOffice events.",
                    "properties": {
                        "autoDeclineMode": {
                            "type": "string",
                            "enum": ["declineNone", "declineAllConflictingInvitations", "declineOnlyNewConflictingInvitations"],
                            "description": "How to handle conflicting invitations.",
                        },
                        "declineMessage": {
                            "type": "string",
                            "description": "Message sent when auto-declining.",
                        }
                    },
                    "additionalProperties": False
                },
                "workingLocationProperties": {
                    "type": "object",
                    "description": "Properties for workingLocation events (requires Workspace Enterprise).",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["homeOffice", "officeLocation", "customLocation"],
                            "description": "Type of working location.",
                        },
                        "homeOffice": {"type": "object", "properties": {}},
                        "customLocation": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"}
                            },
                            "required": ["label"]
                        },
                        "officeLocation": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "buildingId": {"type": "string"},
                                "floorId": {"type": "string"},
                                "deskId": {"type": "string"}
                            }
                        }
                    },
                    "required": ["type"],
                    "additionalProperties": False
                }
            },
            "required": ["start_datetime"],
            "additionalProperties": False,
        },
    }
},
{
    "type": "function",
    "function": {
        "name": "googlecalendar_quick_add",
        "description": "Creates a Google Calendar event from a simple text string. Google parses the text to automatically determine the title, date, and time.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The natural language text describing the event (e.g., 'Lunch with Alex tomorrow at 12pm'). Required.",
                },
                "calendar_id": {
                    "type": "string",
                    "default": "primary",
                    "description": "The calendar ID where the event will be added (e.g., 'primary' or 'user@example.com').",
                },
                "send_updates": {
                    "type": "string",
                    "enum": ["all", "externalOnly", "none"],
                    "default": "none",
                    "description": "Controls email notifications. 'all' notifies everyone, 'externalOnly' notifies non-Google emails, 'none' sends no emails.",
                }
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    }
},
{
    "type": "function",
    "function": {
        "name": "googlecalendar_events_get",
        "description": "Retrieves the details of a single specific event from a Google Calendar. You must provide the unique Event ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "REQUIRED. The unique identifier of the specific event to retrieve (e.g., '0a9160c4...').",
                },
                "calendar_id": {
                    "type": "string",
                    "default": "primary",
                    "description": "The identifier of the calendar (e.g., 'primary' or 'user@example.com') containing the event.",
                },
                "max_attendees": {
                    "type": "integer",
                    "description": "The maximum number of attendees to include in the response details.",
                },
                "time_zone": {
                    "type": "string",
                    "description": "The IANA time zone to use in the response (e.g., 'America/New_York'). Defaults to the calendar's time zone.",
                }
            },
            "required": ["event_id"],
            "additionalProperties": False,
        },
    }
},
{
    "type": "function",
    "function": {
        "name": "googlecalendar_find_event",
        "description": "Searches for events on a Google Calendar based on free-text queries, time ranges, and event types. Supports expanding recurring events and sorting.",
        "parameters": {
            "type": "object",
            "properties": {
                "calendar_id": {
                    "type": "string",
                    "default": "primary",
                    "description": "The valid calendar identifier (e.g., 'primary', email address, or calendar ID). Use 'List Calendars' to find IDs for named calendars.",
                },
                "query": {
                    "type": "string",
                    "description": "Free-text search terms to match against summary, description, location, or attendees.",
                },
                "timeMin": {
                    "type": "string",
                    "description": "Lower bound for an event's end time (ISO 8601 or simple datetime). Only events ending after this time are included.",
                },
                "timeMax": {
                    "type": "string",
                    "description": "Upper bound for an event's start time (ISO 8601 or simple datetime). Only events starting before this time are included.",
                },
                "single_events": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to expand recurring event series into individual instances. Required for sorting by 'startTime'.",
                },
                "max_results": {
                    "type": "integer",
                    "default": 10,
                    "description": "Maximum number of events to return per page (1-2500).",
                },
                "order_by": {
                    "type": "string",
                    "enum": ["startTime", "updated"],
                    "description": "Sort order: 'startTime' (requires single_events=true) or 'updated'.",
                },
                "event_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["birthday", "default", "focusTime", "outOfOffice", "workingLocation"]
                    },
                    "default": ["birthday", "default", "focusTime", "outOfOffice", "workingLocation"],
                    "description": "List of event types to include in the search.",
                },
                "show_deleted": {
                    "type": "boolean",
                    "description": "If true, includes cancelled/deleted events in the results.",
                },
                "updated_min": {
                    "type": "string",
                    "description": "Lower bound for an event's last modification time. Includes deleted events since this time.",
                },
                "page_token": {
                    "type": "string",
                    "description": "Token used to fetch the next page of results from a previous request.",
                }
            },
            "additionalProperties": False,
        },
    }
},
{
  "type": "function",
  "function": {
    "name": "googlecalendar_patch_event",
    "description": "Patch (partially update) a Google Calendar event using the events.patch endpoint. Allows updating event metadata, times, attendees, RSVP status, location, and conference details without replacing the full event.",
    "parameters": {
      "type": "object",
      "properties": {
        "calendar_id": {
          "type": "string",
          "description": "Identifier of the calendar containing the event. Use 'primary' for the user's main calendar."
        },
        "event_id": {
          "type": "string",
          "description": "Unique technical identifier of the event to update (not the event title). For recurring instances, includes the instance timestamp."
        },
        "summary": {
          "type": "string",
          "description": "New title (summary) for the event."
        },
        "description": {
          "type": "string",
          "description": "New description for the event. Can include HTML."
        },
        "location": {
          "type": "string",
          "description": "New event location, such as a physical address, room name, or virtual meeting link."
        },
        "start_time": {
          "type": "string",
          "description": "New start time in RFC3339 format or YYYY-MM-DD for all-day events."
        },
        "end_time": {
          "type": "string",
          "description": "New end time in RFC3339 format or YYYY-MM-DD for all-day events. If omitted when updating start_time, the original duration is preserved."
        },
        "timezone": {
          "type": "string",
          "description": "IANA time zone name (e.g., 'America/Los_Angeles') applied to start and end times."
        },
        "attendees": {
          "type": "array",
          "items": {
            "type": "string"
          },
          "description": "List of attendee email addresses. Replaces the existing attendee list. Use an empty list to remove all attendees."
        },
        "rsvp_response": {
          "type": "string",
          "description": "RSVP response for the authenticated user only. Allowed values: needsAction, accepted, tentative, declined."
        },
        "send_updates": {
          "type": "string",
          "description": "Whether to send update notifications to attendees. Allowed values: all, externalOnly, none."
        },
        "conference_data_version": {
          "type": "integer",
          "description": "Conference data support version. Set to 1 to manage Google Meet or other conference details."
        },
        "max_attendees": {
          "type": "integer",
          "description": "Maximum number of attendees returned in the response. Does not affect who is invited."
        },
        "supports_attachments": {
          "type": "boolean",
          "description": "Whether the client application supports event attachments."
        }
      },
      "required": ["calendar_id", "event_id","send_updates"],
      "additionalProperties": False
    }
  }
},
{
  "type": "function",
  "function": {
    "name": "googlecalendar_delete_event",
    "description": "Delete an event from a Google Calendar. Supports deleting single events, individual instances of recurring events, or entire recurring event series.",
    "parameters": {
      "type": "object",
      "properties": {
        "calendar_id": {
          "type": "string",
          "description": "Identifier of the Google Calendar containing the event. Use 'primary' for the authenticated user's main calendar.",
          "default": "primary"
        },
        "event_id": {
          "type": "string",
          "description": "Unique identifier of the event to delete. Use the base event ID to delete a standalone event or the entire recurring series. Use an instance ID (baseEventId_YYYYMMDDTHHMMSSZ) to delete a single occurrence of a recurring event."
        }
      },
      "required": ["event_id"],
      "additionalProperties": False
    }
  }
},
{
  "type": "function",
  "function": {
    "name": "googlecalendar_remove_attendee",
    "description": "Remove a specific attendee from a Google Calendar event by email address. This updates the event's attendee list without deleting the event.",
    "parameters": {
      "type": "object",
      "properties": {
        "calendar_id": {
          "type": "string",
          "description": "Identifier of the Google Calendar containing the event. Use 'primary' for the authenticated user's main calendar.",
          "default": "primary"
        },
        "event_id": {
          "type": "string",
          "description": "Unique identifier of the event from which the attendee should be removed."
        },
        "attendee_email": {
          "type": "string",
          "format": "email",
          "description": "Email address of the attendee to remove. Must match an attendee currently on the event."
        }
      },
      "required": ["event_id", "attendee_email"],
      "additionalProperties": False
    }
  }
},
{
    "type": "function",
    "function": {
        "name": "googlecalendar_find_free_slots",
        "description": "Find free (available) time slots for a set of calendars within a specific time range.",
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "List of calendar identifiers to query for free/busy information (e.g., ['primary', 'user@example.com']). Default: ['primary'].",
                    "default": ["primary"],
                },
                "time_min": {
                    "type": "string",
                    "description": "Start datetime for the query interval. Accepts ISO, comma-separated, or simple datetime formats. Defaults to current time if not provided.",
                },
                "time_max": {
                    "type": "string",
                    "description": "End datetime for the query interval. Defaults to the end of the current day (23:59:59) if not provided. Max span is ~90 days.",
                },
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone identifier (e.g., 'America/New_York', 'UTC') used to interpret naive datetimes and format the response. Default: 'UTC'.",
                    "default": "UTC",
                },
                "calendar_expansion_max": {
                    "type": "integer",
                    "description": "Maximum number of calendars to include in the free/busy check. Default: 50.",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 50,
                },
                "group_expansion_max": {
                    "type": "integer",
                    "description": "Maximum calendar identifiers to return for a single group. Default: 100.",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 100,
                },
            },
            "additionalProperties": False,
        },
    },
},
{
    "type": "function",
    "function": {
        "name": "googlecalendar_events_import",
        "description": "Import an event into Google Calendar from an external iCal source. Requires iCalUID to identify the event being imported. Useful for importing events from email invitations or other calendar systems.",
        "parameters": {
            "type": "object",
            "properties": {
                "iCalUID": {
                    "type": "string",
                    "description": "REQUIRED. Event unique identifier as defined in RFC5545. This is required to identify the event being imported.",
                },
                "summary": {
                    "type": "string",
                    "description": "Title of the event.",
                },
                "description": {
                    "type": "string",
                    "description": "Description of the event. Can contain HTML.",
                },
                "location": {
                    "type": "string",
                    "description": "Geographic location of the event as free-form text.",
                },
                "start": {
                    "type": "object",
                    "description": "REQUIRED. The (inclusive) start time of the event. For all-day events, use 'date' field; for timed events, use 'dateTime' and 'timeZone' fields.",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "The date, in 'yyyy-mm-dd' format, for all-day events.",
                        },
                        "dateTime": {
                            "type": "string",
                            "description": "The start/end time as a combined date-time value (RFC3339).",
                        },
                        "timeZone": {
                            "type": "string",
                            "description": "The time zone for the start/end time.",
                        },
                    },
                },
                "end": {
                    "type": "object",
                    "description": "REQUIRED. The (exclusive) end time of the event. For all-day events, use 'date' field; for timed events, use 'dateTime' and 'timeZone' fields.",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "The date, in 'yyyy-mm-dd' format, for all-day events.",
                        },
                        "dateTime": {
                            "type": "string",
                            "description": "The start/end time as a combined date-time value (RFC3339).",
                        },
                        "timeZone": {
                            "type": "string",
                            "description": "The time zone for the start/end time.",
                        },
                    },
                },
                "attendees": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string"},
                            "displayName": {"type": "string"},
                            "optional": {"type": "boolean"},
                            "responseStatus": {"type": "string"},
                        },
                    },
                    "description": "The attendees of the event.",
                },
                "calendar_id": {
                    "type": "string",
                    "default": "primary",
                    "description": "Calendar identifier. Use 'primary' for the logged-in user's primary calendar.",
                },
                "status": {
                    "type": "string",
                    "enum": ["confirmed", "tentative", "cancelled"],
                    "description": "Status of the event.",
                },
                "visibility": {
                    "type": "string",
                    "enum": ["default", "public", "private", "confidential"],
                    "description": "Visibility of the event.",
                },
                "transparency": {
                    "type": "string",
                    "enum": ["opaque", "transparent"],
                    "description": "Whether the event blocks time on the calendar.",
                },
                "recurrence": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of RRULE, EXRULE, RDATE and EXDATE lines for a recurring event.",
                },
            },
            "required": ["iCalUID", "start", "end"],
            "additionalProperties": False,
        },
    },
}
]

def get_schemas() -> List[Dict[str, Any]]:
    return _SCHEMAS

_LOG_STORE = get_execution_agent_logs()


def _execute(tool_name: str, composio_user_id: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a Google Calendar tool and record the action for the execution agent journal."""

    payload = {k: v for k, v in arguments.items() if v is not None}
    payload_str = json.dumps(payload, ensure_ascii=False, sort_keys=True) if payload else "{}"
    try:
        result = execute_calendar_tool(tool_name, composio_user_id, arguments=payload)
    except Exception as exc:
        _LOG_STORE.record_action(
            _CALENDAR_AGENT_NAME,
            description=f"{tool_name} failed | args={payload_str} | error={exc}",
        )
        raise

    _LOG_STORE.record_action(
        _CALENDAR_AGENT_NAME,
        description=f"{tool_name} succeeded | args={payload_str}",
    )
    return result

def googlecalendar_create_event(
    start_datetime: str,
    calendar_id: str = "primary",
    summary: Optional[str] = None,
    description: Optional[str] = None,
    event_duration_hour: Optional[int] = 0,
    event_duration_minutes: Optional[int] = 30,
    timezone: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    location: Optional[str] = None,
    create_meeting_room: Optional[bool] = True,
    recurrence: Optional[List[str]] = None,
    send_updates: Optional[bool] = True,
    visibility: Optional[str] = "default",
    transparency: Optional[str] = "opaque",
    exclude_organizer: Optional[bool] = False,
    guests_can_modify: Optional[bool] = False,
    eventType: Optional[str] = "default",
    outOfOfficeProperties: Optional[Dict[str, Any]] = None,
    workingLocationProperties: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    arguments: Dict[str, Any] = {
        "calendar_id": calendar_id,
        "summary": summary,
        "description": description,
        "start_datetime": start_datetime,
        "event_duration_hour": event_duration_hour,
        "event_duration_minutes": event_duration_minutes,
        "timezone": timezone,
        "attendees": attendees,
        "location": location,
        "create_meeting_room": create_meeting_room,
        "recurrence": recurrence,
        "send_updates": send_updates,
        "visibility": visibility,
        "transparency": transparency,
        "exclude_organizer": exclude_organizer,
        "guests_can_modify": guests_can_modify,
        "eventType": eventType,
        "outOfOfficeProperties": outOfOfficeProperties,
        "workingLocationProperties": workingLocationProperties,
    }

    composio_user_id = get_active_calendar_user_id()
    if not composio_user_id:
        return {
            "error": "Google Calendar not connected. Please connect Google Calendar in settings first."
        }

    return _execute("GOOGLECALENDAR_CREATE_EVENT", composio_user_id, arguments)


def googlecalendar_quick_add(
    text: str,
    calendar_id: str = "primary",
    send_updates: Optional[str] = "none",
) -> Dict[str, Any]:
    arguments: Dict[str, Any] = {
        "text": text,
        "calendar_id": calendar_id,
        "send_updates": send_updates,
    }

    composio_user_id = get_active_calendar_user_id()
    if not composio_user_id:
        return {
            "error": "Google Calendar not connected. Please connect Google Calendar in settings first."
        }

    return _execute("GOOGLECALENDAR_QUICK_ADD", composio_user_id, arguments)


def googlecalendar_events_get(
    event_id: str,
    calendar_id: str = "primary",
    max_attendees: Optional[int] = None,
    time_zone: Optional[str] = None,
) -> Dict[str, Any]:
    arguments: Dict[str, Any] = {
        "event_id": event_id,
        "calendar_id": calendar_id,
        "max_attendees": max_attendees,
        "time_zone": time_zone,
    }

    composio_user_id = get_active_calendar_user_id()
    if not composio_user_id:
        return {
            "error": "Google Calendar not connected. Please connect Google Calendar in settings first."
        }

    return _execute("GOOGLECALENDAR_EVENTS_GET", composio_user_id, arguments)


def googlecalendar_find_event(
    calendar_id: str = "primary",
    query: Optional[str] = None,
    timeMin: Optional[str] = None,
    timeMax: Optional[str] = None,
    single_events: Optional[bool] = True,
    max_results: Optional[int] = 10,
    order_by: Optional[str] = None,
    event_types: Optional[List[str]] = None,
    show_deleted: Optional[bool] = None,
    updated_min: Optional[str] = None,
    page_token: Optional[str] = None,
) -> Dict[str, Any]:
    arguments: Dict[str, Any] = {
        "calendar_id": calendar_id,
        "query": query,
        "timeMin": timeMin,
        "timeMax": timeMax,
        "single_events": single_events,
        "max_results": max_results,
        "order_by": order_by,
        "event_types": event_types,
        "show_deleted": show_deleted,
        "updated_min": updated_min,
        "page_token": page_token,
    }

    composio_user_id = get_active_calendar_user_id()
    if not composio_user_id:
        return {
            "error": "Google Calendar not connected. Please connect Google Calendar in settings first."
        }

    return _execute("GOOGLECALENDAR_FIND_EVENT", composio_user_id, arguments)

from typing import Optional, List, Dict, Any


def googlecalendar_patch_event(
    calendar_id: str,
    event_id: str,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    timezone: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    rsvp_response: Optional[str] = None,
    send_updates: Optional[str] = None,
    conference_data_version: Optional[int] = None,
    max_attendees: Optional[int] = None,
    supports_attachments: Optional[bool] = None,
) -> Dict[str, Any]:
    arguments: Dict[str, Any] = {
        "calendar_id": calendar_id,
        "event_id": event_id,
        "summary": summary,
        "description": description,
        "location": location,
        "start_time": start_time,
        "end_time": end_time,
        "timezone": timezone,
        "attendees": attendees,
        "rsvp_response": rsvp_response,
        "send_updates": send_updates,
        "conference_data_version": conference_data_version,
        "max_attendees": max_attendees,
        "supports_attachments": supports_attachments,
    }

    composio_user_id = get_active_calendar_user_id()
    if not composio_user_id:
        return {
            "error": "Google Calendar not connected. Please connect Google Calendar in settings first."
        }

    return _execute("GOOGLECALENDAR_PATCH_EVENT", composio_user_id, arguments)


def googlecalendar_delete_event(
    event_id: str,
    calendar_id: str = "primary",
) -> Dict[str, Any]:
    arguments: Dict[str, Any] = {
        "calendar_id": calendar_id,
        "event_id": event_id,
    }

    composio_user_id = get_active_calendar_user_id()
    if not composio_user_id:
        return {
            "error": "Google Calendar not connected. Please connect Google Calendar in settings first."
        }

    return _execute("GOOGLECALENDAR_DELETE_EVENT", composio_user_id, arguments)

def googlecalendar_remove_attendee(
    event_id: str,
    calendar_id: str = "primary",
    attendee_email: str = "",
) -> Dict[str, Any]:
    arguments: Dict[str, Any] = {
        "calendar_id": calendar_id,
        "event_id": event_id,
        "attendee_email": attendee_email,
    }

    composio_user_id = get_active_calendar_user_id()
    if not composio_user_id:
        return {
            "error": "Google Calendar not connected. Please connect Google Calendar in settings first."
        }

    return _execute("GOOGLECALENDAR_REMOVE_ATTENDEE", composio_user_id, arguments)

def googlecalendar_find_free_slots(
    items: List[str] = ["primary"],
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    timezone: Optional[str] = None,
    calendar_expansion_max: Optional[int] = None,
    group_expansion_max: Optional[int] = None,
) -> Dict[str, Any]:
    arguments: Dict[str, Any] = {
        "items": items,
        "time_min": time_min,
        "time_max": time_max,
        "timezone": timezone,
        "calendar_expansion_max": calendar_expansion_max,
        "group_expansion_max": group_expansion_max,
    }

    composio_user_id = get_active_calendar_user_id()
    if not composio_user_id:
        return {
            "error": "Google Calendar not connected. Please connect Google Calendar in settings first."
        }

    return _execute("GOOGLECALENDAR_FIND_FREE_SLOTS", composio_user_id, arguments)

def googlecalendar_events_import(
    iCalUID: str,
    start: Dict[str, Any],
    end: Dict[str, Any],
    calendar_id: str = "primary",
    summary: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[Dict[str, Any]]] = None,
    status: Optional[str] = None,
    visibility: Optional[str] = None,
    transparency: Optional[str] = None,
    recurrence: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Import an event into Google Calendar from an external iCal source."""
    arguments: Dict[str, Any] = {
        "iCalUID": iCalUID,
        "start": start,
        "end": end,
        "calendar_id": calendar_id,
        "summary": summary,
        "description": description,
        "location": location,
        "attendees": attendees,
        "status": status,
        "visibility": visibility,
        "transparency": transparency,
        "recurrence": recurrence,
    }

    composio_user_id = get_active_calendar_user_id()
    if not composio_user_id:
        return {
            "error": "Google Calendar not connected. Please connect Google Calendar in settings first."
        }

    return _execute("GOOGLECALENDAR_EVENTS_IMPORT", composio_user_id, arguments)

def build_registry(agent_name: str) -> Dict[str, Callable[..., Any]]:  # noqa: ARG001
    """Return Google Calendar tool callables."""
    
    return {
        "googlecalendar_create_event": googlecalendar_create_event,
        "googlecalendar_quick_add": googlecalendar_quick_add,
        "googlecalendar_events_get": googlecalendar_events_get,
        "googlecalendar_find_event": googlecalendar_find_event,
        "googlecalendar_patch_event": googlecalendar_patch_event,
        "googlecalendar_delete_event": googlecalendar_delete_event,
        "googlecalendar_remove_attendee": googlecalendar_remove_attendee,
        "googlecalendar_find_free_slots": googlecalendar_find_free_slots,
        "googlecalendar_events_import": googlecalendar_events_import,
    }


__all__ = [
    "build_registry",
    "googlecalendar_create_event",
    "googlecalendar_quick_add",
    "googlecalendar_events_get",
    "googlecalendar_find_event",
    "googlecalendar_patch_event",
    "googlecalendar_delete_event",
    "googlecalendar_remove_attendee",
    "googlecalendar_find_free_slots",
    "googlecalendar_events_import",
]

    