from __future__ import annotations

import json
import os
import uuid
import threading
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import status
from fastapi.responses import JSONResponse

from ...config import Settings, get_settings
from ...logging_config import logger
from ...models import JiraConnectPayload, JiraDisconnectPayload, JiraStatusPayload
from ...utils import error_response

_CLIENT_LOCK = threading.Lock()
_CLIENT: Optional[Any] = None

_PROFILE_CACHE: Dict[str, Dict[str, Any]] = {}
_PROFILE_CACHE_LOCK = threading.Lock()
_ACTIVE_USER_ID_JIRA_LOCK = threading.Lock()
_ACTIVE_USER_ID_JIRA: Optional[str] = None

def _normalized(value: Optional[str]) -> str:
    return (value or "").strip()

def _set_active_jira_user_id(user_id: Optional[str]) -> None:
    sanitized = _normalized(user_id)
    with _ACTIVE_USER_ID_JIRA_LOCK:
        global _ACTIVE_USER_ID_JIRA
        _ACTIVE_USER_ID_JIRA = sanitized or None
    logger.info(f"Active Jira user ID set to: {sanitized}")

def get_active_jira_user_id() -> Optional[str]:
    with _ACTIVE_USER_ID_JIRA_LOCK:
        return _ACTIVE_USER_ID_JIRA

def _jira_import_client():
    from composio import Composio  # type: ignore
    return Composio

def _get_composio_client(settings: Optional[Settings] = None):
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    with _CLIENT_LOCK:
        if _CLIENT is None:
            resolved_settings = settings or get_settings()
            Composio = _jira_import_client()
            api_key = resolved_settings.composio_api_key
            try:
                _CLIENT = Composio(api_key=api_key) if api_key else Composio()
            except TypeError as exc:
                if api_key:
                    raise RuntimeError("Installed Composio SDK does not accept the api_key argument.") from exc
                _CLIENT = Composio()
    return _CLIENT

def _extract_jira_details(obj: Any) -> Dict[str, Any]:
    """Extract identity prioritizing accountId over email."""
    details: Dict[str, Any] = {"email": None, "accountId": None, "displayName": None}
    if obj is None:
        return details

    details["accountId"] = (
        getattr(obj, "accountId", None) or
        (obj.get("accountId") if isinstance(obj, dict) else None)
    )
    details["displayName"] = (
        getattr(obj, "displayName", None) or
        (obj.get("displayName") if isinstance(obj, dict) else None)
    )

    for key in ("email", "emailAddress", "email_address"):
        val = getattr(obj, key, None) or (obj.get(key) if isinstance(obj, dict) else None)
        if isinstance(val, str) and "@" in val:
            details["email"] = val
            break
    return details

# --- Cache and Profile Helpers ---

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
        return payload["profile"] if payload and isinstance(payload.get("profile"), dict) else None

def _clear_cached_profile(user_id: Optional[str] = None) -> None:
    with _PROFILE_CACHE_LOCK:
        if user_id:
            _PROFILE_CACHE.pop(_normalized(user_id), None)
        else:
            _PROFILE_CACHE.clear()

def _fetch_profile_from_composio(user_id: Optional[str]) -> Optional[Dict[str, Any]]:
    sanitized = _normalized(user_id)
    if not sanitized:
        return None
    try:
        result = execute_jira_tool(
            "JIRA_GET_CURRENT_USER",
            sanitized,
            arguments={
                "expand": "groups,applicationRoles"
            }
        )
        profile = result.get("data") or result.get("profile") or result
        if isinstance(profile, dict):
            _cache_profile(sanitized, profile)
            logger.info(f"JIRA_GET_CURRENT_USER success, user_id:- {sanitized}", extra={"user_id": sanitized, "profile": profile})
            return profile
    except Exception as exc:
        logger.warning(f"JIRA_GET_CURRENT_USER failed, error:- {str(exc)}", extra={"user_id": sanitized, "error": str(exc)})
    return None

# --- Main API Methods ---

def jira_initiate_connect(payload: JiraConnectPayload, settings: Settings) -> JSONResponse:
    auth_config_id = (
    (payload.auth_config_id or "").strip()
    or (settings.composio_jira_auth_config_id or "").strip()
    or (os.getenv("COMPOSIO_JIRA_AUTH_CONFIG_ID") or "").strip()
    )

    logger.info(f"Jira auth_config_id: {auth_config_id}")
    
    if not auth_config_id:
        return error_response("Missing auth_config_id for Jira.", status_code=400)

    user_id = payload.user_id or f"web-jira-{uuid.uuid4()}"
    _set_active_jira_user_id(user_id)
    _clear_cached_profile(user_id)

    logger.info(f"Jira user_id: {user_id}")

    subdomain = (
        (settings.jira_subdomain or "").strip()
        or (os.getenv("JIRA_SUBDOMAIN") or "").strip()
    )

    logger.info(f"Jira subdomain: {subdomain}")
        

    try:
        from composio import ComposioToolSet
        settings = get_settings()
        api_key = settings.composio_api_key
        toolset = ComposioToolSet(api_key=api_key, entity_id=user_id)
        
        req = toolset.initiate_connection(
            app="jira",
            auth_config={"id": auth_config_id},
            auth_scheme="OAUTH2",
            connected_account_params={
                "subdomain": subdomain,
            }
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "ok": True,
                "already_connected": False,
                "user_id": user_id,
                "connection_request_id": getattr(req, "connectedAccountId", None) or getattr(req, "id", None),
                "redirect_url": getattr(req, "redirectUrl", None) or getattr(req, "redirect_url", None),
                "status": "INITIALIZING"
                }
            )



    except Exception as exc:
        logger.exception("Jira connect initiation failed", extra={"user_id": user_id})
        return error_response(f"Failed to initiate Jira connect", status_code=500, detail=str(exc))

def jira_fetch_status(payload: JiraStatusPayload) -> JSONResponse:
    connection_request_id = _normalized(payload.connection_request_id)
    user_id = _normalized(payload.user_id)
    try:
        from composio import ComposioToolSet
        settings = get_settings()
        api_key = settings.composio_api_key
        toolset = ComposioToolSet(api_key=api_key)
        
        account: Any = None
        
        if connection_request_id:
            try:
                account = toolset.get_connected_account(id=connection_request_id)
            except Exception as exc:
                logger.warning("Wait for connection failed, attempting direct fetch", extra={"id": connection_request_id})
                account = None

        if account is None and user_id:
            try:
                entity = toolset.client.get_entity(id=user_id)
                connections = entity.get_connections()
                # Find the first active Jira connection
                for conn in connections:
                    if (getattr(conn, "appName", "").upper() == "JIRA" or
                        getattr(conn, "appUniqueId", "").upper() == "JIRA") and \
                       getattr(conn, "status", "").upper() == "ACTIVE":
                        account = conn
                        break
            except Exception:
                account = None

        status_value = "UNKNOWN"
        connected = False
        profile = None
        details = {"email": None, "accountId": None, "displayName": None}

        if account:
            raw_status = getattr(account, "status", None) or (account.get("status") if isinstance(account, dict) else None)
            status_value = str(raw_status or "UNKNOWN")
            connected = status_value.upper() in {"CONNECTED", "ACTIVE", "SUCCESSFUL"}
            details = _extract_jira_details(account)

        if connected and user_id:
            profile = _get_cached_profile(user_id) or _fetch_profile_from_composio(user_id)
            if profile:
                p_details = _extract_jira_details(profile)
                for k in details:
                    if not details[k]: details[k] = p_details[k]
                
        logger.info(f"Setting active Jira user_id using _set_active_jira_user_id:- {user_id}")    
        _set_active_jira_user_id(user_id)
        return JSONResponse({
            "ok": True,
            "connected": connected,
            "status": status_value,
            "user_id": user_id,
            "jira_account_id": details["accountId"],
            "email": details["email"],
            "display_name": details["displayName"],
            "profile": profile
        })
    except Exception as exc:
        logger.exception("Jira status check failed")
        return error_response("Failed to fetch Jira status", status_code=500, detail=str(exc))

def jira_disconnect_account(payload: JiraDisconnectPayload) -> JSONResponse:
    """Disconnects account with explicit error logging."""
    connection_id = _normalized(payload.connection_id) or _normalized(payload.connection_request_id)
    user_id = _normalized(payload.user_id)
    client = _get_composio_client()
    removed_ids = []

    if connection_id:
        try:
            client.connected_accounts.delete(connection_id)
            removed_ids.append(connection_id)
        except Exception as exc:
            logger.error("Failed to delete Jira connection by ID", 
                         extra={"connection_id": connection_id, "user_id": user_id, "error": str(exc)})

    elif user_id:
        try:
            entity = client.get_entity(id=user_id)
            connections = entity.get_connections()
            for conn in connections:
                if getattr(conn, "appName", "").upper() == "JIRA" or \
                   getattr(conn, "appUniqueId", "").upper() == "JIRA":
                    cid = getattr(conn, "id", None)
                    if cid:
                        try:
                            client.connected_accounts.delete(cid)
                            removed_ids.append(cid)
                        except Exception as exc:
                            logger.error("Failed to delete Jira connection during bulk removal",
                                         extra={"connection_id": cid, "user_id": user_id, "error": str(exc)})
        except Exception as exc:
            logger.error("Failed to list Jira connections for disconnection", extra={"user_id": user_id, "error": str(exc)})

    if user_id:
        _clear_cached_profile(user_id)
        if get_active_jira_user_id() == user_id:
            _set_active_jira_user_id(None)

    return JSONResponse({"ok": True, "disconnected": bool(removed_ids), "removed_connection_ids": removed_ids})


def _normalize_jira_response(result: Any) -> Dict[str, Any]:
    payload_dict: Optional[Dict[str, Any]] = None
    try:
        if hasattr(result, "model_dump"):
            payload_dict = result.model_dump()  # type: ignore[assignment]
        elif hasattr(result, "dict"):
            payload_dict = result.dict()  # type: ignore[assignment]
    except Exception:
        payload_dict = None

    if payload_dict is None:
        try:
            if hasattr(result, "model_dump_json"):
                payload_dict = json.loads(result.model_dump_json())
        except Exception:
            payload_dict = None

    if payload_dict is None:
        if isinstance(result, dict):
            payload_dict = result
        elif isinstance(result, list):
            payload_dict = {"items": result}
        else:
            payload_dict = {"repr": str(result)}

    return payload_dict

def execute_jira_tool(tool_name: str, composio_user_id: str, *, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    prepared_args = {k: v for k, v in (arguments or {}).items() if v is not None}
    try:
        from composio import ComposioToolSet
        settings = get_settings()
        api_key = settings.composio_api_key
        toolset = ComposioToolSet(api_key=api_key, entity_id=composio_user_id)
        
        logger.info(f"BEFORE CALLING toolset.execute_action: tool_name={tool_name}, composio_user_id={composio_user_id}, arguments={prepared_args}")
        result = toolset.execute_action(action=tool_name, params=prepared_args)
        
        final_res = _normalize_jira_response(result)
        logger.info(f"AFTER CALLING toolset.execute_action: WILL RETURN {final_res}")
        return final_res
    except Exception as exc:
        logger.exception("Jira tool execution failed", extra={"tool": tool_name, "user_id": composio_user_id})
        raise RuntimeError(f"{tool_name} failed: {exc}") from exc
