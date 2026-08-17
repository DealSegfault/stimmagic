"""
Cloudflare Tunnel Service for Stimma.
Manages running `cloudflared tunnel --url http://127.0.0.1:{port}`.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import signal
from typing import Optional

from core.logging import get_logger
from utils.websocket import ws_manager

log = get_logger(__name__)

CLOUDFLARED_COMMON_PATHS = [
    "/opt/homebrew/bin/cloudflared",
    "/usr/local/bin/cloudflared",
    os.path.expanduser("~/.local/bin/cloudflared"),
    os.path.expanduser("~/bin/cloudflared"),
    os.path.expanduser("~/go/bin/cloudflared"),
    "/usr/bin/cloudflared",
]

TRY_CLOUDFLARE_REGEX = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


def find_cloudflared_executable() -> Optional[str]:
    """Find the path to the cloudflared executable."""
    found = shutil.which("cloudflared")
    if found and os.path.isfile(found) and os.access(found, os.X_OK):
        return found

    for candidate in CLOUDFLARED_COMMON_PATHS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    return None


class TunnelService:
    """Singleton service to manage the cloudflared quick tunnel."""

    _instance: Optional[TunnelService] = None

    def __init__(self):
        self._process: Optional[asyncio.subprocess.Process] = None
        self._tunnel_url: Optional[str] = None
        self._is_starting: bool = False
        self._is_running: bool = False
        self._error: Optional[str] = None
        self._started_at: Optional[float] = None
        self._port: int = 9192
        self._reader_task: Optional[asyncio.Task] = None

    @classmethod
    def get_instance(cls) -> TunnelService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_status(self) -> dict:
        executable = find_cloudflared_executable()
        return {
            "running": self._is_running and bool(self._tunnel_url),
            "starting": self._is_starting,
            "url": self._tunnel_url if self._is_running else None,
            "error": self._error,
            "installed": bool(executable),
            "executable_path": executable,
            "port": self._port,
            "started_at": self._started_at,
        }

    async def _broadcast_status(self):
        status = self.get_status()
        try:
            await ws_manager.broadcast("tunnel_status_changed", status)
        except Exception as e:
            log.warning("failed to broadcast tunnel status", error=str(e))

    async def start_tunnel(self, port: int = 9192) -> dict:
        """Start cloudflared tunnel pointing to http://127.0.0.1:{port}."""
        if self._is_running and self._tunnel_url:
            return self.get_status()

        executable = find_cloudflared_executable()
        if not executable:
            self._error = "cloudflared non trouvé. Installez-le avec `brew install cloudflared`."
            self._is_running = False
            self._is_starting = False
            await self._broadcast_status()
            return self.get_status()

        self._port = port
        self._is_starting = True
        self._error = None
        self._tunnel_url = None
        await self._broadcast_status()

        try:
            target_url = f"http://127.0.0.1:{port}"
            log.info("starting cloudflared tunnel", executable=executable, target_url=target_url)

            # cloudflared logs quick tunnel connection details to stderr
            self._process = await asyncio.create_subprocess_exec(
                executable,
                "tunnel",
                "--url",
                target_url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            url_future = asyncio.get_running_loop().create_future()
            self._reader_task = asyncio.create_task(self._read_tunnel_logs(self._process, url_future))

            # Wait up to 20 seconds for the trycloudflare URL to be output
            try:
                found_url = await asyncio.wait_for(url_future, timeout=20.0)
                self._tunnel_url = found_url
                self._is_running = True
                self._is_starting = False
                self._started_at = asyncio.get_running_loop().time()
                log.info("cloudflared tunnel ready", url=found_url)
                await self._broadcast_status()
            except asyncio.TimeoutError:
                log.error("cloudflared tunnel url lookup timed out")
                self._error = "Délai d'attente dépassé pour la création de l'URL Cloudflare."
                self._is_starting = False
                await self._broadcast_status()

        except Exception as e:
            log.exception("failed to start cloudflared tunnel")
            self._error = str(e)
            self._is_starting = False
            self._is_running = False
            await self._broadcast_status()

        return self.get_status()

    async def _read_tunnel_logs(self, process: asyncio.subprocess.Process, url_future: asyncio.Future):
        """Read stderr/stdout in background to extract tunnel URL and monitor process."""
        async def read_stream(stream, is_stderr=True):
            while True:
                line_bytes = await stream.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                log.debug("cloudflared log", line=line)

                # Look for trycloudflare URL
                match = TRY_CLOUDFLARE_REGEX.search(line)
                if match and not url_future.done():
                    url_future.set_result(match.group(0))

        try:
            await asyncio.gather(
                read_stream(process.stderr, is_stderr=True),
                read_stream(process.stdout, is_stderr=False),
            )
            # Process terminated
            return_code = await process.wait()
            log.info("cloudflared process terminated", return_code=return_code)
            self._is_running = False
            self._is_starting = False
            self._tunnel_url = None
            if return_code != 0 and not self._error:
                self._error = f"cloudflared s'est arrêté avec le code {return_code}"
            await self._broadcast_status()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.exception("error reading cloudflared logs")

    async def stop_tunnel(self) -> dict:
        """Stop the running cloudflared tunnel."""
        log.info("stopping cloudflared tunnel")
        self._is_starting = False

        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()

        if self._process:
            try:
                if self._process.returncode is None:
                    self._process.send_signal(signal.SIGTERM)
                    try:
                        await asyncio.wait_for(self._process.wait(), timeout=3.0)
                    except asyncio.TimeoutError:
                        self._process.kill()
                        await self._process.wait()
            except Exception as e:
                log.warning("error while stopping cloudflared process", error=str(e))
            finally:
                self._process = None

        self._is_running = False
        self._tunnel_url = None
        self._error = None
        self._started_at = None
        await self._broadcast_status()
        return self.get_status()


tunnel_service = TunnelService.get_instance()
