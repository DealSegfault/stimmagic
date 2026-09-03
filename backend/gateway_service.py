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
PROJECT_ROOT = REPO_ROOT.parent

STP_PORT = 8188
BRIDGE_PORT = 8190
HD_BRIDGE_PORT = 8191


def _env_float(name: str, default: float, *, minimum: float = 0.1) -> float:
    """Read a bounded numeric gateway setting without breaking app startup."""
    try:
        return max(minimum, float(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


# Modal cold starts are allowed to take longer than the old hard-coded 10s.
START_TIMEOUT_SECONDS = _env_float("STIMMA_GATEWAY_START_TIMEOUT", 60.0, minimum=1.0)
POLL_INTERVAL_SECONDS = _env_float("STIMMA_GATEWAY_POLL_INTERVAL", 0.5)
GATEWAY_LOG_PATH = PROJECT_ROOT / "logs" / "gateway-service.log"


def _resolve_gateway_script() -> Path:
    """Resolve the gateway for this checkout's actual ComfyUI installation.

    The fork keeps ComfyUI at the workspace root, while upstream Stimma's
    optional infra launcher expects ``stimma/infra/.runtime/ComfyUI``.  The
    latter is not present on this installation, so the UI's Start button used
    to spawn a process that exited immediately and no H3 tools were exposed.
    An explicit override remains available for packaged/CI environments.
    """
    override = os.environ.get("STIMMA_GATEWAY_SCRIPT", "").strip()
    root_script = PROJECT_ROOT / "bin" / "start-gateway.sh"
    nested_script = REPO_ROOT / "infra" / "bin" / "start-gateway.sh"
    candidates = [Path(override).expanduser()] if override else []
    candidates.extend((root_script, nested_script))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return root_script


GATEWAY_SCRIPT = _resolve_gateway_script()


def is_port_listening(port: int, host: str = "127.0.0.1") -> bool:
    """Check whether a TCP port is open and listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def _h3_provider_configured() -> bool:
    """Return whether the local H3 STP provider is enabled in Stimma."""
    try:
        from config import get_settings

        return any(
            getattr(provider, "id", None) == "comfyui-modal-h3"
            and getattr(provider, "enabled", True)
            for provider in get_settings().tool_providers
        )
    except Exception:
        # Gateway status must remain usable even while settings/providers are
        # still initializing during backend startup.
        return False


def _h3_provider_connected() -> bool:
    """Return whether the H3 provider completed its STP handshake."""
    try:
        from providers import ProviderRegistry
        from providers.base import ProviderStatus

        provider = ProviderRegistry.get_instance().get_provider("comfyui-modal-h3")
        return bool(provider and provider.status == ProviderStatus.CONNECTED)
    except Exception:
        return False


def _gateway_process_command(pid: int) -> str:
    """Read a process command line, returning an empty string on failure."""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip()
    except OSError:
        return ""


def _is_gateway_process(command: str) -> bool:
    """Avoid killing the Stimma backend when cleaning orphan gateway ports."""
    return any(
        marker in command
        for marker in (
            "modal_bridge.py",
            "modal_account_bridges.py",
            "/bin/start-gateway.sh",
            "/infra/bin/start-gateway.sh",
        )
    ) or ("main.py --cpu" in command and "--port 8188" in command)


def _kill_orphan_gateway_processes() -> None:
    """Terminate gateway listeners left behind by a crashed supervisor.

    The old shell pipeline killed every process returned by ``lsof``.  This
    is unnecessarily broad and made a gateway restart capable of taking down
    the backend.  Only known gateway command lines are eligible now.
    """
    for port in (STP_PORT, BRIDGE_PORT, HD_BRIDGE_PORT):
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            continue
        for raw_pid in result.stdout.splitlines():
            try:
                pid = int(raw_pid.strip())
            except ValueError:
                continue
            if pid == os.getpid():
                continue
            if _is_gateway_process(_gateway_process_command(pid)):
                try:
                    os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass


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
        stp_listening = is_port_listening(STP_PORT)
        bridge_listening = is_port_listening(BRIDGE_PORT)
        is_running = stp_listening and bridge_listening
        is_partial = (stp_listening or bridge_listening) and not is_running

        return {
            "running": is_running,
            "partial": is_partial,
            "starting": self._is_starting,
            "stp_port": STP_PORT,
            "bridge_port": BRIDGE_PORT,
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
        if self._is_starting:
            return self.get_status()

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
            GATEWAY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with GATEWAY_LOG_PATH.open("ab") as gateway_log:
                self._process = await asyncio.create_subprocess_exec(
                    str(GATEWAY_SCRIPT),
                    cwd=str(REPO_ROOT),
                    stdout=gateway_log,
                    stderr=asyncio.subprocess.STDOUT,
                    start_new_session=True,
                )

            # Wait for both local services and the H3 STP handshake.  The
            # latter can lag behind the ports by several seconds while Modal
            # wakes up and the provider manager retries its WebSocket.
            deadline = asyncio.get_running_loop().time() + START_TIMEOUT_SECONDS
            wait_for_provider = _h3_provider_configured()
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                if self._process and self._process.returncode is not None:
                    code = self._process.returncode
                    self._error = (
                        f"Le superviseur H3 s’est arrêté prématurément (code {code}). "
                        f"Consultez {GATEWAY_LOG_PATH}."
                    )
                    break
                cur = self.get_status()
                if cur["running"] and (
                    not wait_for_provider or _h3_provider_connected()
                ):
                    break

            final_status = self.get_status()
            if not final_status["running"] and not self._error:
                self._error = (
                    f"La passerelle H3 n’est pas prête après {START_TIMEOUT_SECONDS:g} s "
                    f"(STP {STP_PORT}, bridge {BRIDGE_PORT}). "
                    f"Consultez {GATEWAY_LOG_PATH}."
                )
            elif (
                final_status["running"]
                and wait_for_provider
                and not _h3_provider_connected()
                and not self._error
            ):
                self._error = (
                    "La passerelle locale répond, mais le provider H3 n’a pas terminé "
                    f"sa connexion après {START_TIMEOUT_SECONDS:g} s."
                )

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

            # Clean only known gateway processes on all three gateway ports;
            # never use a broad shell pipeline that could target the backend.
            _kill_orphan_gateway_processes()
            await asyncio.sleep(0.5)
            self._error = None
        except Exception as e:
            log.error("Error stopping gateway", error=str(e))
            self._error = str(e)

        await self._broadcast_status()
        return self.get_status()


gateway_service = GatewayService.get_instance()
