"""
API routes for managing Cloudflare quick tunnels.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import get_settings
from tunnel_service import tunnel_service

router = APIRouter(prefix="/api/tunnel", tags=["tunnel"])


class StartTunnelRequest(BaseModel):
    port: Optional[int] = None


@router.get("/status")
async def get_tunnel_status():
    """Get current status of the Cloudflare tunnel."""
    return tunnel_service.get_status()


@router.post("/start")
async def start_tunnel(req: Optional[StartTunnelRequest] = None):
    """Start cloudflared tunnel for the Stimma local server."""
    port = req.port if req and req.port else get_settings().server.port
    if not port:
        port = 9192
    status = await tunnel_service.start_tunnel(port=port)
    if status.get("error") and not status.get("running"):
        raise HTTPException(status_code=500, detail=status.get("error"))
    return status


@router.post("/stop")
async def stop_tunnel():
    """Stop the running cloudflared tunnel."""
    return await tunnel_service.stop_tunnel()
