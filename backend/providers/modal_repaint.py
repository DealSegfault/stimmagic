"""Cloud FLUX.1 Fill provider for the image editor.

The diffusion model never runs in Stimma. This provider only uploads the
editor's source/mask bytes to the authenticated Modal web app and streams the
completed PNG back into the canonical generation queue.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .base import ExecutionProgress, ExecutionResult, ProviderStatus, ToolDescriptor, ToolProvider


class ModalRepaintProvider(ToolProvider):
    provider_id = "modal-repaint"
    provider_name = "Stimma Repaint · Modal"
    provider_type = "builtin"
    max_concurrent = 1

    def __init__(self):
        self._status = ProviderStatus.DISCONNECTED
        self._assets: dict[str, bytes] = {}

    @property
    def status(self): return self._status

    async def connect(self):
        self._status = ProviderStatus.CONNECTED

    async def disconnect(self):
        self._status = ProviderStatus.DISCONNECTED
        self._assets.clear()

    async def upload_asset(self, data: bytes, mime_type: str) -> str:
        key = f"repaint_{uuid.uuid4().hex}"
        self._assets[key] = data
        return key

    async def download_asset(self, asset_id: str) -> bytes:
        return self._assets[asset_id]

    async def list_tools(self):
        return [ToolDescriptor(
            id="flux-fill:inpaint-image", name="FLUX.1 Fill Repaint (cloud)", task_type="inpaint-image", task_types=["inpaint-image"],
            parameter_schema={"type": "object", "properties": {
                "prompt": {"type": "string", "x-label": "Prompt", "minLength": 1},
                "input_images": {"type": "array", "items": {"type": "string", "format": "file-path"}, "minItems": 1, "maxItems": 1, "x-control": "image_picker"},
                "mask": {"type": "string", "format": "file-path", "x-mask-format": "white-black", "x-control": "mask_picker"},
                "steps": {"type": "integer", "default": 28, "minimum": 8, "maximum": 50},
                "guidance": {"type": "number", "default": 30.0, "minimum": 1, "maximum": 50},
                "seed": {"type": "integer", "minimum": 0},
            }, "required": ["prompt", "input_images", "mask"]},
            output_schema={"type": "object", "properties": {"image": {"type": "string", "format": "file-path"}}},
            model_vendor="Black Forest Labs", model="FLUX.1 Fill [dev]", subtitle="Modal · L40S 48 GB · cloud only",
            description="Repaint a masked region with FLUX.1 Fill. The model runs on a provisioned NVIDIA L40S 48 GB GPU.",
            metadata={"provider": "Modal", "gpu": "L40S", "gpuMemoryGb": 48, "cloud_only": True, "lineage": "canonical"},
        )]

    @staticmethod
    def _data_url(path: str, default_mime: str = "image/png") -> str:
        raw = Path(path).read_bytes()
        mime = "image/jpeg" if Path(path).suffix.lower() in {".jpg", ".jpeg"} else default_mime
        return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")

    @staticmethod
    def _request(url: str, method: str, payload: dict, token: str) -> dict:
        body = json.dumps(payload).encode()
        request = Request(url, data=body, method=method, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
        with urlopen(request, timeout=45) as response:
            return json.loads(response.read())

    async def execute(self, tool_id: str, parameters: Dict[str, Any], output_path: Optional[str] = None, progress_callback=None, request_id=None) -> AsyncIterator[Any]:
        started = time.perf_counter()
        # Match H3: Stimma talks to the local authenticated Modal bridge. The
        # bridge owns Modal proxy credentials and optionally forwards /repaint
        # to the dedicated serverless Repaint web app.
        endpoint = os.environ.get("STIMMA_REPAINT_BRIDGE_URL", "http://127.0.0.1:8190/repaint").rstrip("/")
        token = os.environ.get("STIMMA_REPAINT_API_TOKEN", "")
        if not endpoint:
            yield ExecutionResult(success=False, error="Repaint bridge non configuré.")
            return
        source = (parameters.get("input_images") or [None])[0]
        mask = parameters.get("mask")
        prompt = str(parameters.get("prompt") or "").strip()
        if not source or not Path(str(source)).is_file() or not mask or not Path(str(mask)).is_file() or not prompt:
            yield ExecutionResult(success=False, error="Repaint exige une image source, un masque lisible et un prompt non vide.")
            return
        try:
            job = await asyncio.to_thread(self._request, endpoint + "/jobs", "POST", {"sourceImage": self._data_url(str(source)), "maskImage": self._data_url(str(mask)), "prompt": prompt, "seed": parameters.get("seed"), "steps": int(parameters.get("steps", 28)), "guidance": float(parameters.get("guidance", 30.0))}, token)
            if job.get("error"): raise RuntimeError(job["error"].get("message", "Modal Repaint request failed"))
            job_id = job.get("id")
            if not job_id: raise RuntimeError("Modal Repaint did not return a job id")
            while True:
                await asyncio.sleep(max(0.5, float(job.get("pollAfterMs", 2500)) / 1000))
                state = await asyncio.to_thread(self._request, endpoint + "/jobs/" + str(job_id), "GET", {}, token)
                if progress_callback: progress_callback(ExecutionProgress(progress=0.5, stage="Modal FLUX.1 Fill", message="GPU L40S 48 GB en cours"))
                if state.get("status") == "completed":
                    image = state.get("output", {}).get("image", "")
                    encoded = image.split(",", 1)[1] if "," in image else image
                    output = base64.b64decode(encoded)
                    if output_path: Path(output_path).write_bytes(output)
                    yield ExecutionResult(success=True, output_data=output, generation_time=time.perf_counter() - started, metadata={**(state.get("metadata") or {}), "provider": "Modal", "gpu": "L40S", "gpuMemoryGb": 48, "model": "FLUX.1 Fill [dev]"})
                    return
                if state.get("status") == "failed" or state.get("error"):
                    raise RuntimeError((state.get("error") or {}).get("message", "Modal Repaint failed"))
        except (HTTPError, URLError, TimeoutError, ValueError, OSError, RuntimeError) as exc:
            yield ExecutionResult(success=False, error=str(exc))
