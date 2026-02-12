from __future__ import annotations

from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import JSONResponse

from ..config import Settings, get_settings
from ..models import JiraConnectPayload, JiraDisconnectPayload, JiraStatusPayload
from ..services import get_jira_watcher, process_event
from ..logging_config import logger

router = APIRouter(tags=["webhook"])

import asyncio
import json
from pathlib import Path

jira_watcher_instance = get_jira_watcher()

DATA_DIR = Path(__file__).parent.parent / "data"
PROCESSED_FILE = DATA_DIR / "processed_webhooks.json"

# In-memory deduplication cache for webhooks
# Stores hashes of (message_id or content_payload) to prevent duplicate processing within a short window
_PROCESSED_WEBHOOKS = set()
_DEDUPLICATION_WINDOW = 1000  # Keep last 1000 processed IDs
_DEDUPLICATION_LOCK = asyncio.Lock()

def _load_processed_webhooks():
    if PROCESSED_FILE.exists():
        try:
            with open(PROCESSED_FILE, "r") as f:
                ids = json.load(f)
                if isinstance(ids, list):
                    _PROCESSED_WEBHOOKS.update(ids)
                    logger.info(f"Loaded {len(_PROCESSED_WEBHOOKS)} processed webhook keys from disk.")
        except Exception as e:
            logger.warning(f"Failed to load processed webhooks: {e}")

def _save_processed_webhooks():
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(PROCESSED_FILE, "w") as f:
            # Only save the last _DEDUPLICATION_WINDOW items
            to_save = list(_PROCESSED_WEBHOOKS)[-_DEDUPLICATION_WINDOW:]
            json.dump(to_save, f)
    except Exception as e:
        logger.warning(f"Failed to save processed webhooks: {e}")

# Initial load
_load_processed_webhooks()

async def is_duplicate_webhook(payload: dict, trigger_type: str, actual_data: dict) -> bool:
    """Check if this webhook has already been processed recently."""
    import hashlib
    import json
    
    # 1. Primary key: Jira Business Key (Robust against multiple triggers/retries)
    # We use issue_key and an event timestamp which are immutable for the same event.
    issue_key = actual_data.get("issue_key")
    # New issues have created_at, updates have updated_at
    timestamp = actual_data.get("updated_at") or actual_data.get("created_at")
    
    if issue_key and timestamp:
        unique_key = f"JIRA:{issue_key}:{timestamp}"
    else:
        # 2. Secondary key: Message ID from Composio
        msg_id = payload.get("id")
        
        # 3. Tertiary key: Hash of the actual event data
        try:
            data_str = json.dumps(actual_data, sort_keys=True)
            content_hash = hashlib.md5(f"{trigger_type}:{data_str}".encode()).hexdigest()
        except Exception:
            content_hash = str(actual_data)

        unique_key = msg_id if msg_id else content_hash
    
    async with _DEDUPLICATION_LOCK:
        if unique_key in _PROCESSED_WEBHOOKS:
            logger.info(f"Duplicate detected: {unique_key}")
            return True
            
        # Add to set and maintain window size
        _PROCESSED_WEBHOOKS.add(unique_key)
        if len(_PROCESSED_WEBHOOKS) > _DEDUPLICATION_WINDOW:
            # Simple pop (random-ish in sets, but fine for a sliding window of this size)
            _PROCESSED_WEBHOOKS.remove(next(iter(_PROCESSED_WEBHOOKS)))
            
        _save_processed_webhooks()
        return False

@router.post("/webhook")
async def webhook(payload: dict, background_tasks: BackgroundTasks) -> JSONResponse:
    logger.info(f"\n\n\n\nWebhook received:{payload}")
    
    # Extract the actual trigger type from payload or metadata
    trigger_type = str(payload.get("type"))
    actual_data = payload
    
    if trigger_type == "composio.trigger.message":
        metadata = payload.get("metadata", {})
        trigger_type = str(metadata.get("trigger_slug"))
        actual_data = payload.get("data", {})
        logger.info(f"Extracted trigger type from metadata: {trigger_type}")

    # Deduplication check
    if await is_duplicate_webhook(payload, trigger_type, actual_data):
        logger.info(f"Skipping duplicate webhook: type={trigger_type}, id={payload.get('id')}")
        return JSONResponse(content={"status": "ok", "detail": "duplicate ignored"})

    # Offload processing to background and respond immediately to prevent timeout/retry
    background_tasks.add_task(async_webhook_processor, trigger_type, actual_data, payload)
    
    return JSONResponse(content={"status": "ok", "detail": "processing started"})

async def async_webhook_processor(trigger_type: str, actual_data: dict, full_payload: dict) -> None:
    """Handles the actual processing of the webhook in the background."""
    try:
        if trigger_type == "JIRA_NEW_PROJECT_TRIGGER":
            await jira_watcher_instance.process_project_payload(payload=actual_data)
        elif trigger_type == "JIRA_NEW_ISSUE_TRIGGER":
            await jira_watcher_instance.process_issue_payload(actual_data)
        elif trigger_type == "JIRA_UPDATED_ISSUE_TRIGGER":
            await jira_watcher_instance.process_update_payload(actual_data)
        elif trigger_type == "GOOGLECALENDAR_ATTENDEE_RESPONSE_CHANGED_TRIGGER":
            await process_event(actual_data)
        else:
            logger.warning(f"Unknown webhook type: {trigger_type}. Full payload: {full_payload}")
    except Exception as e:
        logger.error(f"Error processing background webhook: {e}", exc_info=True)