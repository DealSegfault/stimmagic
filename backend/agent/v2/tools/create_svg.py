"""Create an SVG document — validates, renders to verify, saves it to the library."""

import json
import uuid
from datetime import datetime
from pathlib import Path

import app_dirs

from ..tools_registry import tool, ToolParameter

from config_version import get_config_version_manager
from core.logging import get_logger
from generation_metadata import build_generation_metadata
from utils.svg_doc import SvgParseError, prepare_text

log = get_logger(__name__)


# A document that parses but draws nothing is the characteristic SVG failure —
# a bad viewBox, a shape outside the visible area, a fill matching the ground.
# Rendering and checking for any marked pixel catches it before it ships.
_BLANK_CHECK_SIZE = 128


@tool(
    name="create_svg",
    description=(
        "Create an SVG document from markup and save it to the library. For icons, logos, "
        "wordmarks, badges, and vector illustration. Returns the media_id of the saved "
        "document. Preferred workflow: write the SVG to a workspace file with write_file, "
        "then pass the file path here; iterate with edit_file and re-run. The document must "
        "be self-contained — no <script>, no external images, fonts, or stylesheets. Embed "
        "any raster as a data: URI, and convert text to paths so it renders identically "
        "outside this app. Call view_image on the result to see what you actually made. To "
        "display it as the next version of an existing artifact, call show with "
        "revises=<asset_id> afterward — this tool only saves."
    ),
    parameters=[
        ToolParameter(
            name="file",
            type="string",
            description="Path to an .svg file in the workspace (e.g. 'logo.svg'). Preferred over inline svg — write once, iterate with edit_file, re-save.",
            required=False,
        ),
        ToolParameter(
            name="svg",
            type="string",
            description="Inline SVG markup, starting with <svg>. Use for simple one-shot documents.",
            required=False,
        ),
        ToolParameter(
            name="title",
            type="string",
            description="Short name for the document, used for the filename (e.g. 'acme-logo').",
            required=False,
        ),
    ],
)
async def create_svg(
    file: str | None = None,
    svg: str | None = None,
    title: str | None = None,
    **kwargs,
) -> str:
    workspace_dir = kwargs.get("workspace_dir")
    if not workspace_dir:
        return "Error: No workspace directory available"

    if file:
        from ._workspace_files import resolve_workspace_path
        resolved, err = resolve_workspace_path(workspace_dir, file)
        if err:
            return err
        if not resolved.exists():
            return f"Error: File not found: {file}"
        try:
            svg = resolved.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            return f"Error: File is not a text file: {file}"

    if not svg:
        return (
            "Error: Provide either 'file' (path to an .svg file in the workspace) or 'svg' "
            "(inline markup). Preferred: write_file then create_svg(file=...)."
        )

    try:
        clean, doc = prepare_text(svg)
    except SvgParseError as e:
        return f"Error: {e}"

    notes: list[str] = []
    if doc.removed:
        notes.append(
            "Removed (an SVG document here must be self-contained): "
            + ", ".join(doc.removed)
        )
    notes.extend(doc.warnings)

    blank_reason = await _render_check(clean, doc.width, doc.height)
    if blank_reason:
        return (
            f"Error: the SVG renders blank ({blank_reason}). Common causes: the viewBox does "
            f"not contain the geometry, shapes fall outside it, or fill/stroke are unset. "
            f"Document size is {doc.width}x{doc.height}, viewBox is "
            f"'{doc.root.get('viewBox')}'."
        )

    stem = _safe_stem(title) or f"svg_{uuid.uuid4().hex[:8]}"
    svg_path = Path(workspace_dir) / f"{stem}.svg"
    svg_path.write_text(clean, encoding="utf-8")

    session = kwargs.get("session")
    if not session:
        return str(svg_path)

    try:
        media_id = await _save_to_library(
            session=session,
            svg_path=svg_path,
            width=doc.width,
            height=doc.height,
            session_media_ids=kwargs.get("session_media_ids"),
            project_id=kwargs.get("project_id"),
        )
    except Exception as e:
        log.error(f"Failed to save SVG to library: {e}")
        return str(svg_path)

    result = {
        "media_id": media_id,
        "file": svg_path.name,
        "width": doc.width,
        "height": doc.height,
    }
    if notes:
        result["notes"] = notes
    return json.dumps(result)


def _safe_stem(title: str | None) -> str | None:
    if not title:
        return None
    keep = [c if (c.isalnum() or c in "-_") else "-" for c in title.strip().lower()]
    stem = "".join(keep).strip("-")
    while "--" in stem:
        stem = stem.replace("--", "-")
    return stem[:48] or None


async def _render_check(svg_text: str, width: int, height: int) -> str | None:
    """Return a reason string if the document renders blank, else None.

    A render that cannot run at all (no UI client, renderer busy) is not a
    failure of the document, so it passes — blocking a save on renderer
    availability would be worse than saving something unverified.
    """
    import io

    from PIL import Image

    from utils.ui_render import (
        LayoutRenderBusy,
        LayoutRenderUnavailable,
        render_svg_document,
    )

    scale = _BLANK_CHECK_SIZE / max(width, height)
    check_w = max(1, min(width, int(round(width * scale)) or 1))
    check_h = max(1, min(height, int(round(height * scale)) or 1))

    try:
        png_bytes = await render_svg_document(
            svg_text,
            check_w,
            check_h,
            wait_for_client_timeout_s=2.0,
            queue_timeout_s=5.0,
        )
    except (LayoutRenderBusy, LayoutRenderUnavailable) as e:
        log.debug(f"Skipped blank check for SVG: {e}")
        return None
    except Exception as e:
        return f"render failed: {e}"

    try:
        img = Image.open(io.BytesIO(png_bytes))
        img.load()
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        if img.getbbox() is None:
            return "nothing was drawn"
        alpha_max = img.getchannel("A").getextrema()[1]
        if alpha_max == 0:
            return "every pixel is fully transparent"
    except Exception as e:
        log.warning(f"Blank check could not inspect the render: {e}")
    return None


async def _save_to_library(
    session,
    svg_path: Path,
    width: int,
    height: int,
    session_media_ids: list[int] | None = None,
    project_id: int | None = None,
) -> int:
    """Save the SVG document to the library and return the media_id."""
    import hashlib
    import os
    import shutil

    from core.profile_context import get_current_profile
    from database import MediaItem, MediaLineage

    profile_id = get_current_profile()
    output_folder = app_dirs.get_managed_staging_dir(profile_id, "generated")
    os.makedirs(output_folder, exist_ok=True)

    dest = os.path.join(output_folder, svg_path.name)
    if os.path.exists(dest):
        stem = svg_path.stem
        counter = 1
        while os.path.exists(dest):
            dest = os.path.join(output_folder, f"{stem}_{counter}.svg")
            counter += 1

    shutil.copy2(str(svg_path), dest)
    dest_path = Path(dest)

    file_bytes = dest_path.read_bytes()
    source_ids = list(session_media_ids or [])

    gen_meta = build_generation_metadata(
        task_type="vector",
        source="agent_v2_create_svg",
        source_inputs=[{"media_id": mid, "role": "source_image"} for mid in source_ids],
    )

    media_item = MediaItem(
        file_path=dest,
        file_hash=hashlib.sha256(file_bytes).hexdigest(),
        file_size=len(file_bytes),
        file_format="svg",
        width=width,
        height=height,
        megapixels=(width * height) / 1_000_000,
        has_alpha=True,
        metadata_status="completed",
        metadata_config_version=get_config_version_manager().get_version('metadata'),
        metadata_processed_at=datetime.utcnow(),
        # Vector documents carry no photographic content for the AI pipeline to
        # index, same as layouts.
        clip_status="skipped",
        face_detection_status="skipped",
        vlm_caption_status="skipped",
        created_date=datetime.utcnow(),
        modified_date=datetime.utcnow(),
        indexed_date=datetime.utcnow(),
        generation_metadata=json.dumps(gen_meta),
    )
    session.add(media_item)
    await session.flush()

    from storage_service import stage_managed_media

    await stage_managed_media(
        session,
        media=media_item,
        profile_id=profile_id,
        remove_source=True,
    )

    for idx, source_media_id in enumerate(source_ids):
        session.add(MediaLineage(
            media_id=media_item.id,
            source_media_id=source_media_id,
            source_order=idx,
            task_type="vector",
            relationship_type="derived",
        ))

    if project_id is not None:
        from project_service import attach_media_to_project
        await attach_media_to_project(session, project_id, media_item.id)
        log.info(f"[create_svg] Attached media {media_item.id} to project {project_id}")

    await session.commit()

    from storage_service import cleanup_staged_source

    await cleanup_staged_source(session, media_id=media_item.id)

    try:
        from utils.websocket import broadcast_media_updated
        await broadcast_media_updated(media_item, ["created"], session)
    except Exception as e:
        log.warning(f"[create_svg] Failed to broadcast media update: {e}")

    return media_item.id
