"""Antigravity / Nano Banana Pro provider for the image editor and generation queue.

This provider directly executes the Antigravity CLI (agy) using native generate_image
with the strict source-locked multi-zone inpainting and reference-fidelity system prompts,
bypassing the standard ComfyUI workflow framework.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from PIL import Image

import app_dirs
from agy_cli import _agy_executable
from core.logging import get_logger
from core.profile_context import get_current_profile
from .base import (
    ExecutionProgress,
    ExecutionResult,
    ProviderStatus,
    ToolDescriptor,
    ToolProvider,
)

log = get_logger(__name__)


class AntigravityImageProvider(ToolProvider):
    provider_id = "antigravity"
    provider_name = "Antigravity · Nano Banana Pro"
    provider_type = "builtin"
    max_concurrent = 2

    def __init__(self):
        self._status = ProviderStatus.DISCONNECTED
        self._assets: dict[str, bytes] = {}

    @property
    def status(self):
        return self._status

    async def connect(self):
        self._status = ProviderStatus.CONNECTED

    async def disconnect(self):
        self._status = ProviderStatus.DISCONNECTED
        self._assets.clear()

    async def upload_asset(self, data: bytes, mime_type: str) -> str:
        key = f"agy_{uuid.uuid4().hex}"
        self._assets[key] = data
        return key

    async def download_asset(self, asset_id: str) -> bytes:
        return self._assets[asset_id]

    async def list_tools(self) -> List[ToolDescriptor]:
        return [
            ToolDescriptor(
                id="nano-banana-pro:inpaint-image",
                name="Nano Banana Pro Inpaint (AGY CLI)",
                task_type="inpaint-image",
                task_types=["inpaint-image", "erase-image"],
                parameter_schema={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "x-label": "Prompt", "minLength": 1},
                        "input_images": {
                            "type": "array",
                            "items": {"type": "string", "format": "file-path"},
                            "minItems": 1,
                            "maxItems": 1,
                            "x-control": "image_picker",
                        },
                        "mask": {
                            "type": "string",
                            "format": "file-path",
                            "x-mask-format": "white-black",
                            "x-control": "mask_picker",
                        },
                        "reference_images": {
                            "type": "array",
                            "items": {"type": "string", "format": "file-path"},
                            "x-control": "reference_strip",
                        },
                        "seed": {"type": "integer", "minimum": 0},
                    },
                    "required": ["prompt", "input_images", "mask"],
                },
                output_schema={
                    "type": "object",
                    "properties": {"image": {"type": "string", "format": "file-path"}},
                },
                model_vendor="google",
                model="Nano Banana Pro",
                subtitle="AGY CLI · Source-locked inpainting",
                description="Repaint or edit a masked region using Nano Banana Pro via AGY CLI with strict source-locked multi-zone semantic edit directives.",
                metadata={
                    "provider": "Antigravity",
                    "model": "Nano Banana Pro",
                    "cli": "agy",
                    "cloud_only": False,
                    "lineage": "canonical",
                },
            ),
            ToolDescriptor(
                id="nano-banana-pro:image-to-image",
                name="Nano Banana Pro Reference (AGY CLI)",
                task_type="image-to-image",
                task_types=["image-to-image"],
                parameter_schema={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "x-label": "Prompt", "minLength": 1},
                        "input_images": {
                            "type": "array",
                            "items": {"type": "string", "format": "file-path"},
                            "minItems": 1,
                            "maxItems": 1,
                            "x-control": "image_picker",
                        },
                        "reference_images": {
                            "type": "array",
                            "items": {"type": "string", "format": "file-path"},
                            "x-control": "reference_strip",
                        },
                        "seed": {"type": "integer", "minimum": 0},
                    },
                    "required": ["prompt", "input_images"],
                },
                output_schema={
                    "type": "object",
                    "properties": {"image": {"type": "string", "format": "file-path"}},
                },
                model_vendor="google",
                model="Nano Banana Pro",
                subtitle="AGY CLI · Reference fidelity",
                description="Generate image variations adhering strictly to reference inputs via AGY CLI.",
                metadata={
                    "provider": "Antigravity",
                    "model": "Nano Banana Pro",
                    "cli": "agy",
                    "cloud_only": False,
                    "lineage": "canonical",
                },
            ),
        ]

    async def execute(
        self,
        tool_id: str,
        parameters: Dict[str, Any],
        output_path: Optional[str] = None,
        progress_callback=None,
        request_id=None,
    ) -> AsyncIterator[Any]:
        started = time.perf_counter()
        if progress_callback:
            progress_callback(
                ExecutionProgress(
                    progress=0.1,
                    stage="AGY CLI",
                    message="Préparation de l'environnement Nano Banana Pro...",
                )
            )

        # 1. Parse parameters
        source_param = (parameters.get("input_images") or [None])[0] or parameters.get("image")
        mask_param = parameters.get("mask")
        prompt = str(parameters.get("prompt") or "").strip()
        reference_images = parameters.get("reference_images") or []

        if not source_param or not Path(str(source_param)).is_file():
            yield ExecutionResult(
                success=False,
                error="Antigravity Nano Banana Pro exige une image source valide.",
            )
            return

        source_path = Path(str(source_param))

        # Determine dimensions
        try:
            with Image.open(source_path) as img:
                width, height = img.size
        except Exception as exc:
            yield ExecutionResult(success=False, error=f"Impossible de lire l'image source: {exc}")
            return

        # 2. Setup staging workspace
        profile_id = get_current_profile()
        run_id = f"agy_edit_{uuid.uuid4().hex[:10]}"
        staging_dir = Path(app_dirs.get_managed_staging_dir(profile_id, "generated")) / "editor_agy_runs" / run_id
        staging_dir.mkdir(parents=True, exist_ok=True)

        staged_source = staging_dir / f"source_{source_path.name}"
        shutil.copy2(source_path, staged_source)

        ordered_refs: List[tuple[int, Path]] = []
        ordered_refs.append((1, staged_source))

        is_inpaint = bool(mask_param and Path(str(mask_param)).is_file())

        if is_inpaint:
            mask_path = Path(str(mask_param))
            staged_mask = staging_dir / f"mask_{mask_path.name}"
            shutil.copy2(mask_path, staged_mask)
            ordered_refs.append((2, staged_mask))

            # If user provided a basic prompt or removal prompt without EDIT MAP structure, build it
            if "EDIT MAP" not in prompt.upper():
                instruction = prompt or "seamlessly inpaint the masked area matching surrounding scene"
                prompt = (
                    "EDIT MAP\n\n"
                    "ZONE 1 — MASKED REGION\n"
                    "Target: masked area @image1\n"
                    "Operation: replace\n"
                    f"Instruction: {instruction}\n\n"
                    "GLOBAL LOCK:\n"
                    "Everything not selected by a zone remains unchanged."
                )

        # Additional reference images
        for idx, ref_img_path in enumerate(reference_images, start=len(ordered_refs) + 1):
            if ref_img_path and Path(str(ref_img_path)).is_file():
                staged_ref = staging_dir / f"ref_{idx}_{Path(ref_img_path).name}"
                shutil.copy2(ref_img_path, staged_ref)
                ordered_refs.append((idx, staged_ref))

        output_target = staging_dir / f"output_{run_id}_antigravity.png"

        # 3. Build Prompt with System Directives
        try:
            from agent.v2.tools.antigravity_image import (
                build_antigravity_prompt,
                normalize_generated_still,
                _wait_for_agy_output,
            )
            agy_prompt = build_antigravity_prompt(
                prompt=prompt,
                reference_files=ordered_refs,
                output_path=output_target,
                expected_dimensions=[width, height],
            )
            executable = _agy_executable()
        except Exception as exc:
            yield ExecutionResult(
                success=False,
                error=f"Erreur lors de la préparation du prompt Antigravity: {exc}",
            )
            return

        if progress_callback:
            progress_callback(
                ExecutionProgress(
                    progress=0.3,
                    stage="AGY CLI",
                    message="Exécution Nano Banana Pro via Antigravity CLI...",
                )
            )

        # 4. Launch AGY subprocess
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                executable,
                "--dangerously-skip-permissions",
                "--disable-slash-commands",
                "--add-dir",
                str(staging_dir),
                "--print-timeout",
                "5m",
                "--print",
                agy_prompt,
                cwd=str(staging_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr, output_ready = await _wait_for_agy_output(
                process,
                output_target,
                [width, height],
                timeout_seconds=300,
            )
        except asyncio.TimeoutError:
            if process and process.returncode is None:
                process.kill()
            yield ExecutionResult(
                success=False,
                error="Antigravity CLI génération dépassé le délai imparti (300s).",
            )
            return
        except Exception as exc:
            if process and process.returncode is None:
                process.kill()
            yield ExecutionResult(success=False, error=f"Erreur d'exécution AGY CLI: {exc}")
            return

        cli_output = "\n".join(
            part.decode(errors="replace") for part in (stdout or b"", stderr or b"") if part
        ).strip()

        if not output_target.is_file():
            yield ExecutionResult(
                success=False,
                error=f"Antigravity CLI n'a pas produit de fichier de sortie: {cli_output[-1000:] or 'Pas de diagnostic CLI'}",
            )
            return

        # 5. Normalize & read output
        normalize_generated_still(output_target, [width, height])
        output_bytes = output_target.read_bytes()

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(output_bytes)

        elapsed = time.perf_counter() - started
        log.info(
            "Antigravity Nano Banana Pro execution complete",
            elapsed_seconds=elapsed,
            output_bytes=len(output_bytes),
        )

        yield ExecutionResult(
            success=True,
            output_data=output_bytes,
            generation_time=elapsed,
            metadata={
                "provider": "Antigravity",
                "model": "Nano Banana Pro",
                "cli": "agy",
                "width": width,
                "height": height,
                "is_inpaint": is_inpaint,
            },
        )
