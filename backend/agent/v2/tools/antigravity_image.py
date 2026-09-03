"""Generate or edit one still image through the real Antigravity CLI.

Stimma prepares the prompt and canonical references; Antigravity (agy) owns
the Nano Banana generation/edit operation.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
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


def normalize_generated_still(
    path: Path,
    expected_dimensions: list[int] | tuple[int, int] | None,
) -> list[str]:
    """Center-crop AGY's near-16:9 canvas and normalize it to the project size."""
    if not expected_dimensions:
        return validate_generated_still(path)
    target_width, target_height = map(int, expected_dimensions)
    try:
        with Image.open(path) as source:
            source.load()
            if source.size == (target_width, target_height):
                return []
            width, height = source.size
            target_ratio = target_width / target_height
            actual_ratio = width / height
            if actual_ratio > target_ratio:
                crop_width = max(1, round(height * target_ratio))
                left = max(0, (width - crop_width) // 2)
                box = (left, 0, min(width, left + crop_width), height)
            else:
                crop_height = max(1, round(width / target_ratio))
                top = max(0, (height - crop_height) // 2)
                box = (0, top, width, min(height, top + crop_height))
            normalized = source.crop(box)
            if normalized.size != (target_width, target_height):
                normalized = normalized.resize(
                    (target_width, target_height),
                    Image.Resampling.LANCZOS,
                )
            normalized.save(path, format=source.format or "PNG")
    except (OSError, UnidentifiedImageError, ValueError, SyntaxError) as exc:
        return [f"generated still could not be normalized: {exc}"]
    return validate_generated_still(path, expected_dimensions)


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


INPAINTING_SYSTEM_PROMPT = """\
You are a SOURCE-LOCKED MULTI-ZONE IMAGE INPAINTING EDITOR.

Your task is to edit an existing source image using user-defined colored regions as semantic edit masks.
The source image is the canonical visual master.
The colored mask / annotation image defines WHERE changes are allowed.
The user's written instructions define WHAT must change inside each colored region.

==================================================
1. DEFAULT OPERATING MODE
==================================================
Whenever a source image and a colored annotation/mask image are provided, operate in MULTI-ZONE INPAINTING MODE.
Do NOT recreate the entire image.
Do NOT treat the source image as inspiration.
Do NOT redesign the scene.
Do NOT generate an alternative composition.
Use the original source image as the visual foundation of the output.
The goal is:
SOURCE IMAGE + COLOR-CODED EDIT REGIONS + ZONE-SPECIFIC INSTRUCTIONS = LOCALLY EDITED SOURCE IMAGE

==================================================
2. SOURCE IMAGE PRIORITY
==================================================
The clean source image is the authoritative master for:
- composition, framing, camera position, camera angle, perspective, geometry, architecture
- object placement, object scale, lighting, shadows, materials, textures, color relationships
- depth, atmospheric conditions, text, logos, identity, continuity
Preserve these properties unless a specific masked edit explicitly requires one of them to change.

==================================================
3. MASK IMAGE INTERPRETATION
==================================================
The annotation image is NOT the desired final appearance.
Colored strokes, outlines, fills, circles, arrows or highlights are editing instructions only.
They must NEVER appear in the final image.
Remove all annotation colors from the final output.
Interpret each distinct annotation color as an independent semantic edit zone.
(e.g., YELLOW MASK → Zone Yellow, RED MASK → Zone Red, BLUE MASK → Zone Blue, GREEN MASK → Zone Green).
The exact meaning of each color is provided by the user's prompt. Do not assign your own semantic meaning to colors.

==================================================
4. COLOR-TO-ZONE MAPPING & MULTI-ZONE ISOLATION
==================================================
Each color represents a separate editing region. Only apply the instruction associated with that color.
Execute each instruction only inside its corresponding region. Do not transfer instructions between colors.
Treat every colored zone independently. Editing Zone A must not cause visual changes in Zone B unless physically necessary.

==================================================
5. UNDEFINED COLORS & MASK BOUNDARY RULE
==================================================
If a colored region exists without instructions, preserve the corresponding source content. Never guess.
Treat colored regions as semantic inpainting boundaries. Outside all authorized mask regions: PRESERVE THE SOURCE IMAGE.
Do not make unrelated changes outside the mask.

==================================================
6. OUTLINE, BRUSH & SCRIBBLE MASKS
==================================================
If a colored OUTLINE is drawn around an object/region, interpret the enclosed interior as the editable target.
The outline itself is not part of the final image.
For rough strokes or scribbles, infer the target object semantically and apply minimal coherent edits.

==================================================
7. MINIMUM CHANGE PRINCIPLE & SOURCE-LOCKED AREA
==================================================
For every zone: make the minimum visual modification required. Preservation has priority over creative reinterpretation.
Everything outside edit zones is SOURCE-LOCKED.
Preserve exact framing, perspective, architecture, furniture, wear/imperfections, lighting direction, shadows, reflections, noise/grain, text and signage.

==================================================
8. REPLACEMENT, REMOVAL, ADDITION & STRUCTURAL EDITS
==================================================
- REPLACE: Replace only the selected object; replacement inherits position, scale, perspective, lighting, shadows, depth.
- REMOVE: Remove only the selected object; reconstruct revealed background from surrounding visual evidence.
- ADD: Place new object inside target region with matching perspective, optics, lighting, reflections, color grading.
- STRUCTURAL: Modify only selected architectural elements, preserving neighboring geometry and vanishing points.

==================================================
9. TEXT & CHARACTER PROTECTION
==================================================
Existing text and people outside active masks are strictly identity-locked.
Do not change face, body, clothing, hair, pose, expression, or text unless explicitly masked and instructed.

==================================================
10. NO COLOR CONTAMINATION & OUTPUT
==================================================
Annotation colors are control metadata, never visual content. Never retain colored lines or glow.
Blend mask edges seamlessly with matching sharpness, lighting, grain.
Return ONE final edited image looking like the original photograph after localized, controlled inpainting.
SOURCE OUTSIDE MASK = PRESERVE. INSIDE MASK = APPLY ONLY THE ASSOCIATED EDIT. EDIT, DO NOT RECREATE.\
"""

REFERENCE_GENERATION_SYSTEM_PROMPT = """\
When uncertain whether an element should change:
PRESERVE IT.

When uncertain whether the user wants a recreation or an edit:
EDIT THE SOURCE IMAGE.

When an instruction can be fulfilled either by changing the entire image or by making a localized modification:
choose the localized modification.

==================================================
GLOBAL TRANSFORMATIONS
==================================================
If the user explicitly requests a global transformation such as:
- change daytime to nighttime
- change the season
- change the entire artistic style
- age the entire environment
- make the whole scene abandoned
- change the location substantially
perform that requested global transformation while preserving all unrelated structural properties that do not need to change.
A broad requested transformation does not automatically authorize a new camera angle, new composition or unrelated scene redesign.

==================================================
USER OVERRIDE
==================================================
The user may explicitly override preservation constraints.
Explicit instructions always take priority (e.g. "Move the camera", "Redesign the room", "Replace all furniture", "Create a different composition").
Without such explicit authorization, preserve those properties.

==================================================
FINAL OPERATIONAL RULE
==================================================
IF AN IMAGE EXISTS:
DO NOT ASK: "What new image should I create from this?"
ASK INTERNALLY: "What is the smallest set of visual changes necessary to transform this exact source image into what the user requested?"
Perform those changes while preserving the remainder of the source.

SOURCE FIDELITY > CREATIVE REINTERPRETATION.
EDIT > RECREATE.
PRESERVE > REDESIGN.
RETURN THE EDITED IMAGE.\
"""


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

    # Determine relevant operational system prompt to inject
    is_inpaint = "EDIT MAP" in prompt.upper() or "ZONE " in prompt.upper()
    if is_inpaint:
        operating_system_prompt = f"OPERATING SYSTEM DIRECTIVE (INPAINTING):\n{INPAINTING_SYSTEM_PROMPT}\n\n"
    elif reference_files:
        operating_system_prompt = f"OPERATING SYSTEM DIRECTIVE (REFERENCE FIDELITY):\n{REFERENCE_GENERATION_SYSTEM_PROMPT}\n\n"
    else:
        operating_system_prompt = ""

    return (
        "You are executing one image generation/edit operation using Antigravity's native generate_image tool.\n"
        "Do NOT use any external CLI, network command, or third-party tool.\n"
        "Do NOT use third-party skills. Call Antigravity's built-in generate_image tool directly.\n"
        f"{operating_system_prompt}"
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


async def _wait_for_agy_output(
    process: Any,
    output_path: Path,
    expected_dimensions: list[int] | tuple[int, int] | None,
    *,
    timeout_seconds: float = 600,
) -> tuple[bytes, bytes, bool]:
    """Drain AGY while accepting a complete file even if print mode stays open."""
    communicate_task = asyncio.create_task(process.communicate())
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    last_signature: tuple[int, int] | None = None
    stable_checks = 0
    output_ready = False

    while not communicate_task.done():
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            communicate_task.cancel()
            if process.returncode is None:
                process.kill()
            raise asyncio.TimeoutError
        await asyncio.wait({communicate_task}, timeout=min(0.5, remaining))
        if communicate_task.done():
            break
        if not output_path.is_file():
            continue
        signature = (output_path.stat().st_size, output_path.stat().st_mtime_ns)
        if signature == last_signature and not validate_generated_still(output_path):
            stable_checks += 1
        else:
            stable_checks = 0
        last_signature = signature
        if stable_checks < 1:
            continue
        normalization_errors = normalize_generated_still(
            output_path,
            expected_dimensions,
        )
        if normalization_errors:
            continue
        output_ready = True
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(asyncio.shield(communicate_task), timeout=5)
        except asyncio.TimeoutError:
            if process.returncode is None:
                process.kill()
            communicate_task.cancel()
            with suppress(asyncio.CancelledError):
                await communicate_task
            return b"", b"", output_ready
        break

    stdout, stderr = await communicate_task
    return stdout or b"", stderr or b"", output_ready


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
        stdout, stderr, output_ready = await _wait_for_agy_output(
            process,
            output_path,
            expected_dimensions,
        )
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
    if process.returncode != 0 and not output_ready:
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
