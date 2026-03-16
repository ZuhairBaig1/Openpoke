from __future__ import annotations

from fastapi import APIRouter

from .chat import router as chat_router
from .gmail import router as gmail_router
from .jira import router as jira_router
from .meta import router as meta_router
from .calendar import router as calendar_router
from .webhook import router as webhook_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(meta_router)
api_router.include_router(chat_router)
api_router.include_router(gmail_router)
api_router.include_router(jira_router)
api_router.include_router(calendar_router)
api_router.include_router(webhook_router)

__all__ = ["api_router"]
