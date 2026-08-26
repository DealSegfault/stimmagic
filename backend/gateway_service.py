"""
Gateway Service for Stimma.
Manages the local Modal H3 gateway (modal_bridge.py on 8190 and ComfyUI STP on 8188).
"""
from __future__ import annotations

import asyncio
import os
import signal
import socket
import subprocess
from pathlib import Path
from typing import Optional

from core.logging import get_logger
from utils.websocket import ws_manager

log = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
GATEWAY_SCRIPT = REPO_ROOT / "infra" / "bin" / "start-gateway.sh"


def is_port_listening(port: int, host: str = "127.0.0.1") -> bool:
    """Check whether a TCP port is open and listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


class GatewayService:
    """Singleton service to manage the local ComfyUI Modal gateway."""

    _instance: Optional[GatewayService] = None

    def __init__(self):
        self._process: Optional[asyncio.subprocess.Process] = None
        self._is_starting: bool = False
        self._error: Optional[str] = None
        self._monitor_task: Optional[asyncio.Task] = None

    @classmethod
    def get_instance(cls) -> GatewayService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_status(self) -> dict:
        stp_listening = is_port_listening(8188)
        bridge_listening = is_port_listening(8190)
        is_running = stp_listening and bridge_listening
        is_partial = (stp_listening or bridge_listening) and not is_running

        return {
            "running": is_running,
            "partial": is_partial,
            "starting": self._is_starting,
            "stp_port": 8188,
            "bridge_port": 8190,
            "stp_listening": stp_listening,
            "bridge_listening": bridge_listening,
            "url": "http://127.0.0.1:8188",
            "error": self._error,
            "script_exists": GATEWAY_SCRIPT.is_file(),
        }

    async def _broadcast_status(self):
        status = self.get_status()
        try:
            await ws_manager.broadcast("gateway_status_changed", status)
        except Exception as e:
            log.warning("failed to broadcast gateway status", error=str(e))

    async def start_gateway(self) -> dict:
        """Start the gateway supervisor script in the background."""
        status = self.get_status()
        if status["running"]:
            return status

        if not GATEWAY_SCRIPT.is_file():
            self._error = f"Script introuvable : {GATEWAY_SCRIPT}"
            await self._broadcast_status()
            return self.get_status()

        self._is_starting = True
        self._error = None
        await self._broadcast_status()

        try:
            log.info("Starting gateway supervisor", script=str(GATEWAY_SCRIPT))
            self._process = await asyncio.create_subprocess_exec(
                str(GATEWAY_SCRIPT),
                cwd=str(REPO_ROOT),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )

            # Poll for readiness up to 10 seconds
            for _ in range(20):
                await asyncio.sleep(0.5)
                cur = self.get_status()
                if cur["running"]:
                    break

            self._is_starting = False
            await self._broadcast_status()
            return self.get_status()
        except Exception as e:
            log.error("Failed to start gateway", error=str(e))
            self._error = str(e)
            self._is_starting = False
            await self._broadcast_status()
            return self.get_status()

    async def stop_gateway(self) -> dict:
        """Stop the running gateway processes."""
        self._is_starting = False
        try:
            # Terminate supervised subprocess group if exists
            if self._process and self._process.returncode is None:
                try:
                    os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
                self._process = None

            # Cleanly kill any orphan processes on ports 8188 and 8190
            subprocess.run(
                "lsof -ti :8188 -ti :8190 | xargs kill -9 2>/dev/null || true",
                shell=True,
                check=False,
            )
            await asyncio.sleep(0.5)
        except Exception as e:
            log.error("Error stopping gateway", error=str(e))
            self._error = str(e)

        await self._broadcast_status()
        return self.get_status()


gateway_service = GatewayService.get_instance()
