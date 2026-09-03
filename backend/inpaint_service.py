"""Service for multi-zone inpainting and reference-based still image generation via AGY CLI."""

from __future__ import annotations

import base64
from datetime import datetime
import io
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from agent.v2.tools.antigravity_image import antigravity_image
from agent.v2.tools.library import save_workspace_file
from agent.v2.workspace import get_project_workspace
import app_dirs
from core.profile_context import get_current_profile
from database import MediaItem


_RESULT_MEDIA = re.compile(r"<result\s+media_id=(\d+)")


class InpaintServiceError(ValueError):
    """Raised when inpainting or reference generation parameters or execution fail."""


def compile_inpaint_prompt(
    zones: List[Dict[str, Any]],
    prompt_override: Optional[str] = None,
    global_lock: str = "Everything not selected by a zone remains unchanged.",
) -> str:
    """Compile structured EDIT MAP prompt from zone definitions."""
    if prompt_override and prompt_override.strip():
        return prompt_override.strip()

    lines = ["EDIT MAP\n"]
    for idx, zone in enumerate(zones, start=1):
        color_label = str(zone.get("color_name") or f"COLOR {idx}").upper()
        target = str(zone.get("target") or "@image1").strip()
        operation = str(zone.get("operation") or "modify").strip().lower()
        instruction = str(zone.get("instruction") or "").strip()

        lines.append(f"ZONE {idx} — {color_label}")
        lines.append(f"Target: {target}")
        lines.append(f"Operation: {operation}")
        if instruction:
            lines.append(f"Instruction: {instruction}")
        lines.append("")

    lines.append("GLOBAL LOCK:")
    lines.append(global_lock.strip())
    return "\n".join(lines).strip()


async def save_mask_image(
    session: AsyncSession,
    mask_data_or_base64: str,
    *,
    project_id: Optional[int] = None,
    source_media_id: Optional[int] = None,
) -> MediaItem:
    """Save an inpainting mask / annotation image to the library and return its MediaItem."""
    if not mask_data_or_base64:
        raise InpaintServiceError("Mask image data is required.")

    # Clean base64 header if present
    raw_b64 = mask_data_or_base64
    if "base64," in raw_b64:
        raw_b64 = raw_b64.split("base64,")[1]

    try:
        image_bytes = base64.b64decode(raw_b64)
        with Image.open(io.BytesIO(image_bytes)) as pil_img:
            pil_img.verify()
        with Image.open(io.BytesIO(image_bytes)) as pil_img:
            width, height = pil_img.size
    except Exception as exc:
        raise InpaintServiceError(f"Invalid mask image data: {exc}") from exc

    profile_id = get_current_profile()
    staging_dir = Path(app_dirs.get_managed_staging_dir(profile_id, "generated")) / "inpainting_masks"
    staging_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    mask_filename = f"inpaint_mask_{source_media_id or 'src'}_{timestamp}.png"
    mask_path = staging_dir / mask_filename

    with open(mask_path, "wb") as f:
        f.write(image_bytes)

    provenance = {
        "task_type": "inpaint-mask",
        "tool_id": "stimma:inpaint_mask",
        "source_media_id": source_media_id,
        "width": width,
        "height": height,
    }

    workspace = staging_dir
    saved = json.loads(
        await save_workspace_file(
            session=session,
            path=str(mask_path),
            workspace_dir=workspace,
            save_tags=None,
            provenance=provenance,
            project_id=project_id,
            metadata_source="inpaint_studio_mask",
            materialize_asset=False,
        )
    )

    media_id = saved.get("media_id")
    if not media_id:
        raise InpaintServiceError("Failed to register inpainting mask media item.")

    media_item = await session.get(MediaItem, int(media_id))
    if media_item is None:
        raise InpaintServiceError(f"MediaItem {media_id} could not be retrieved.")
    return media_item


def _parse_media_id(result_str: str) -> int:
    if result_str.startswith("Error:"):
        raise InpaintServiceError(result_str.removeprefix("Error:").strip())
    match = _RESULT_MEDIA.search(result_str)
    if not match:
        raise InpaintServiceError(f"Antigravity returned no Media id: {result_str[-500:]}")
    return int(match.group(1))


async def execute_inpaint(
    session: AsyncSession,
    *,
    source_media_id: int,
    mask_media_id: int,
    prompt: str,
    reference_media_ids: Optional[List[int]] = None,
    project_id: Optional[int] = None,
    output_role: str = "final",
    expected_dimensions: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Execute multi-zone inpainting through AGY CLI."""
    source_media = await session.get(MediaItem, source_media_id)
    if source_media is None or source_media.deleted_at is not None:
        raise InpaintServiceError(f"Source media {source_media_id} not found.")

    mask_media = await session.get(MediaItem, mask_media_id)
    if mask_media is None or mask_media.deleted_at is not None:
        raise InpaintServiceError(f"Mask media {mask_media_id} not found.")

    # Canonical order: Picture 1 = clean source, Picture 2 = mask image, Picture 3+ = additional references
    ordered_references = [source_media_id, mask_media_id]
    for ref_id in reference_media_ids or []:
        if ref_id not in ordered_references:
            ordered_references.append(ref_id)

    dims = expected_dimensions or ([source_media.width, source_media.height] if source_media.width and source_media.height else None)

    workspace_dir = get_project_workspace(project_id) if project_id else Path(app_dirs.get_managed_staging_dir(get_current_profile(), "generated")) / "inpaint_runs"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    output_name = f"inpaint_{source_media_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_antigravity.png"

    raw_result = await antigravity_image(
        prompt=prompt,
        reference_media_ids=ordered_references,
        output_name=output_name,
        output_role=output_role,
        expected_dimensions=dims,
        workspace_dir=workspace_dir,
        session=session,
        project_id=project_id,
    )

    result_media_id = _parse_media_id(raw_result)
    result_media = await session.get(MediaItem, result_media_id)

    return {
        "result_media_id": result_media_id,
        "result_media": {
            "id": result_media_id,
            "filename": result_media.filename if result_media else output_name,
            "width": result_media.width if result_media else dims[0] if dims else None,
            "height": result_media.height if result_media else dims[1] if dims else None,
        } if result_media else None,
        "prompt": prompt,
        "source_media_id": source_media_id,
        "mask_media_id": mask_media_id,
        "reference_media_ids": ordered_references,
        "status": "success",
    }


async def execute_reference_generation(
    session: AsyncSession,
    *,
    prompt: str,
    reference_media_ids: Optional[List[int]] = None,
    negative_prompt: Optional[str] = None,
    dimensions: Optional[List[int]] = None,
    project_id: Optional[int] = None,
    output_role: str = "final",
) -> Dict[str, Any]:
    """Execute reference-based image generation through AGY CLI."""
    refs = list(reference_media_ids or [])
    for ref_id in refs:
        item = await session.get(MediaItem, ref_id)
        if item is None or item.deleted_at is not None:
            raise InpaintServiceError(f"Reference media {ref_id} not found.")

    final_prompt_parts = [prompt.strip()]
    if negative_prompt and negative_prompt.strip():
        final_prompt_parts.append(f"\nEXCLUSIONS / NEGATIVES:\n{negative_prompt.strip()}")
    final_prompt = "\n".join(final_prompt_parts)

    workspace_dir = get_project_workspace(project_id) if project_id else Path(app_dirs.get_managed_staging_dir(get_current_profile(), "generated")) / "reference_runs"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    output_name = f"ref_gen_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_antigravity.png"

    raw_result = await antigravity_image(
        prompt=final_prompt,
        reference_media_ids=refs,
        output_name=output_name,
        output_role=output_role,
        expected_dimensions=dimensions,
        workspace_dir=workspace_dir,
        session=session,
        project_id=project_id,
    )

    result_media_id = _parse_media_id(raw_result)
    result_media = await session.get(MediaItem, result_media_id)

    return {
        "result_media_id": result_media_id,
        "result_media": {
            "id": result_media_id,
            "filename": result_media.filename if result_media else output_name,
            "width": result_media.width if result_media else dimensions[0] if dimensions else None,
            "height": result_media.height if result_media else dimensions[1] if dimensions else None,
        } if result_media else None,
        "prompt": final_prompt,
        "reference_media_ids": refs,
        "dimensions": dimensions,
        "status": "success",
    }
