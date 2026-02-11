from __future__ import annotations

import json
import uuid
import os
import threading
from typing import Any, Dict, Optional, TYPE_CHECKING
from datetime import datetime
from uuid import UUID

from fastapi import status
from fastapi.responses import JSONResponse

from ...config import Settings, get_settings
from ...logging_config import logger
from ...models import CalendarConnectPayload, CalendarDisconnectPayload, CalendarStatusPayload
from ...utils import error_response

if TYPE_CHECKING:
    from ...agents.interaction_agent.runtime import InteractionAgentRuntime

_CLIENT_LOCK = threading.Lock()
_CLIENT: Optional[Any] = None

_PROFILE_CACHE: Dict[str, Dict[str, Any]] = {}
_PROFILE_CACHE_LOCK = threading.Lock()
_ACTIVE_USER_CALENDAR_ID_LOCK = threading.Lock()
_ACTIVE_USER_CALENDAR_ID: Optional[str] = None


def _normalized(value: Optional[str]) -> Optional[str]:
    val = (value or "").strip()
    return val or None


def _set_active_calendar_user_id(user_id: Optional[str]) -> None:
    sanitized = _normalized(user_id)
    with _ACTIVE_USER_CALENDAR_ID_LOCK:
        global _ACTIVE_USER_CALENDAR_ID
        _ACTIVE_USER_CALENDAR_ID = sanitized or None


def get_active_calendar_user_id() -> Optional[str]:
    with _ACTIVE_USER_CALENDAR_ID_LOCK:
        return _ACTIVE_USER_CALENDAR_ID


def _calendar_import_client():
    from composio import Composio  # type: ignore
    return Composio


# Get or create a singleton Composio client instance with thread-safe initialization
def _get_composio_client(settings: Optional[Settings] = None):
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    with _CLIENT_LOCK:
        if _CLIENT is None:
            resolved_settings = settings or get_settings()
            Composio = _calendar_import_client()
            api_key = resolved_settings.composio_api_key
            try:
                _CLIENT = Composio(api_key=api_key) if api_key else Composio()
            except TypeError as exc:
                if api_key:
                    raise RuntimeError(
                        "Installed Composio SDK does not accept the api_key argument; upgrade the SDK or remove COMPOSIO_API_KEY."
                    ) from exc
                _CLIENT = Composio()
    return _CLIENT


# --- Generic Tool Executor ---
def execute_calendar_tool(action_name: str, user_id: str, arguments: dict) -> Any:
    sanitized_user_id = _normalized(user_id)
    if not sanitized_user_id:
        return {"error": "Missing user_id"}

    try:
        client = _get_composio_client()
        result = client.client.tools.execute(
            tool_name=action_name,  # Updated from action_name kwarg to tool_name
            user_id=sanitized_user_id,
            arguments=arguments
        )
        return _normalize_tool_response(result)
    except Exception as exc:
        logger.error(f"Tool execution failed: {exc}")
        return {"error": str(exc)}


def enable_calendar_trigger(trigger_name: str, user_id: str, arguments: dict) -> Dict[str, Any]:
    sanitized_user_id = _normalized(user_id)
    if not sanitized_user_id:
        return {"status": "FAILED", "error": "Missing user_id"}

    try:
        client = _get_composio_client()
        result = client.triggers.create(
            slug=trigger_name.upper(),
            user_id=sanitized_user_id,
            trigger_config=arguments
        )

        if hasattr(result, "model_dump"):
            return result.model_dump()
        return result if isinstance(result, dict) else {"result": str(result)}

    except Exception as exc:
        logger.exception(
            "Failed to enable calendar trigger",
            extra={"trigger": trigger_name, "user_id": sanitized_user_id, "error": str(exc)}
        )
        return {"status": "FAILED", "error": str(exc)}


def _extract_email(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    direct_keys = (
        "email",
        "email_address",
        "emailAddress",
        "user_email",
        "provider_email",
        "account_email",
    )
    for key in direct_keys:
        try:
            val = getattr(obj, key)
            if isinstance(val, str) and "@" in val:
                return val
        except Exception:
            pass
        if isinstance(obj, dict):
            val = obj.get(key)
            if isinstance(val, str) and "@" in val:
                return val
    if isinstance(obj, dict):
        email_addresses = obj.get("emailAddresses")
        if isinstance(email_addresses, (list, tuple)):
            for entry in email_addresses:
                if isinstance(entry, dict):
                    candidate = entry.get("value") or entry.get("email") or entry.get("emailAddress")
                    if isinstance(candidate, str) and "@" in candidate:
                        return candidate
                elif isinstance(entry, str) and "@" in entry:
                    return entry
    if isinstance(obj, dict):
        nested_paths = (
            ("profile", "email"),
            ("profile", "emailAddress"),
            ("user", "email"),
            ("data", "email"),
            ("data", "user", "email"),
            ("provider_profile", "email"),
        )
        for path in nested_paths:
            current: Any = obj
            for segment in path:
                if isinstance(current, dict) and segment in current:
                    current = current[segment]
                else:
                    current = None
                    break
            if isinstance(current, str) and "@" in current:
                return current
    return None


def _cache_profile(user_id: str, profile: Dict[str, Any]) -> None:
    sanitized = _normalized(user_id)
    if not sanitized or not isinstance(profile, dict):
        return
    with _PROFILE_CACHE_LOCK:
        _PROFILE_CACHE[sanitized] = {
            "profile": profile,
            "cached_at": datetime.utcnow().isoformat(),
        }


def _get_cached_profile(user_id: Optional[str]) -> Optional[Dict[str, Any]]:
    sanitized = _normalized(user_id)
    if not sanitized:
        return None
    with _PROFILE_CACHE_LOCK:
        payload = _PROFILE_CACHE.get(sanitized)
        if payload and isinstance(payload.get("profile"), dict):
            return payload["profile"]
    return None


def _clear_cached_profile(user_id: Optional[str] = None) -> None:
    with _PROFILE_CACHE_LOCK:
        if user_id:
            key = _normalized(user_id)
            if key:
                _PROFILE_CACHE.pop(key, None)
        else:
            _PROFILE_CACHE.clear()


def _fetch_calendar_profile_from_composio(
    user_id: Optional[str],
    *,
    calendar_id: str = "primary",
) -> Optional[Dict[str, Any]]:
    sanitized = _normalized(user_id)
    if not sanitized:
        return None

    try:
        result = execute_calendar_tool(
            "GOOGLECALENDAR_CALENDARLIST_GET",
            sanitized,
            arguments={"calendarId": calendar_id},
        )
    except RuntimeError as exc:
        logger.warning("CALENDARLIST_GET invocation failed: %s", exc)
        return None
    except Exception:
        logger.exception(
            "Unexpected error fetching Calendar profile",
            extra={"user_id": sanitized},
        )
        return None

    profile: Optional[Dict[str, Any]] = None

    if isinstance(result, dict):
        if result.get("successful") is True and isinstance(result.get("data"), dict):
            profile = result["data"]
        elif isinstance(result.get("response_data"), dict):
            profile = result["response_data"]
        elif isinstance(result.get("data"), dict):
            profile = result["data"]

    if isinstance(profile, dict):
        _cache_profile(sanitized, profile)
        return profile

    logger.warning(
        "Received unexpected Calendar profile payload",
        extra={"user_id": sanitized, "raw": result},
    )
    return None


# Start Calendar OAuth connection process and return redirect URL
async def initiate_calendar_connect(payload: CalendarConnectPayload, settings: Settings) -> JSONResponse:
    auth_config_id = (
        payload.auth_config_id
        or settings.composio_googlecalendar_auth_config_id
        or get_settings().composio_googlecalendar_auth_config_id
        or os.getenv("COMPOSIO_GOOGLECALENDAR_AUTH_CONFIG_ID")
        or ""
    )

    if not auth_config_id:
        return error_response(
            "Missing auth_config_id. Set COMPOSIO_GOOGLECALENDAR_AUTH_CONFIG_ID or pass auth_config_id.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    user_id = payload.user_id or f"web-{uuid.uuid4()}"
    _set_active_calendar_user_id(user_id)
    _clear_cached_profile(user_id)

    try:
        # REPLACEMENT: Use singleton client and direct connected_accounts.initiate
        client = _get_composio_client()
        
        # NOTE: In new SDK, initiate often takes integration_id/auth_config_id as a parameter
        # Assuming auth_config_id is the integration UUID
        req = client.connected_accounts.initiate(
            auth_config_id=auth_config_id,
            user_id=user_id
        )

        # Preserve the watcher start logic
        async def start_calendar_watcher():
            from server.services import get_calendar_watcher
            calendar_watcher = get_calendar_watcher()
            return await calendar_watcher.start()
        
        await start_calendar_watcher()
        
        return JSONResponse(
            {
                "ok": True,
                "redirect_url": getattr(req, "redirectUrl", None) or getattr(req, "redirect_url", None),
                "connection_request_id": getattr(req, "connectedAccountId", None) or getattr(req, "id", None),
                "user_id": user_id,
            }
        )
    except Exception as exc:
        logger.exception("calendar connect failed", extra={"user_id": user_id})
        return error_response(
            "Failed to initiate Google Calendar connect",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


# Check Calendar connection status and retrieve user account information
def fetch_calendar_status(payload: CalendarStatusPayload) -> JSONResponse:
    connection_request_id = _normalized(payload.connection_request_id)
    user_id = _normalized(payload.user_id)

    if not connection_request_id and not user_id:
        return error_response(
            "Missing connection_request_id or user_id",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        # REPLACEMENT: Use singleton client
        client = _get_composio_client()
        account: Any = None

        if connection_request_id:
            try:
                account = client.connected_accounts.get(id=connection_request_id)
            except Exception:
                account = None

        if account is None and user_id:
            try:
                # REPLACEMENT: Use list filtering logic instead of get_entity iteration
                items = client.connected_accounts.list(
                    user_ids=[user_id], 
                    statuses=["ACTIVE"]
                )
                
                data = getattr(items, "data", None)
                if data is None and isinstance(items, dict):
                    data = items.get("data")
                elif isinstance(items, list):
                    data = items
                
                if data:
                    # Find first Google Calendar account
                    for item in data:
                        if (getattr(item, "appName", "").upper() == "GOOGLECALENDAR" or 
                            getattr(item, "appUniqueId", "").upper() == "GOOGLECALENDAR"):
                            account = item
                            break
            except Exception:
                account = None

        status_value = None
        email = None
        connected = False
        profile = None
        profile_source = "none"

        account_user_id = None
        if account is not None:
            status_value = getattr(account, "status", None) or (
                account.get("status") if isinstance(account, dict) else None
            )
            connected = (status_value or "").upper() in {
                "CONNECTED",
                "SUCCESS",
                "SUCCESSFUL",
                "ACTIVE",
                "COMPLETED",
            }
            email = _extract_email(account)
            account_user_id = getattr(account, "user_id", None) or (
                account.get("user_id") if isinstance(account, dict) else None
            )

        if not user_id and account_user_id:
            user_id = _normalized(account_user_id)

        if connected and user_id:
            cached_profile = _get_cached_profile(user_id)
            if cached_profile:
                profile = cached_profile
                profile_source = "cache"
            else:
                fetched = _fetch_calendar_profile_from_composio(user_id)
                if fetched:
                    profile = fetched
                    profile_source = "fetched"

            if profile and not email:
                email = _extract_email(profile) or profile.get("id")

        elif user_id and not connected:
            _clear_cached_profile(user_id)

        _set_active_calendar_user_id(user_id)

        return JSONResponse(
            {
                "ok": True,
                "connected": bool(connected),
                "status": status_value or "UNKNOWN",
                "email": email,
                "user_id": user_id,
                "profile": profile,
                "profile_source": profile_source,
            }
        )
    except Exception as exc:
        logger.exception(
            "calendar status failed",
            extra={"connection_request_id": connection_request_id, "user_id": user_id},
        )
        return error_response(
            "Failed to fetch Calendar connection status",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


def disconnect_calendar_account(payload: CalendarDisconnectPayload) -> JSONResponse:
    connection_id = _normalized(payload.connection_id) or _normalized(payload.connection_request_id)
    user_id = _normalized(payload.user_id)

    if not connection_id and not user_id:
        return error_response(
            "Missing connection_id or user_id",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        client = _get_composio_client()
    except Exception as exc:
        logger.exception("calendar disconnect failed: client init", extra={"user_id": user_id})
        return error_response(
            "Failed to disconnect Google Calendar",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    removed_ids: list[str] = []
    errors: list[str] = []
    affected_user_ids: set[str] = set()

    def _delete_connection(identifier: str) -> None:
        sanitized_id = _normalized(identifier)
        if not sanitized_id:
            return
        try:
            connection = client.connected_accounts.get(sanitized_id)
        except Exception:
            connection = None
        try:
            client.connected_accounts.delete(sanitized_id)
            removed_ids.append(sanitized_id)
            if connection is not None:
                if hasattr(connection, "user_id"):
                    uid = _normalized(getattr(connection, "user_id", None))
                    if uid:
                        affected_user_ids.add(uid)
                elif isinstance(connection, dict):
                    uid = _normalized(connection.get("user_id"))
                    if uid:
                        affected_user_ids.add(uid)
        except Exception as exc:  # pragma: no cover
            logger.exception(
                "Failed to remove Google Calendar connection",
                extra={"connection_id": sanitized_id},
            )
            errors.append(str(exc))

    if connection_id:
        _delete_connection(connection_id)
    elif user_id:
        try:
            # REPLACEMENT: Use list filtering instead of get_entity
            items = client.connected_accounts.list(user_ids=[user_id])
            
            data = getattr(items, "data", None)
            if data is None and isinstance(items, dict):
                data = items.get("data")
            elif isinstance(items, list):
                data = items

            if data:
                for conn in data:
                    if getattr(conn, "appName", "").upper() == "GOOGLECALENDAR" or \
                       getattr(conn, "appUniqueId", "").upper() == "GOOGLECALENDAR":
                        cid = getattr(conn, "id", None)
                        if cid:
                            _delete_connection(cid)

        except Exception as exc:
            logger.exception("Failed to list Calendar connections", extra={"user_id": user_id})
            return error_response(
                "Failed to disconnect Google Calendar",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            )

    if user_id:
        affected_user_ids.add(user_id)

    for uid in list(affected_user_ids):
        if uid:
            _clear_cached_profile(uid)
            if get_active_calendar_user_id() == uid:
                _set_active_calendar_user_id(None)

    if errors and not removed_ids:
        return error_response(
            "Failed to disconnect Google Calendar",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="; ".join(errors),
        )

    return_payload = {
        "ok": True,
        "disconnected": bool(removed_ids),
        "removed_connection_ids": removed_ids,
    }
    if not removed_ids:
        return_payload["message"] = "No Google Calendar connection found"

    if errors:
        return_payload["warnings"] = errors

    return JSONResponse(return_payload)


def _sanitize_dict_values(data: Any) -> Any:
    """Recursively converts non-JSON serializable objects into strings."""
    if isinstance(data, dict):
        return {k: _sanitize_dict_values(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_sanitize_dict_values(i) for i in data]
    elif isinstance(data, (datetime, UUID)):
        return str(data)
    return data

def _base_normalize(result: Any) -> Dict[str, Any]:
    if result is None:
        return {}

    payload_dict: Optional[Dict[str, Any]] = None

    for method in ("model_dump", "dict"):
        if hasattr(result, method):
            try:
                payload_dict = getattr(result, method)()
                break
            except Exception:
                continue

    if payload_dict is None and hasattr(result, "model_dump_json"):
        try:
            payload_dict = json.loads(result.model_dump_json())
        except Exception:
            pass

    if payload_dict is None:
        if isinstance(result, dict):
            payload_dict = result
        elif isinstance(result, list):
            payload_dict = {"items": result}
        elif isinstance(result, str):
            try:
                payload_dict = json.loads(result)
            except json.JSONDecodeError:
                payload_dict = {"raw_content": result}
        else:
            payload_dict = {"repr": str(result)}

    return _sanitize_dict_values(payload_dict)

def _normalize_tool_response(result: Any) -> Dict[str, Any]:
    return _base_normalize(result)

def normalize_trigger_response(result: Any) -> Dict[str, Any]:
    if isinstance(result, dict):
        if "payload" in result:
            result = result["payload"]
        elif "data" in result:
            result = result["data"]
    else:
        for attr in ("payload", "data"):
            val = getattr(result, attr, None)
            if val is not None:
                result = val
                break
                
    return _base_normalize(result)







    
