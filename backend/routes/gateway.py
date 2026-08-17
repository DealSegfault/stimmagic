"""
API routes for managing the local Modal H3 gateway.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from gateway_service import gateway_service

router = APIRouter(prefix="/api/gateway", tags=["gateway"])


@router.get("/status")
async def get_gateway_status():
    """Get current status of the Modal ComfyUI gateway (ports 8188 & 8190)."""
    return gateway_service.get_status()


@router.post("/start")
async def start_gateway():
    """Start the local Modal ComfyUI gateway."""
    status = await gateway_service.start_gateway()
    if status.get("error") and not status.get("running"):
        raise HTTPException(status_code=500, detail=status.get("error"))
    return status


@router.post("/stop")
async def stop_gateway():
    """Stop the local Modal ComfyUI gateway."""
    return await gateway_service.stop_gateway()
