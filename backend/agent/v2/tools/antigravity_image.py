"""Generate or edit one still image through the real Antigravity CLI.

Stimma prepares the prompt and canonical references; Antigravity (agy) owns
the Nano Banana generation/edit operation.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select

from ..tools_registry import ToolParameter, tool
from .library import save_workspace_file
from agy_cli import _agy_executable
from database import MediaItem
from shot_continuity_service import validate_generation_request


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff"}
_SAFE_OUTPUT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def validate_generated_still(
    path: Path,
    expected_dimensions: list[int] | tuple[int, int] | None = None,
) -> list[str]:
    """Validate that AGY produced a readable still with the required canvas."""
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            actual_dimensions = list(image.size)
    except (OSError, UnidentifiedImageError, ValueError, SyntaxError) as exc:
        return [f"generated still is not readable: {exc}"]

    if expected_dimensions and actual_dimensions != [int(expected_dimensions[0]), int(expected_dimensions[1])]:
        return [
            "generated still dimensions mismatch: "
            f"expected {int(expected_dimensions[0])}x{int(expected_dimensions[1])}, "
            f"got {actual_dimensions[0]}x{actual_dimensions[1]}"
        ]
    return []


def _normalize_media_ids(values: Iterable[Any] | None) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values or []:
        try:
            media_id = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid reference media id: {value!r}") from exc
        if media_id <= 0:
            raise ValueError(f"Invalid reference media id: {value!r}")
        if media_id not in seen:
            seen.add(media_id)
            result.append(media_id)
    return result


def _normalize_output_name(value: str | None) -> str:
    name = (value or "antigravity_image.png").strip()
    if not _SAFE_OUTPUT_NAME.fullmatch(name):
        raise ValueError(
            "output_name must be a simple filename inside the chat workspace "
            "(letters, numbers, dots, dashes and underscores only)"
        )
    if Path(name).suffix.casefold() not in _IMAGE_SUFFIXES:
        name = f"{name}.png"
    return name


def build_antigravity_prompt(
    prompt: str,
    reference_files: list[tuple[int, Path]],
    output_path: Path,
    expected_dimensions: list[int] | tuple[int, int] | None = None,
) -> str:
    """Build the explicit prompt sent to AGY, including ordered references."""
    references = "\n".join(
        f"<Picture {index}> (media_id={media_id}): {path}"
        for index, (media_id, path) in enumerate(reference_files, start=1)
    )
    image_paths_list = [str(path) for _, path in reference_files]
    aspect_ratio = "16:9"
    if expected_dimensions and len(expected_dimensions) == 2:
        w, h = int(expected_dimensions[0]), int(expected_dimensions[1])
        if w == h:
            aspect_ratio = "1:1"
        elif w > h:
            aspect_ratio = "16:9"
        else:
            aspect_ratio = "9:16"

    reference_block = (
        "REFERENCE IMAGES — use these exact files in this exact order:\n"
        f"{references}\n\n"
        if reference_files
        else "REFERENCE IMAGES — none. Generate from the written prompt only.\n\n"
    )
    size_instruction = ""
    if expected_dimensions and len(expected_dimensions) == 2:
        size_instruction = (
            f"The final canvas must be exactly {int(expected_dimensions[0])}x"
            f"{int(expected_dimensions[1])} pixels.\n"
        )
    return (
        "You are executing one image generation/edit operation using Antigravity's native generate_image tool.\n"
        "Do NOT use any external CLI, network command, or third-party tool.\n"
        "Do NOT use third-party skills. Call Antigravity's built-in generate_image tool directly.\n"
        f"Call generate_image with Prompt={prompt.strip()!r}, ImagePaths={json.dumps(image_paths_list)}, AspectRatio='{aspect_ratio}', ImageName='{output_path.stem}'.\n"
        "If reference images are listed below, inspect them and preserve their identity; "
        "do not invent substitute references and do not create a collage or viewsheet "
        "unless the task prompt explicitly asks for one.\n"
        f"{reference_block}"
        f"TASK PROMPT:\n{prompt.strip()}\n\n"
        f"{size_instruction}"
        "OUTPUT CONTRACT:\n"
        f"Once generate_image produces the image file, copy/move it to: {output_path}\n"
        "Do not stop after describing the image. Do not save a second candidate."
    )


async def _materialize_references(
    session: Any,
    media_ids: list[int],
    workspace_dir: Path,
) -> list[tuple[int, Path]]:
    if not media_ids:
        return []
    result = await session.execute(select(MediaItem).where(MediaItem.id.in_(media_ids)))
    rows = {int(row.id): row for row in result.scalars().all()}
    missing = [media_id for media_id in media_ids if media_id not in rows]
    if missing:
        raise ValueError(f"Reference media not found: {missing}")

    files: list[tuple[int, Path]] = []
    for index, media_id in enumerate(media_ids, start=1):
        source = Path(rows[media_id].file_path or "")
        if not source.is_file():
            raise ValueError(f"Reference media {media_id} has no readable source file")
        suffix = source.suffix.casefold() or ".png"
        dest = workspace_dir / f"_antigravity_ref_{index:02d}_{media_id}{suffix}"
        shutil.copy2(source, dest)
        files.append((media_id, dest))
    return files


def _shot_manifest_ids(shot_contract: dict[str, Any] | None) -> list[int]:
    if not isinstance(shot_contract, dict):
        return []
    return [
        int(item["media_id"])
        for item in shot_contract.get("reference_manifest") or []
        if isinstance(item, dict) and item.get("media_id")
    ]


@tool(
    name="antigravity_image",
    description=(
        "Generate or edit exactly one still image through the real Antigravity CLI (agy) "
        "using native generate_image. Stimma sends the written prompt and ordered reference "
        "media files to AGY, ingests the result, and records lineage. Use this for new "
        "assets, viewsheets, location edits, and composed opening keyframes; do not use "
        "the local .stimma image-to-image catalogue for these operations."
    ),
    parameters=[
        ToolParameter(name="prompt", type="string", description="The complete image generation or edit prompt", required=True),
        ToolParameter(
            name="reference_media_ids",
            type="array",
            description="Ordered canonical media IDs to send as <Picture 1>, <Picture 2>, ...; omit for text-only generation",
            required=False,
            items={"type": "integer"},
        ),
        ToolParameter(
            name="output_name",
            type="string",
            description="Simple output filename, preferably ending in _antigravity.png",
            required=False,
        ),
        ToolParameter(
            name="output_role",
            type="string",
            description="Use intermediate for a candidate keyframe or final for a user-facing approved image",
            required=False,
            enum=["intermediate", "final"],
        ),
        ToolParameter(
            name="expected_dimensions",
            type="array",
            description="Optional exact [width, height] canvas for non-shot reference generation",
            required=False,
            items={"type": "integer"},
        ),
    ],
    scope="agent",
)
async def antigravity_image(
    prompt: str,
    reference_media_ids: list[int] | None = None,
    output_name: str | None = None,
    output_role: str = "final",
    expected_dimensions: list[int] | None = None,
    **kwargs: Any,
) -> str:
    workspace_dir = kwargs.get("workspace_dir")
    session = kwargs.get("session")
    if not workspace_dir or not session:
        return "Error: no workspace or database session available"
    if not isinstance(prompt, str) or not prompt.strip():
        return "Error: prompt is required"
    if output_role not in {"intermediate", "final"}:
        return "Error: output_role must be 'intermediate' or 'final'"

    workspace = Path(workspace_dir)
    try:
        media_ids = _normalize_media_ids(reference_media_ids)
        name = _normalize_output_name(output_name)
    except ValueError as exc:
        return f"Error preparing Antigravity image generation: {exc}"

    shot_contract = kwargs.get("_shot_contract")
    manifest_ids = _shot_manifest_ids(shot_contract)
    if isinstance(shot_contract, dict) and shot_contract.get("workflow") == "compose_opening_keyframe_then_i2v":
        if media_ids != manifest_ids:
            return (
                "Error: the opening keyframe must use the exact World State reference manifest "
                f"in order: {manifest_ids}; received {media_ids}. No image was generated."
            )
        if output_role != "intermediate":
            return "Error: the composed opening keyframe must use output_role='intermediate' until QA approval"
        errors = validate_generation_request(
            shot_contract,
            task_type="image-to-image",
            final_params={"prompt": prompt},
            input_media_ids=media_ids,
            session_media_ids=kwargs.get("session_media_ids") or [],
        )
        if errors:
            return "Error: shot image preflight blocked this job:\n- " + "\n- ".join(errors)

    try:
        reference_files = await _materialize_references(session, media_ids, workspace)
        output_path = workspace / name
        # Never accept a stale file left by a timed-out or interrupted AGY run.
        # The CLI is required to produce a fresh artifact for this invocation.
        output_path.unlink(missing_ok=True)
        contract_dimensions = (
            shot_contract.get("expected_dimensions")
            if isinstance(shot_contract, dict)
            else None
        )
        requested_dimensions = expected_dimensions or contract_dimensions
        if requested_dimensions is not None and (
            not isinstance(requested_dimensions, (list, tuple))
            or len(requested_dimensions) != 2
            or any(int(value) <= 0 for value in requested_dimensions)
        ):
            raise ValueError("expected_dimensions must be [positive width, positive height]")
        expected_dimensions = (
            [int(requested_dimensions[0]), int(requested_dimensions[1])]
            if requested_dimensions is not None
            else None
        )
        agy_prompt = build_antigravity_prompt(
            prompt,
            reference_files,
            output_path,
            expected_dimensions=expected_dimensions,
        )
        executable = _agy_executable()
    except (OSError, ValueError, RuntimeError) as exc:
        return f"Error preparing Antigravity image generation: {exc}"

    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            executable,
            "--dangerously-skip-permissions",
            "--disable-slash-commands",
            "--add-dir",
            str(workspace),
            "--print-timeout",
            "5m",
            "--print",
            agy_prompt,
            cwd=str(workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=600)
    except asyncio.TimeoutError:
        if process and process.returncode is None:
            process.kill()
        return "Error: Antigravity image generation timed out after 600 seconds"
    except asyncio.CancelledError:
        if process and process.returncode is None:
            process.kill()
        raise
    except OSError as exc:
        return f"Error launching Antigravity CLI: {exc}"

    cli_output = "\n".join(
        part.decode(errors="replace") for part in (stdout or b"", stderr or b"") if part
    ).strip()
    if process.returncode != 0:
        return f"Error: Antigravity CLI exited with status {process.returncode}: {cli_output[-2000:] or 'no CLI diagnostic'}"
    if not output_path.is_file():
        return f"Error: Antigravity completed but did not create {output_path.name}: {cli_output[-2000:] or 'no CLI diagnostic'}"
    output_errors = validate_generated_still(output_path, expected_dimensions)
    if output_errors:
        return "Error: Antigravity output preflight blocked the result:\n- " + "\n- ".join(output_errors)

    provenance = {
        "task_type": "image-to-image" if media_ids else "text-to-image",
        "tool_id": "antigravity:generate_image",
        "parameters": {
            "prompt": prompt,
            "reference_media_ids": media_ids,
            "model": "Antigravity Image",
            "output_role": output_role,
        },
        "source_media_ids": media_ids,
    }
    try:
        saved = json.loads(
            await save_workspace_file(
                session=session,
                path=str(output_path),
                workspace_dir=workspace,
                save_tags=None,
                provenance=provenance,
                project_id=kwargs.get("project_id"),
                metadata_source="agent_v2_antigravity",
                materialize_asset=output_role == "final",
            )
        )
    except Exception as exc:
        return f"Error saving Antigravity output to the library: {exc}"

    media_id = saved.get("media_id")
    session_media_ids = kwargs.get("session_media_ids")
    if media_id and isinstance(session_media_ids, list) and int(media_id) not in session_media_ids:
        session_media_ids.append(int(media_id))
    if (
        media_id
        and isinstance(shot_contract, dict)
        and shot_contract.get("workflow") == "compose_opening_keyframe_then_i2v"
    ):
        shot_contract["opening_keyframe_media_id"] = int(media_id)
        shot_contract["opening_keyframe_source_media_ids"] = list(media_ids)
        shot_contract["opening_keyframe_backend"] = "antigravity:generate_image"
        shot_contract["opening_keyframe_output_role"] = output_role
    asset_note = " and registered as an Asset" if saved.get("asset_id") else ""
    return (
        f"<result media_id={media_id} workspace_file=\"{saved.get('filename', name)}\" /> "
        f"Generated by Antigravity Image (agy){asset_note}. "
        f"References used in order: {media_ids or 'none'}. "
        + (
            f"Opening keyframe bound to shot contract: {media_id}. "
            if isinstance(shot_contract, dict)
            and shot_contract.get("workflow") == "compose_opening_keyframe_then_i2v"
            else ""
        )
        + "Call show with the requested role."
    )
