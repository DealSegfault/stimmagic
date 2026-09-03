"""Multi-instance ComfyUI client for load balancing across GPUs."""

import uuid
import json
import logging
import os
import asyncio
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Dict, Any, Optional, AsyncIterator

import aiohttp

logger = logging.getLogger(__name__)


def _routing_state_path() -> Path:
    configured = os.environ.get("MODAL_ROUTER_STATE_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".config" / "adp-comfy" / "modal-router.state.json"


def _read_routing_state() -> dict:
    try:
        payload = json.loads(_routing_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {"mode": "auto", "account_id": None}
    mode = payload.get("mode") if isinstance(payload, dict) else "auto"
    return {
        "mode": mode if mode in {"auto", "fixed"} else "auto",
        "account_id": payload.get("account_id") if isinstance(payload, dict) else None,
    }


def _uploaded_reference_name(
    response: Dict[str, Any],
    fallback: str,
    default_type: str = "input",
) -> str:
    """Return the ComfyUI filename format accepted by annotated_filepath.

    ComfyUI's upload endpoint returns ``name`` separately from ``subfolder``
    and ``type``.  Passing only ``name`` works for files uploaded directly to
    the input root, but loses the location for uploads routed into a subfolder
    (and loses the type annotation for output/temp files).  The field nodes
    validate the complete annotated path, so preserve all of the response
    fields when handing the reference to the workflow executor.
    """
    if not isinstance(response, dict):
        return fallback

    name = str(response.get("name") or fallback).strip()
    subfolder = str(response.get("subfolder") or "").strip("/")
    if subfolder:
        name = f"{subfolder}/{name}"

    file_type = str(response.get("type") or default_type).strip()
    if file_type and file_type != default_type:
        name = f"{name} [{file_type}]"
    return name


def parse_addresses(addresses) -> List[str]:
    """Parse various address input formats into a list of individual addresses.

    Handles: list, single string, comma-separated, port ranges (host:8188-8191).
    """
    if isinstance(addresses, str):
        addresses = [addr.strip() for addr in addresses.split(",")]
    elif not isinstance(addresses, list):
        addresses = [str(addresses)]

    expanded = []
    for addr in addresses:
        if ":" not in addr:
            expanded.append(addr)
            continue
        host, port_spec = addr.rsplit(":", 1)
        if "-" in port_spec:
            start, end = map(int, port_spec.split("-"))
            expanded.extend(f"{host}:{port}" for port in range(start, end + 1))
        else:
            expanded.append(addr)

    return expanded


class SingleComfy:
    """Client for a single ComfyUI instance."""

    def __init__(self, addr: str, account_id: Optional[str] = None, is_modal_bridge: bool = False):
        self.addr = addr
        self.account_id = account_id
        self.is_modal_bridge = is_modal_bridge or addr.rsplit(":", 1)[-1] in {"8190", "8191"}
        self.client_id = str(uuid.uuid4())
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get (or lazily create) a keep-alive HTTP session for this instance.

        Reusing one session across requests keeps the TCP connection to ComfyUI
        warm instead of doing a fresh connect/teardown on every /prompt,
        /history, /object_info and /upload call. Created lazily so it binds to
        the running STP event loop.
        """
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(auto_decompress=False)
        return self._session

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        """Make an HTTP request to the ComfyUI server."""
        session = await self._get_session()
        url = f"http://{self.addr}{path}"
        # The local Modal bridge owns proxy authentication and follows any
        # authenticated upstream redirect. Never let this client follow an
        # absolute Modal redirect itself, because it has no proxy credentials.
        kwargs.setdefault("allow_redirects", False)
        async with session.request(method, url, **kwargs) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise RuntimeError(
                    f"ComfyUI {method} {path} failed ({resp.status}): {error_text}"
                )
            raw = await resp.read()
            try:
                return json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return raw

    async def queue_prompt(
        self, prompt: Dict[str, Any], preview_frames: bool = True
    ) -> Dict[str, Any]:
        """Queue a workflow prompt for execution.

        preview_frames=False asks ComfyUI not to decode previews at all for
        this prompt. That matters: the decode runs per sampler step on the GPU
        worker, so suppressing only the delivery would leave the cost in place
        while nothing consumes it.
        """
        # preview_method is applied per-prompt by ComfyUI's executor
        # (set_preview_method(extra_data.get("preview_method")) resets the
        # global setting on EVERY execution, so a startup-time override alone
        # is wiped). taesd uses tiny-VAE decoders from models/vae_approx when
        # present and falls back to latent2rgb otherwise.
        data = json.dumps({
            "prompt": prompt,
            "client_id": self.client_id,
            "extra_data": {
                "preview_method": "taesd" if preview_frames else "none",
                # Marks the prompt as ours. The sampling process is usually a
                # DIFFERENT ComfyUI instance than the one hosting this server,
                # so the previewer there has no other way to tell our jobs from
                # ones the user started in their own browser.
                "stimma_preview": bool(preview_frames),
            },
        })
        result = await self._request(
            "POST", "/prompt",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        # Check for validation/prompt errors in response body
        if "error" in result:
            error_info = result["error"]
            if isinstance(error_info, dict):
                error_msg = error_info.get("message", str(error_info))
            else:
                error_msg = str(error_info)
            node_errors = result.get("node_errors", {})
            if node_errors:
                # Summarize first few node errors
                details = []
                for nid, nerr in list(node_errors.items())[:3]:
                    errs = nerr.get("errors", []) if isinstance(nerr, dict) else []
                    for e in errs[:1]:
                        details.append(
                            f"node #{nid}: {e.get('message', str(e))}"
                        )
                if details:
                    error_msg += " — " + "; ".join(details)
            raise RuntimeError(f"ComfyUI prompt validation error: {error_msg}")
        if not result.get("prompt_id"):
            raise RuntimeError(f"ComfyUI response missing prompt_id: {result}")
        logger.debug(f"Queued prompt {result['prompt_id']} on {self.addr}")
        return result

    async def get_history(self, prompt_id: str) -> Dict[str, Any]:
        """Get execution history for a prompt."""
        return await self._request("GET", f"/history/{prompt_id}")

    async def delete_history(self, prompt_id: str) -> None:
        """Delete a prompt's history entry (holds prompt text + output refs)."""
        await self._request("POST", "/history", json={"delete": [prompt_id]})

    async def get_object_info(self) -> Dict[str, Any]:
        """Get available nodes, models, samplers, etc."""
        return await self._request("GET", "/object_info")

    async def upload_image(
        self, image_path: str, image_type: str = "input", overwrite: bool = True
    ) -> str:
        """Upload an image to ComfyUI's input directory."""
        from pathlib import Path

        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")

        filename = Path(image_path).name

        ext = Path(image_path).suffix.lower()
        content_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        content_type = content_type_map.get(ext, "image/png")
        session = await self._get_session()
        with open(image_path, "rb") as f:
            form_data = aiohttp.FormData()
            form_data.add_field("image", f, filename=filename, content_type=content_type)
            form_data.add_field("type", image_type)
            form_data.add_field("overwrite", str(overwrite).lower())

            async with session.post(
                f"http://{self.addr}/upload/image",
                data=form_data,
                allow_redirects=False,
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"Image upload failed ({resp.status}): {error_text}")
                raw = await resp.read()
                response = json.loads(raw.decode("utf-8"))
                return _uploaded_reference_name(response, filename)

    async def upload_video(self, video_path: str, overwrite: bool = True) -> str:
        """Upload a video to ComfyUI's input directory."""
        from pathlib import Path

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        filename = Path(video_path).name
        ext = Path(video_path).suffix.lower()
        content_type_map = {
            ".mp4": "video/mp4", ".webm": "video/webm",
            ".mov": "video/quicktime", ".avi": "video/x-msvideo",
        }
        content_type = content_type_map.get(ext, "video/mp4")

        session = await self._get_session()
        with open(video_path, "rb") as f:
            form_data = aiohttp.FormData()
            form_data.add_field("image", f, filename=filename, content_type=content_type)
            form_data.add_field("type", "input")
            form_data.add_field("overwrite", str(overwrite).lower())

            async with session.post(
                f"http://{self.addr}/upload/image",
                data=form_data,
                allow_redirects=False,
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"Video upload failed ({resp.status}): {error_text}")
                raw = await resp.read()
                response = json.loads(raw.decode("utf-8"))
                return _uploaded_reference_name(response, filename)

    async def upload_audio(self, audio_path: str, overwrite: bool = True) -> str:
        """Upload an audio file to ComfyUI's input directory."""
        from pathlib import Path

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        filename = Path(audio_path).name
        ext = Path(audio_path).suffix.lower()
        content_type_map = {
            ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
            ".flac": "audio/flac", ".ogg": "audio/ogg", ".opus": "audio/opus",
        }
        content_type = content_type_map.get(ext, "audio/wav")

        session = await self._get_session()
        with open(audio_path, "rb") as f:
            form_data = aiohttp.FormData()
            # /upload/image takes every input file type under the "image" field.
            form_data.add_field("image", f, filename=filename, content_type=content_type)
            form_data.add_field("type", "input")
            form_data.add_field("overwrite", str(overwrite).lower())

            async with session.post(
                f"http://{self.addr}/upload/image",
                data=form_data,
                allow_redirects=False,
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"Audio upload failed ({resp.status}): {error_text}")
                raw = await resp.read()
                response = json.loads(raw.decode("utf-8"))
                return _uploaded_reference_name(response, filename)

    async def interrupt(self) -> bool:
        """Interrupt current execution."""
        try:
            session = await self._get_session()
            async with session.post(
                f"http://{self.addr}/interrupt", allow_redirects=False
            ) as resp:
                return resp.status == 200
        except aiohttp.ClientError:
            return False

    async def clear_queue(self) -> bool:
        """Clear all pending prompts."""
        try:
            session = await self._get_session()
            async with session.post(
                f"http://{self.addr}/queue",
                json={"clear": True},
                allow_redirects=False,
            ) as resp:
                return resp.status == 200
        except aiohttp.ClientError:
            return False

    async def connect_ws(self, preview_frames: bool = True):
        """Create a websocket connection for progress monitoring.

        preview_frames: declare supports_preview_metadata so ComfyUI streams
        live sampler previews to this socket. Pass False (host disabled
        previews) to skip the declaration — ComfyUI then sends none, and our
        animated video previewer also skips its per-step assembly work.
        """
        session = aiohttp.ClientSession()
        try:
            ws = await session.ws_connect(
                f"http://{self.addr}/ws?clientId={self.client_id}",
                compress=0,
                heartbeat=30.0,
            )
            if preview_frames:
                # Feature-flag handshake: must be the FIRST client message.
                await ws.send_json(
                    {"type": "feature_flags", "data": {"supports_preview_metadata": True}}
                )
        except Exception:
            await session.close()
            raise
        ws._session = session  # attach so we can close it later
        return ws


class Comfy:
    """Multi-instance ComfyUI client.

    Exposes an `acquire()` context manager that hands out a `SingleComfy`
    instance for the full lifetime of a job (uploads → queue → monitor →
    capture). The instance is returned to the pool when the context exits,
    so the next job in line picks a *truly* idle GPU instead of dispatching
    based on POST latency.
    """

    def __init__(
        self,
        addresses,
        hd_address: Optional[str] = None,
        hd_min_megapixels: float = 2.0,
        hd_min_steps: int = 20,
        account_addresses: Optional[Dict[str, str]] = None,
        account_hd_addresses: Optional[Dict[str, str]] = None,
    ):
        self.addresses = parse_addresses(addresses)
        self.account_addresses = {
            str(account_id): addr
            for account_id, addr in (account_addresses or {}).items()
            if addr
        }
        self.account_hd_addresses = {
            str(account_id): addr
            for account_id, addr in (account_hd_addresses or {}).items()
            if addr
        }
        if self.account_addresses:
            self.normal_instances = [
                SingleComfy(addr, account_id=account_id, is_modal_bridge=True)
                for account_id, addr in self.account_addresses.items()
            ]
            self.addresses = [instance.addr for instance in self.normal_instances]
        else:
            self.normal_instances = [SingleComfy(addr) for addr in self.addresses]
        self.hd_min_megapixels = float(hd_min_megapixels)
        self.hd_min_steps = int(hd_min_steps)

        if self.account_hd_addresses:
            self.hd_instances_by_account = {
                account_id: SingleComfy(addr, account_id=account_id, is_modal_bridge=True)
                for account_id, addr in self.account_hd_addresses.items()
            }
            self.hd_instance = next(iter(self.hd_instances_by_account.values()), None)
        else:
            self.hd_instances_by_account = {}
            hd_addresses = parse_addresses(hd_address) if hd_address else []
            hd_addr = next(
                (addr for addr in hd_addresses if addr not in self.addresses),
                None,
            )
            self.hd_instance = SingleComfy(hd_addr, is_modal_bridge=True) if hd_addr else None
        self.instances = list(self.normal_instances)
        for instance in self.hd_instances_by_account.values():
            if instance not in self.instances:
                self.instances.append(instance)
        if not self.hd_instances_by_account and self.hd_instance is not None:
            self.instances.append(self.hd_instance)

        self._available: asyncio.Queue = asyncio.Queue()
        for inst in self.normal_instances:
            self._available.put_nowait(inst)
        self._available_by_account = {}
        self._available_instances_seeded = set()
        if self.account_addresses:
            for inst in self.normal_instances:
                queue = asyncio.Queue()
                queue.put_nowait(inst)
                self._available_by_account[inst.account_id] = queue
                self._available_instances_seeded.add(inst)
        self._hd_available: asyncio.Queue = asyncio.Queue()
        if self.hd_instances_by_account:
            self._hd_available_by_account = {}
            for account_id, instance in self.hd_instances_by_account.items():
                queue = asyncio.Queue()
                queue.put_nowait(instance)
                self._hd_available_by_account[account_id] = queue
        else:
            self._hd_available_by_account = {}
            if self.hd_instance is not None:
                self._hd_available.put_nowait(self.hd_instance)
        logger.info(
            "ComfyUI client initialized with normal instance(s)=%s, hd_instance=%s "
            "(threshold %.2f MP / %d steps)",
            self.addresses,
            (self.hd_instance.addr if self.hd_instance is not None else "disabled"),
            self.hd_min_megapixels,
            self.hd_min_steps,
        )

    @staticmethod
    def _number(value) -> Optional[float]:
        try:
            if isinstance(value, bool) or value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def is_hd_request(self, parameters: Optional[Dict[str, Any]]) -> bool:
        """Return whether a job belongs on the dedicated B300 HD worker."""
        parameters = parameters or {}
        width = self._number(parameters.get("width"))
        height = self._number(parameters.get("height"))
        steps = self._number(parameters.get("steps"))
        if width is None or height is None or steps is None:
            return False
        megapixels = (width * height) / 1_000_000.0
        return megapixels >= self.hd_min_megapixels and steps >= self.hd_min_steps

    @asynccontextmanager
    async def acquire(
        self, parameters: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[SingleComfy]:
        """Acquire the correct ComfyUI instance for the full job lifetime.

        HD jobs (at least 2 MP and 20 steps by default) exclusively use the
        B300 instance and never fall back to the normal GPU.
        """
        if not self.instances:
            raise RuntimeError("No ComfyUI instances configured")

        use_hd = self.is_hd_request(parameters)
        routing = _read_routing_state()
        requested_account = (parameters or {}).get("_modal_account_id") or routing.get("account_id")
        if routing.get("mode") != "fixed" and not (parameters or {}).get("_modal_account_id"):
            requested_account = None
        instance = None
        if use_hd:
            if requested_account and requested_account in self._hd_available_by_account:
                queue = self._hd_available_by_account[requested_account]
                instance = await queue.get()
            elif requested_account:
                # Backward-compatible single-bridge mode: an existing gateway
                # started before account-aware manifests still points at the
                # currently active Modal account.
                if not self.hd_instances_by_account and self.hd_instance is not None:
                    instance = await self._hd_available.get()
                else:
                    raise RuntimeError(
                        f"Modal account '{requested_account}' has no HD bridge configured."
                    )
            elif self.hd_instances_by_account:
                # Auto mode: wait for the first available configured HD account.
                instance = await self._get_first_available(self._hd_available_by_account)
            elif self.hd_instance is None:
                raise RuntimeError(
                    "An HD generation requires the B300 ComfyUI endpoint, "
                    "but no hd_address is configured."
                )
            else:
                instance = await self._hd_available.get()
        else:
            if not self.normal_instances:
                raise RuntimeError("No normal ComfyUI instance configured")
            if requested_account:
                selected = next(
                    (item for item in self.normal_instances if item.account_id == requested_account),
                    None,
                )
                if selected is None:
                    # Backward-compatible single-bridge mode (see the HD
                    # branch above). The gateway's one bridge is the active
                    # account until it is restarted with an account manifest.
                    if len(self.normal_instances) == 1 and self.normal_instances[0].account_id is None:
                        instance = await self._available.get()
                        selected = instance
                    else:
                        raise RuntimeError(
                            f"Modal account '{requested_account}' has no normal bridge configured."
                        )
                # The regular queue is shared for legacy instances. Account-aware
                # bridges get their own queue so fixed routing cannot leak jobs.
                if instance is None:
                    if not hasattr(self, "_available_by_account"):
                        self._available_by_account = {}
                    queue = self._available_by_account.setdefault(selected.account_id, asyncio.Queue())
                    if queue.empty() and selected not in self._available_instances_seeded:
                        queue.put_nowait(selected)
                        self._available_instances_seeded.add(selected)
                    instance = await queue.get()
            elif self.account_addresses:
                instance = await self._get_first_available(self._available_by_account)
            else:
                instance = await self._available.get()
        try:
            yield instance
        finally:
            if use_hd:
                if self.hd_instances_by_account:
                    self._hd_available_by_account[instance.account_id].put_nowait(instance)
                else:
                    self._hd_available.put_nowait(instance)
            else:
                if self.account_addresses:
                    self._available_by_account[instance.account_id].put_nowait(instance)
                else:
                    self._available.put_nowait(instance)

    @staticmethod
    async def _get_first_available(queues: Dict[str, asyncio.Queue]) -> SingleComfy:
        """Wait for any account queue without busy polling."""
        if not queues:
            raise RuntimeError("No account-aware ComfyUI instances configured")
        tasks = [asyncio.create_task(queue.get()) for queue in queues.values()]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        return next(iter(done)).result()

    async def get_object_info(self) -> Dict[str, Any]:
        """Get object info (samplers/schedulers/models). Uses the first instance.

        All instances are expected to expose equivalent node/model catalogs,
        so it doesn't matter which one we ask.
        """
        if not self.instances:
            raise RuntimeError("No ComfyUI instances configured")
        return await self.instances[0].get_object_info()

    async def interrupt_all(self) -> int:
        """Interrupt all instances. Returns count of successful interrupts."""
        results = await asyncio.gather(
            *[inst.interrupt() for inst in self.instances],
            return_exceptions=True,
        )
        return sum(1 for r in results if r is True)
