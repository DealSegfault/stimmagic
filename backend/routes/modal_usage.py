"""Modal account usage and generation tracking API."""
from __future__ import annotations

from fastapi import APIRouter, Query

from modal_usage_service import get_modal_usage_service

router = APIRouter(prefix="/api/modal", tags=["modal-usage"])


@router.get("/usage")
async def get_modal_usage(limit: int = Query(default=50, ge=1, le=200)):
    """Return redacted account totals and recent generation usage."""
    return get_modal_usage_service().snapshot(limit=limit)


@router.get("/accounts")
async def get_modal_accounts():
    """Return account health/budget metadata without credentials."""
    return get_modal_usage_service().snapshot(limit=1)["accounts"]


@router.get("/pricing")
async def get_modal_pricing():
    """Return the standard Modal resource rates used by cost estimates."""
    return get_modal_usage_service().snapshot(limit=1)["pricing"]


@router.get("/health")
async def get_modal_router_health():
    snapshot = get_modal_usage_service().snapshot(limit=1)
    return {
        "configured": snapshot["configured"],
        "accounts": [
            {"id": item["id"], "status": item["status"], "active_jobs": item["active_jobs"]}
            for item in snapshot["accounts"]
        ],
    }
