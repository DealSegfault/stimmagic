"""AGY-backed generation and approval for project reference workflows."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps, ImageStat
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.v2.tools.antigravity_image import antigravity_image, normalize_generated_still
from agent.v2.tools.library import save_workspace_file
from agent.v2.workspace import get_project_workspace
from asset_association_service import attach_asset_to_project
from asset_service import commit_revision, create_asset_from_media, create_asset_snapshot
from database import (
    Asset,
    AssetRevision,
    MediaItem,
    MediaLineage,
    ProjectComposition,
    ProjectCompositionItem,
    ProjectElement,
    ProjectElementState,
    ProjectReferencePack,
    ProjectReferenceView,
)
from location_prompt_service import build_location_prompt_augmentation
from reference_service import (
    ReferenceServiceError,
    get_composition,
    get_pack,
    get_view,
    json_object,
    serialize_composition,
    serialize_view,
)


_RESULT_MEDIA = re.compile(r"<result\s+media_id=(\d+)")


def _hash_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _revision_media(session: AsyncSession, revision_id: int | None) -> MediaItem | None:
    if not revision_id:
        return None
    revision = await session.get(AssetRevision, revision_id)
    if revision is None or revision.deleted_at is not None:
        return None
    media = await session.get(MediaItem, revision.primary_media_id)
    return media if media is not None and media.deleted_at is None else None


async def _approved_view_media(session: AsyncSession, view: ProjectReferenceView) -> MediaItem | None:
    return await _revision_media(session, view.approved_revision_id)


async def _sheet_media(session: AsyncSession, pack: ProjectReferencePack) -> MediaItem | None:
    return await _revision_media(session, pack.approved_sheet_revision_id)


async def _source_binding_for_media(
    session: AsyncSession,
    media_id: int,
) -> tuple[int | None, int | None]:
    revision = await session.scalar(
        select(AssetRevision).where(
            AssetRevision.primary_media_id == media_id,
            AssetRevision.deleted_at.is_(None),
        )
    )
    if revision is None:
        return None, None
    return int(revision.asset_id), int(revision.id)


async def _snapshot_generation_sources(
    session: AsyncSession,
    *,
    owner_revision_id: int,
    generated_media_id: int,
) -> None:
    lineage = list(
        await session.scalars(
            select(MediaLineage)
            .where(
                MediaLineage.media_id == generated_media_id,
                MediaLineage.source_media_id.is_not(None),
            )
            .order_by(MediaLineage.source_order, MediaLineage.id)
        )
    )
    for position, edge in enumerate(lineage):
        source_asset_id, source_revision_id = await _source_binding_for_media(
            session, int(edge.source_media_id)
        )
        await create_asset_snapshot(
            session,
            owner_kind="revision",
            owner_id=owner_revision_id,
            media_id=int(edge.source_media_id),
            role="generation_reference",
            position=position,
            source_asset_id=source_asset_id,
            source_revision_id=source_revision_id,
            idempotency_key=f"reference-generation:{owner_revision_id}:{position}:{edge.source_media_id}",
        )


def _parse_agy_result(result: str) -> int:
    if result.startswith("Error:"):
        raise ReferenceServiceError(result.removeprefix("Error:").strip())
    match = _RESULT_MEDIA.search(result)
    if not match:
        raise ReferenceServiceError(f"Antigravity returned no Media id: {result[-500:]}")
    return int(match.group(1))


async def _recover_completed_view_output(
    session: AsyncSession,
    *,
    view: ProjectReferenceView,
    output_path: Path,
    prompt: str,
    reference_media_ids: list[int],
    dimensions: list[int],
    project_id: int,
) -> int | None:
    """Ingest an AGY file left behind when print mode timed out after rendering."""
    if (
        view.status not in {"error", "generating"}
        or view.candidate_media_id
        or not output_path.is_file()
        or normalize_generated_still(output_path, dimensions)
    ):
        return None
    saved = json.loads(await save_workspace_file(
        session=session,
        path=str(output_path),
        workspace_dir=output_path.parent,
        save_tags=None,
        provenance={
            "task_type": "image-to-image" if reference_media_ids else "text-to-image",
            "tool_id": "antigravity:generate_image",
            "parameters": {
                "prompt": prompt,
                "reference_media_ids": reference_media_ids,
                "model": "Antigravity Image",
                "output_role": "intermediate",
                "recovered_after_print_timeout": True,
            },
            "source_media_ids": reference_media_ids,
        },
        project_id=project_id,
        metadata_source="agent_v2_antigravity_recovery",
        materialize_asset=False,
    ))
    return int(saved["media_id"]) if saved.get("media_id") else None


def _view_contract_text(pack: ProjectReferencePack, view: ProjectReferenceView) -> str:
    spec = json_object(view.view_spec, {})
    if pack.pack_type == "prop":
        return (
            f"Produce the {view.label} reference view. Show exactly one object, isolated on a quiet neutral "
            "seamless background, fully readable silhouette, physically plausible contact shadow, no hands, "
            "no room, no text, no collage and no duplicate. "
            f"Camera/view contract: {json.dumps(spec, ensure_ascii=False)}."
        )
    if pack.pack_type == "location":
        return (
            f"Produce one clean location plate for {view.label}. Preserve the exact architecture, wall openings, "
            "fixed furniture, materials, scale and geography. No people, no captions, no collage and no movable "
            "story props unless they are explicitly part of the canonical location identity. "
            f"Camera/view contract from the approved blocking system: {json.dumps(spec, ensure_ascii=False)}."
        )
    return (
        f"Produce the {view.label} identity reference. Preserve the exact face, hair, proportions, wardrobe and "
        f"scale. No collage and no duplicate. View contract: {json.dumps(spec, ensure_ascii=False)}."
    )


def _location_reference_lock(view: ProjectReferenceView) -> str:
    spec = json_object(view.view_spec, {})
    state = str(spec.get("location_state") or "")
    if state == "APT_MORNING":
        return (
            "REFERENCE USE — EDIT THE APPROVED APARTMENT, DO NOT REBUILD IT\n"
            "<Picture 1> is the exact approved MNESIS apartment master. Treat it as a geometry plate: preserve every "
            "wall, opening, door, window, cabinet, floor, sofa, hallway depth and fixed furniture relationship. "
            "This is a controlled relight/state conversion to APT_MORNING only: rain stops and white morning light "
            "enters. Do not replace the apartment with a new modern room, alter the floor plan, or add a balcony."
        )
    return (
        "REFERENCE USE — PRESERVE THE APPROVED APARTMENT GEOMETRY\n"
        "<Picture 1> is the exact approved MNESIS apartment master. Use it as the architectural source of truth even "
        "when the requested crop changes. Preserve the same door, windows, kitchen cabinetry, hallway depth, floor, "
        "sofa and fixed furniture. Do not reinterpret the room as a different apartment. Additional references are "
        "continuity anchors only; never make a collage or combine two architectures."
    )


async def build_view_generation_request(
    session: AsyncSession,
    *,
    project_id: int,
    view: ProjectReferenceView,
) -> tuple[str, list[int], list[int]]:
    pack = await get_pack(session, project_id=project_id, pack_id=view.pack_id)
    element = await session.get(ProjectElement, pack.project_element_id)
    if element is None or element.deleted_at is not None:
        raise ReferenceServiceError("Reference element is unavailable")
    identity_prompt = (pack.identity_prompt or element.description or "").strip()
    if not identity_prompt:
        identity_prompt = (
            f"Create a production-ready canonical visual reference for {element.name}. "
            "Keep the design specific, physically coherent and repeatable across future views."
        )

    references: list[int] = []
    roles: list[str] = []
    approved_views = list(
        await session.scalars(
            select(ProjectReferenceView)
            .where(
                ProjectReferenceView.pack_id == pack.id,
                ProjectReferenceView.approved_revision_id.is_not(None),
                ProjectReferenceView.status == "approved",
                ProjectReferenceView.deleted_at.is_(None),
            )
            .order_by(ProjectReferenceView.sort_order, ProjectReferenceView.id)
        )
    )
    anchor_order = sorted(
        approved_views,
        key=lambda candidate: (
            candidate.id != view.id,
            candidate.view_key not in {"hero_3q", "master"},
            candidate.sort_order,
        ),
    )
    for candidate in anchor_order:
        media = await _approved_view_media(session, candidate)
        if media is None or media.id in references:
            continue
        references.append(int(media.id))
        roles.append(
            f"<Picture {len(references)}> is the approved {candidate.label} identity anchor. "
            "Preserve its design; change only the requested viewpoint."
        )
        if len(references) >= 2:
            break
    sheet = await _sheet_media(session, pack)
    if sheet is not None and sheet.id not in references and len(references) < 3:
        references.append(int(sheet.id))
        roles.append(
            f"<Picture {len(references)}> is the approved reference sheet. Use it only to preserve identity "
            "across hidden surfaces and angles; do not reproduce the sheet layout."
        )

    role_text = "\n".join(roles) if roles else "No visual reference exists yet; establish the first canonical anchor from the written identity contract."
    automatic_augmentation = (
        build_location_prompt_augmentation(json_object(view.view_spec, {}))
        if pack.pack_type == "location"
        else ""
    )
    prompt_parts = [
        f"IDENTITY CONTRACT — version {pack.prompt_version}:\n{identity_prompt}\n\n",
    ]
    if automatic_augmentation:
        prompt_parts.append(f"{automatic_augmentation}\n\n")
    prompt_parts.extend([
        f"ORDERED REFERENCE ROLES:\n{role_text}\n\n",
        f"{_location_reference_lock(view)}\n\n" if pack.pack_type == "location" else "",
        f"VIEW TASK:\n{_view_contract_text(pack, view)}\n\n",
        "RETENTION RULES:\n",
        "Preserve all identity-defining shapes, proportions, materials, markings and color relationships from the "
        "approved references. Do not redesign the subject. Generate exactly one still image.\n",
    ])
    if pack.negative_prompt:
        prompt_parts.append(f"\nEXCLUSIONS:\n{pack.negative_prompt.strip()}\n")
    prompt = "".join(prompt_parts)
    dimensions = [1344, 768] if pack.pack_type == "location" else [1024, 1024]
    return prompt, references, dimensions


async def generate_view_candidate(
    session: AsyncSession,
    *,
    project_id: int,
    view_id: int,
) -> dict[str, Any]:
    view = await get_view(session, project_id=project_id, view_id=view_id)
    pack = await get_pack(session, project_id=project_id, pack_id=view.pack_id)
    prompt, reference_media_ids, dimensions = await build_view_generation_request(
        session, project_id=project_id, view=view
    )
    output_name = f"{pack.pack_type}_{pack.id}_{view.view_key}_v{pack.prompt_version}_antigravity.png"
    workspace = get_project_workspace(project_id)
    media_id = await _recover_completed_view_output(
        session,
        view=view,
        output_path=workspace / output_name,
        prompt=prompt,
        reference_media_ids=reference_media_ids,
        dimensions=dimensions,
        project_id=project_id,
    )
    if media_id is None:
        view.status = "generating"
        view.updated_at = datetime.utcnow()
        await session.commit()
        try:
            result = await antigravity_image(
                prompt,
                reference_media_ids=reference_media_ids,
                output_name=output_name,
                output_role="intermediate",
                expected_dimensions=dimensions,
                workspace_dir=workspace,
                session=session,
                project_id=project_id,
            )
            media_id = _parse_agy_result(result)
        except Exception as exc:
            view = await get_view(session, project_id=project_id, view_id=view_id)
            view.status = "error"
            view.updated_at = datetime.utcnow()
            await session.commit()
            if isinstance(exc, ReferenceServiceError):
                raise
            raise ReferenceServiceError(str(exc)) from exc

    view = await get_view(session, project_id=project_id, view_id=view_id)
    view.candidate_media_id = media_id
    view.status = "review"
    view.source_signature = _hash_payload({
        "prompt_version": pack.prompt_version,
        "view_spec": json_object(view.view_spec, {}),
        "reference_media_ids": reference_media_ids,
        "dimensions": dimensions,
    })
    view.updated_at = datetime.utcnow()
    pack.status = "review"
    pack.updated_at = datetime.utcnow()
    await session.commit()
    return await serialize_view(session, view)


async def _promote_candidate(
    session: AsyncSession,
    *,
    media_id: int,
    asset_id: int | None,
    project_id: int,
    title: str,
    origin_type: str,
) -> tuple[Asset, AssetRevision]:
    media = await session.get(MediaItem, media_id)
    if media is None or media.deleted_at is not None:
        raise ReferenceServiceError("Candidate Media is unavailable")
    if asset_id:
        revision = await commit_revision(
            session,
            asset_id=asset_id,
            media_id=media_id,
            note="Approved reference generation",
            idempotency_key=f"{origin_type}:asset:{asset_id}:media:{media_id}",
        )
        asset = await session.get(Asset, asset_id)
        if asset is None:
            raise ReferenceServiceError("Reference Asset is unavailable")
    else:
        asset = await create_asset_from_media(
            session,
            media_id=media_id,
            title=title,
            origin_type=origin_type,
            origin_id=str(media_id),
            idempotency_key=f"{origin_type}:media:{media_id}",
        )
        revision = await session.get(AssetRevision, asset.current_revision_id)
        if revision is None:
            raise ReferenceServiceError("Approved Asset revision was not created")
    await attach_asset_to_project(session, project_id, asset.id)
    await _snapshot_generation_sources(
        session,
        owner_revision_id=int(revision.id),
        generated_media_id=media_id,
    )
    return asset, revision


async def approve_view_candidate(
    session: AsyncSession,
    *,
    project_id: int,
    view_id: int,
) -> dict[str, Any]:
    view = await get_view(session, project_id=project_id, view_id=view_id)
    if not view.candidate_media_id:
        raise ReferenceServiceError("This view has no candidate to approve")
    pack = await get_pack(session, project_id=project_id, pack_id=view.pack_id)
    element = await session.get(ProjectElement, pack.project_element_id)
    if element is None:
        raise ReferenceServiceError("Reference element is unavailable")
    asset, revision = await _promote_candidate(
        session,
        media_id=int(view.candidate_media_id),
        asset_id=view.asset_id,
        project_id=project_id,
        title=f"{element.name} · {view.label}",
        origin_type="project_reference_view",
    )
    view.asset_id = asset.id
    view.approved_revision_id = revision.id
    view.candidate_media_id = None
    view.status = "approved"
    view.updated_at = datetime.utcnow()
    if element.asset_id is None or view.view_key in {"hero_3q", "master"}:
        element.asset_id = asset.id
        element.updated_at = datetime.utcnow()
    await session.commit()
    await render_reference_sheet(session, project_id=project_id, pack_id=pack.id)
    view = await get_view(session, project_id=project_id, view_id=view_id)
    return await serialize_view(session, view)


async def reject_view_candidate(
    session: AsyncSession,
    *,
    project_id: int,
    view_id: int,
) -> dict[str, Any]:
    view = await get_view(session, project_id=project_id, view_id=view_id)
    view.status = "rejected"
    view.candidate_media_id = None
    view.updated_at = datetime.utcnow()
    await session.commit()
    return await serialize_view(session, view)


def _font(size: int) -> ImageFont.ImageFont:
    candidates = (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


async def render_reference_sheet(
    session: AsyncSession,
    *,
    project_id: int,
    pack_id: int,
) -> dict[str, Any]:
    pack = await get_pack(session, project_id=project_id, pack_id=pack_id)
    element = await session.get(ProjectElement, pack.project_element_id)
    views = list(
        await session.scalars(
            select(ProjectReferenceView)
            .where(
                ProjectReferenceView.pack_id == pack.id,
                ProjectReferenceView.approved_revision_id.is_not(None),
                ProjectReferenceView.deleted_at.is_(None),
            )
            .order_by(ProjectReferenceView.sort_order, ProjectReferenceView.id)
        )
    )
    media_rows: list[tuple[ProjectReferenceView, MediaItem]] = []
    for view in views:
        media = await _approved_view_media(session, view)
        if media is not None and Path(media.file_path).is_file():
            media_rows.append((view, media))
    if not media_rows:
        raise ReferenceServiceError("Approve at least one view before rendering a sheet")

    columns = 3
    cell_width = 520
    image_height = 292 if pack.pack_type == "location" else 440
    label_height = 64
    header_height = 110
    rows = (len(media_rows) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width, header_height + rows * (image_height + label_height)), "#090b10")
    draw = ImageDraw.Draw(sheet)
    draw.text((28, 24), element.name if element else "Reference sheet", fill="#f4f4f5", font=_font(32))
    draw.text(
        (28, 68),
        f"@{element.reference_id if element else 'reference'} · identity prompt v{pack.prompt_version} · {len(media_rows)} approved view(s)",
        fill="#a1a1aa",
        font=_font(18),
    )
    for index, (view, media) in enumerate(media_rows):
        row, column = divmod(index, columns)
        x = column * cell_width
        y = header_height + row * (image_height + label_height)
        with Image.open(media.file_path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            contained = ImageOps.contain(image, (cell_width - 16, image_height - 16), Image.Resampling.LANCZOS)
            tile = Image.new("RGB", (cell_width, image_height), "#111318")
            tile.paste(contained, ((cell_width - contained.width) // 2, (image_height - contained.height) // 2))
            sheet.paste(tile, (x, y))
        draw.text((x + 16, y + image_height + 10), view.label, fill="#e4e4e7", font=_font(20))
        draw.text((x + 16, y + image_height + 36), view.view_key, fill="#2dd4bf", font=_font(15))

    workspace = Path(get_project_workspace(project_id))
    workspace.mkdir(parents=True, exist_ok=True)
    output_path = workspace / f"reference_pack_{pack.id}_v{pack.prompt_version}_sheet.png"
    sheet.save(output_path, format="PNG", optimize=True)
    source_media_ids = [int(media.id) for _, media in media_rows]
    saved = json.loads(await save_workspace_file(
        session=session,
        path=str(output_path),
        workspace_dir=workspace,
        save_tags=None,
        provenance={
            "task_type": "reference-sheet",
            "tool_id": "stimma:reference-sheet-renderer",
            "parameters": {"pack_id": pack.id, "prompt_version": pack.prompt_version},
            "source_media_ids": source_media_ids,
        },
        project_id=project_id,
        metadata_source="project_reference_sheet",
        materialize_asset=False,
    ))
    media_id = int(saved["media_id"])
    pack = await get_pack(session, project_id=project_id, pack_id=pack_id)
    asset, revision = await _promote_candidate(
        session,
        media_id=media_id,
        asset_id=pack.sheet_asset_id,
        project_id=project_id,
        title=f"{element.name if element else 'Reference'} · view sheet",
        origin_type="project_reference_sheet",
    )
    pack.sheet_asset_id = asset.id
    pack.approved_sheet_revision_id = revision.id
    required_views = list(
        await session.scalars(
            select(ProjectReferenceView).where(
                ProjectReferenceView.pack_id == pack.id,
                ProjectReferenceView.deleted_at.is_(None),
            )
        )
    )
    pack.status = "approved" if all(
        view.approved_revision_id and view.status == "approved"
        for view in required_views
    ) else "review"
    pack.updated_at = datetime.utcnow()
    await session.commit()
    return {
        "pack_id": pack.id,
        "sheet_asset_id": asset.id,
        "sheet_revision_id": revision.id,
        "sheet_media_id": media_id,
        "approved_view_count": len(media_rows),
    }


async def build_composition_generation_request(
    session: AsyncSession,
    *,
    composition: ProjectComposition,
) -> tuple[str, list[int], list[int]]:
    base = await _revision_media(session, composition.base_location_revision_id)
    if base is None:
        raise ReferenceServiceError("The pinned clean location plate is unavailable")
    location_view = await session.get(ProjectReferenceView, composition.location_view_id)
    if location_view is None:
        raise ReferenceServiceError("Location view is unavailable")
    location_pack = await session.get(ProjectReferencePack, location_view.pack_id)
    items = list(
        await session.scalars(
            select(ProjectCompositionItem)
            .where(
                ProjectCompositionItem.composition_id == composition.id,
                ProjectCompositionItem.deleted_at.is_(None),
            )
            .order_by(ProjectCompositionItem.item_order, ProjectCompositionItem.id)
        )
    )
    references = [int(base.id)]
    roles = [
        "<Picture 1> is the exact approved clean location plate. Preserve every pixel outside the requested edit region: architecture, fixed furniture, lighting, camera and crop."
    ]
    item_instructions: list[str] = []
    for item in items:
        media = await _revision_media(session, item.source_revision_id)
        element = await session.get(ProjectElement, item.project_element_id)
        state = await session.get(ProjectElementState, item.state_id) if item.state_id else None
        if media is None or element is None:
            raise ReferenceServiceError("A pinned composition source is unavailable")
        if media.id not in references and len(references) < 7:
            references.append(int(media.id))
            picture = len(references)
            roles.append(
                f"<Picture {picture}> is the exact approved identity view for @{element.reference_id} ({element.name}). Preserve its silhouette, proportions, materials and markings."
            )
        else:
            picture = references.index(int(media.id)) + 1
        state_delta = state.prompt_delta if state and state.prompt_delta else "canonical state"
        placement = json_object(item.placement, {})
        item_instructions.append(
            f"Place exactly one @{element.reference_id} from <Picture {picture}> in state '{state.label if state else 'Canonical'}' ({state_delta}). "
            f"Placement contract: {json.dumps(placement, ensure_ascii=False)}."
        )
    if composition.placement_guide_media_id and len(references) < 8:
        guide = await session.get(MediaItem, composition.placement_guide_media_id)
        if guide is not None and guide.deleted_at is None:
            references.append(int(guide.id))
            roles.append(
                f"<Picture {len(references)}> is a placement/blocking guide. Use only its placement information; do not reproduce its graphics, labels or colors."
            )
    prompt = (
        f"LOCATION IDENTITY CONTRACT — version {location_pack.prompt_version if location_pack else 1}:\n"
        f"{(location_pack.identity_prompt if location_pack else '') or 'Preserve the approved location plate exactly.'}\n\n"
        "ORDERED REFERENCE ROLES:\n" + "\n".join(roles) + "\n\n"
        "COMPOSITION TASK:\n" + "\n".join(item_instructions) + "\n"
        + ((composition.prompt_delta or "").strip() + "\n" if composition.prompt_delta else "")
        + "\nSTRICT EDIT LOCK:\n"
        "Edit Picture 1 rather than rebuilding it. Keep identical camera position, perspective, crop, walls, doors, windows, fixed furniture, materials and lighting. Change only the minimum region required to insert the listed items with plausible scale, contact shadow and occlusion. No extra props, no duplicates, no text, no collage. Generate exactly one still image."
    )
    return prompt, references, [int(base.width), int(base.height)]


def _composition_exclusion_mask(size: tuple[int, int], placements: list[dict[str, Any]]) -> Image.Image:
    width, height = size
    mask = Image.new("L", size, 255)
    draw = ImageDraw.Draw(mask)
    for placement in placements:
        x = float(placement.get("x", 0.5))
        y = float(placement.get("y", 0.5))
        w = float(placement.get("width", placement.get("scale", 0.2)))
        h = float(placement.get("height", placement.get("scale", 0.2)))
        if x > 1 or y > 1 or w > 1 or h > 1:
            x, y, w, h = x / width, y / height, w / width, h / height
        padding = 0.08
        left = max(0, int((x - w / 2 - padding) * width))
        top = max(0, int((y - h / 2 - padding) * height))
        right = min(width, int((x + w / 2 + padding) * width))
        bottom = min(height, int((y + h / 2 + padding) * height))
        draw.rectangle((left, top, right, bottom), fill=0)
    return mask


async def validate_composition_candidate(
    session: AsyncSession,
    *,
    composition: ProjectComposition,
    candidate_media_id: int,
) -> dict[str, Any]:
    base = await _revision_media(session, composition.base_location_revision_id)
    candidate = await session.get(MediaItem, candidate_media_id)
    if base is None or candidate is None:
        raise ReferenceServiceError("Composition comparison media is unavailable")
    if [base.width, base.height] != [candidate.width, candidate.height]:
        return {
            "verdict": "inconsistent",
            "background_similarity": 0.0,
            "message": "Candidate dimensions differ from the pinned clean plate.",
        }
    items = list(
        await session.scalars(
            select(ProjectCompositionItem).where(
                ProjectCompositionItem.composition_id == composition.id,
                ProjectCompositionItem.deleted_at.is_(None),
            )
        )
    )
    placements = [json_object(item.placement, {}) for item in items]
    try:
        with Image.open(base.file_path) as base_image, Image.open(candidate.file_path) as candidate_image:
            original = ImageOps.exif_transpose(base_image).convert("RGB")
            generated = ImageOps.exif_transpose(candidate_image).convert("RGB")
            mask = _composition_exclusion_mask(original.size, placements)
            difference = ImageChops.difference(original, generated)
            channel_means = ImageStat.Stat(difference, mask=mask).mean
            normalized_mae = sum(channel_means) / (len(channel_means) * 255.0)
    except OSError as exc:
        raise ReferenceServiceError(f"Unable to compare composition candidate: {exc}") from exc
    similarity = round(max(0.0, 1.0 - normalized_mae), 4)
    verdict = "review" if similarity >= 0.78 else "inconsistent"
    return {
        "verdict": verdict,
        "background_similarity": similarity,
        "threshold": 0.78,
        "message": (
            "Background outside the placement region is stable enough for visual review."
            if verdict == "review"
            else "The candidate changed too much of the clean location outside the placement region."
        ),
    }


async def generate_composition_candidate(
    session: AsyncSession,
    *,
    project_id: int,
    composition_id: int,
) -> dict[str, Any]:
    composition = await get_composition(session, project_id=project_id, composition_id=composition_id)
    composition.status = "generating"
    composition.updated_at = datetime.utcnow()
    await session.commit()
    prompt, reference_media_ids, dimensions = await build_composition_generation_request(
        session, composition=composition
    )
    try:
        result = await antigravity_image(
            prompt,
            reference_media_ids=reference_media_ids,
            output_name=f"composition_{composition.id}_v{composition.prompt_version}_antigravity.png",
            output_role="intermediate",
            expected_dimensions=dimensions,
            workspace_dir=get_project_workspace(project_id),
            session=session,
            project_id=project_id,
        )
        media_id = _parse_agy_result(result)
        composition = await get_composition(session, project_id=project_id, composition_id=composition_id)
        validation = await validate_composition_candidate(
            session, composition=composition, candidate_media_id=media_id
        )
    except Exception as exc:
        composition = await get_composition(session, project_id=project_id, composition_id=composition_id)
        composition.status = "error"
        composition.updated_at = datetime.utcnow()
        await session.commit()
        if isinstance(exc, ReferenceServiceError):
            raise
        raise ReferenceServiceError(str(exc)) from exc
    composition.candidate_media_id = media_id
    composition.validation = json.dumps(validation, ensure_ascii=False)
    composition.status = validation["verdict"]
    composition.updated_at = datetime.utcnow()
    await session.commit()
    return await serialize_composition(session, composition)


async def approve_composition_candidate(
    session: AsyncSession,
    *,
    project_id: int,
    composition_id: int,
    force: bool = False,
) -> dict[str, Any]:
    composition = await get_composition(session, project_id=project_id, composition_id=composition_id)
    if not composition.candidate_media_id:
        raise ReferenceServiceError("This composition has no candidate to approve")
    if composition.status == "inconsistent" and not force:
        raise ReferenceServiceError("Background consistency check failed; regenerate or explicitly force approval")
    asset, revision = await _promote_candidate(
        session,
        media_id=int(composition.candidate_media_id),
        asset_id=composition.result_asset_id,
        project_id=project_id,
        title=composition.name,
        origin_type="project_composition",
    )
    composition.result_asset_id = asset.id
    composition.approved_revision_id = revision.id
    composition.candidate_media_id = None
    composition.status = "approved"
    composition.updated_at = datetime.utcnow()
    await session.commit()
    return await serialize_composition(session, composition)


async def reject_composition_candidate(
    session: AsyncSession,
    *,
    project_id: int,
    composition_id: int,
) -> dict[str, Any]:
    composition = await get_composition(session, project_id=project_id, composition_id=composition_id)
    composition.candidate_media_id = None
    composition.status = "rejected"
    composition.updated_at = datetime.utcnow()
    await session.commit()
    return await serialize_composition(session, composition)
