"""Project reference packs, approved views, semantic states and compositions.

The semantic root (ProjectElement) is intentionally separate from generated
images.  Views are stable camera/object identities, revisions are iterations
of one view, and compositions pin exact approved revisions so later edits do
not silently rewrite continuity.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
import re
import unicodedata
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from blocking_service import build_blocking_view
from database import (
    Asset,
    AssetRevision,
    MediaItem,
    Project,
    ProjectComposition,
    ProjectCompositionItem,
    ProjectElement,
    ProjectElementState,
    ProjectReferencePack,
    ProjectReferenceView,
    ProjectScene,
    ProjectShot,
)


class ReferenceServiceError(ValueError):
    """A reference workflow request violates a durable continuity invariant."""


PROP_VIEW_SLOTS: tuple[tuple[str, str, str, dict[str, Any]], ...] = (
    ("hero_3q", "Hero 3/4", "identity", {"azimuth": 45, "elevation": 10, "framing": "object"}),
    ("front", "Face", "identity", {"azimuth": 0, "elevation": 0, "framing": "object"}),
    ("left", "Profil gauche", "identity", {"azimuth": -90, "elevation": 0, "framing": "object"}),
    ("right", "Profil droit", "identity", {"azimuth": 90, "elevation": 0, "framing": "object"}),
    ("back", "Dos", "identity", {"azimuth": 180, "elevation": 0, "framing": "object"}),
    ("top", "Dessus", "identity", {"azimuth": 0, "elevation": 90, "framing": "object"}),
)

LOCATION_VIEW_SLOTS: tuple[tuple[str, str, str, dict[str, Any]], ...] = (
    ("master", "Vue maîtresse", "location_camera", {"framing": "wide", "clean_plate": True}),
)

CHARACTER_VIEW_SLOTS: tuple[tuple[str, str, str, dict[str, Any]], ...] = (
    ("hero_3q", "Hero 3/4", "identity", {"azimuth": 45, "framing": "full_body"}),
)


def json_object(raw: str | None, fallback: Any) -> Any:
    try:
        value = json.loads(raw) if raw else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return value if isinstance(value, type(fallback)) else fallback


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"[^a-z0-9]+", "_", ascii_value).strip("_") or "view"


def _angle_delta(a: float, b: float) -> float:
    return abs((float(a) - float(b) + 180.0) % 360.0 - 180.0)


def _signature(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_dump(payload).encode("utf-8")).hexdigest()


def default_slots(element_type: str) -> tuple[tuple[str, str, str, dict[str, Any]], ...]:
    if element_type == "prop":
        return PROP_VIEW_SLOTS
    if element_type == "location":
        return LOCATION_VIEW_SLOTS
    return CHARACTER_VIEW_SLOTS


async def _approved_media_id(session: AsyncSession, revision_id: int | None) -> int | None:
    if not revision_id:
        return None
    revision = await session.get(AssetRevision, revision_id)
    if revision is None or revision.deleted_at is not None:
        return None
    return int(revision.primary_media_id)


async def _asset_current_revision(session: AsyncSession, asset_id: int | None) -> AssetRevision | None:
    if not asset_id:
        return None
    asset = await session.get(Asset, asset_id)
    if (
        asset is None
        or asset.deleted_at is not None
        or asset.state != "active"
        or not asset.current_revision_id
    ):
        return None
    revision = await session.get(AssetRevision, asset.current_revision_id)
    return revision if revision is not None and revision.deleted_at is None else None


async def ensure_reference_pack(
    session: AsyncSession,
    element: ProjectElement,
) -> ProjectReferencePack:
    pack = await session.scalar(
        select(ProjectReferencePack).where(
            ProjectReferencePack.project_element_id == element.id,
            ProjectReferencePack.deleted_at.is_(None),
        )
    )
    created = pack is None
    if pack is None:
        pack = ProjectReferencePack(
            project_id=element.project_id,
            project_element_id=element.id,
            pack_type=element.element_type,
            identity_prompt=element.description,
            status="draft",
        )
        session.add(pack)
        await session.flush()

    state = await session.scalar(
        select(ProjectElementState).where(
            ProjectElementState.project_element_id == element.id,
            ProjectElementState.state_key == "default",
            ProjectElementState.deleted_at.is_(None),
        )
    )
    if state is None:
        state = ProjectElementState(
            project_id=element.project_id,
            project_element_id=element.id,
            state_key="default",
            label="Clean plate" if element.element_type == "location" else "Canonical",
            is_default=True,
        )
        session.add(state)

    existing_views = list(
        await session.scalars(
            select(ProjectReferenceView).where(
                ProjectReferenceView.pack_id == pack.id,
                ProjectReferenceView.deleted_at.is_(None),
            )
        )
    )
    existing_keys = {(view.view_key, view.state_key) for view in existing_views}
    legacy_revision = await _asset_current_revision(session, element.asset_id)
    for index, (key, label, view_type, spec) in enumerate(default_slots(element.element_type)):
        if (key, "default") in existing_keys:
            continue
        is_anchor = index == 0 and legacy_revision is not None
        view = ProjectReferenceView(
            project_id=element.project_id,
            pack_id=pack.id,
            view_key=key,
            label=label,
            view_type=view_type,
            state_key="default",
            view_spec=_dump(spec),
            asset_id=element.asset_id if is_anchor else None,
            approved_revision_id=legacy_revision.id if is_anchor else None,
            status="approved" if is_anchor else "missing",
            sort_order=index,
        )
        session.add(view)

    if created and legacy_revision is not None:
        pack.status = "review"
    await session.flush()
    return pack


async def ensure_project_reference_packs(
    session: AsyncSession,
    project_id: int,
) -> list[ProjectReferencePack]:
    project = await session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise ReferenceServiceError(f"Project {project_id} not found")
    elements = list(
        await session.scalars(
            select(ProjectElement)
            .where(
                ProjectElement.project_id == project_id,
                ProjectElement.deleted_at.is_(None),
            )
            .order_by(ProjectElement.element_type, ProjectElement.name, ProjectElement.id)
        )
    )
    packs = [await ensure_reference_pack(session, element) for element in elements]
    await session.flush()
    return packs


async def get_pack(
    session: AsyncSession,
    *,
    project_id: int,
    pack_id: int,
) -> ProjectReferencePack:
    pack = await session.scalar(
        select(ProjectReferencePack).where(
            ProjectReferencePack.id == pack_id,
            ProjectReferencePack.project_id == project_id,
            ProjectReferencePack.deleted_at.is_(None),
        )
    )
    if pack is None:
        raise ReferenceServiceError("Reference pack not found")
    return pack


async def get_view(
    session: AsyncSession,
    *,
    project_id: int,
    view_id: int,
) -> ProjectReferenceView:
    view = await session.scalar(
        select(ProjectReferenceView).where(
            ProjectReferenceView.id == view_id,
            ProjectReferenceView.project_id == project_id,
            ProjectReferenceView.deleted_at.is_(None),
        )
    )
    if view is None:
        raise ReferenceServiceError("Reference view not found")
    return view


async def serialize_view(session: AsyncSession, view: ProjectReferenceView) -> dict[str, Any]:
    approved_media_id = await _approved_media_id(session, view.approved_revision_id)
    candidate = await session.get(MediaItem, view.candidate_media_id) if view.candidate_media_id else None
    return {
        "id": view.id,
        "project_id": view.project_id,
        "pack_id": view.pack_id,
        "view_key": view.view_key,
        "label": view.label,
        "view_type": view.view_type,
        "state_key": view.state_key,
        "view_spec": json_object(view.view_spec, {}),
        "asset_id": view.asset_id,
        "approved_revision_id": view.approved_revision_id,
        "approved_media_id": approved_media_id,
        "candidate_media_id": candidate.id if candidate and candidate.deleted_at is None else None,
        "status": view.status,
        "source_signature": view.source_signature,
        "sort_order": view.sort_order,
        "created_at": view.created_at.isoformat() if view.created_at else None,
        "updated_at": view.updated_at.isoformat() if view.updated_at else None,
    }


async def serialize_state(state: ProjectElementState) -> dict[str, Any]:
    return {
        "id": state.id,
        "project_id": state.project_id,
        "project_element_id": state.project_element_id,
        "state_key": state.state_key,
        "label": state.label,
        "prompt_delta": state.prompt_delta or "",
        "constraints": json_object(state.constraints, {}),
        "is_default": bool(state.is_default),
    }


async def serialize_composition(
    session: AsyncSession,
    composition: ProjectComposition,
) -> dict[str, Any]:
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
    item_rows: list[dict[str, Any]] = []
    for item in items:
        element = await session.get(ProjectElement, item.project_element_id)
        state = await session.get(ProjectElementState, item.state_id) if item.state_id else None
        view = await session.get(ProjectReferenceView, item.reference_view_id)
        item_rows.append({
            "id": item.id,
            "project_element_id": item.project_element_id,
            "element_name": element.name if element else None,
            "reference_id": element.reference_id if element else None,
            "reference_view_id": item.reference_view_id,
            "view_label": view.label if view else None,
            "source_revision_id": item.source_revision_id,
            "source_media_id": await _approved_media_id(session, item.source_revision_id),
            "state_id": item.state_id,
            "state_key": state.state_key if state else "default",
            "state_label": state.label if state else "Canonical",
            "role": item.role,
            "placement": json_object(item.placement, {}),
            "item_order": item.item_order,
        })
    return {
        "id": composition.id,
        "project_id": composition.project_id,
        "name": composition.name,
        "location_view_id": composition.location_view_id,
        "base_location_revision_id": composition.base_location_revision_id,
        "base_location_media_id": await _approved_media_id(session, composition.base_location_revision_id),
        "result_asset_id": composition.result_asset_id,
        "approved_revision_id": composition.approved_revision_id,
        "approved_media_id": await _approved_media_id(session, composition.approved_revision_id),
        "candidate_media_id": composition.candidate_media_id,
        "placement_guide_media_id": composition.placement_guide_media_id,
        "prompt_delta": composition.prompt_delta or "",
        "prompt_version": composition.prompt_version,
        "source_signature": composition.source_signature,
        "status": composition.status,
        "validation": json_object(composition.validation, {}),
        "items": item_rows,
        "created_at": composition.created_at.isoformat() if composition.created_at else None,
        "updated_at": composition.updated_at.isoformat() if composition.updated_at else None,
    }


async def serialize_pack(session: AsyncSession, pack: ProjectReferencePack) -> dict[str, Any]:
    element = await session.get(ProjectElement, pack.project_element_id)
    views = list(
        await session.scalars(
            select(ProjectReferenceView)
            .where(
                ProjectReferenceView.pack_id == pack.id,
                ProjectReferenceView.deleted_at.is_(None),
            )
            .order_by(ProjectReferenceView.sort_order, ProjectReferenceView.id)
        )
    )
    states = list(
        await session.scalars(
            select(ProjectElementState)
            .where(
                ProjectElementState.project_element_id == pack.project_element_id,
                ProjectElementState.deleted_at.is_(None),
            )
            .order_by(ProjectElementState.is_default.desc(), ProjectElementState.id)
        )
    )
    compositions: list[ProjectComposition] = []
    if pack.pack_type == "location" and views:
        compositions = list(
            await session.scalars(
                select(ProjectComposition)
                .where(
                    ProjectComposition.project_id == pack.project_id,
                    ProjectComposition.location_view_id.in_([view.id for view in views]),
                    ProjectComposition.deleted_at.is_(None),
                )
                .order_by(ProjectComposition.updated_at.desc(), ProjectComposition.id.desc())
            )
        )
    view_statuses = [view.status for view in views]
    all_approved = bool(views) and all(
        view.status == "approved" and view.approved_revision_id
        for view in views
    )
    if all_approved:
        effective_status = "approved"
    elif "error" in view_statuses:
        effective_status = "error"
    elif "inconsistent" in view_statuses:
        effective_status = "inconsistent"
    elif "generating" in view_statuses:
        effective_status = "generating"
    elif "review" in view_statuses or any(view.approved_revision_id for view in views):
        effective_status = "review"
    elif "stale" in view_statuses:
        effective_status = "stale"
    else:
        effective_status = "draft"
    return {
        "id": pack.id,
        "project_id": pack.project_id,
        "project_element_id": pack.project_element_id,
        "element": {
            "id": element.id if element else None,
            "name": element.name if element else "Unavailable element",
            "reference_id": element.reference_id if element else None,
            "element_type": element.element_type if element else pack.pack_type,
            "description": element.description if element else None,
            "asset_id": element.asset_id if element else None,
        },
        "pack_type": pack.pack_type,
        "identity_prompt": pack.identity_prompt or "",
        "negative_prompt": pack.negative_prompt or "",
        "prompt_version": pack.prompt_version,
        "sheet_asset_id": pack.sheet_asset_id,
        "approved_sheet_revision_id": pack.approved_sheet_revision_id,
        "sheet_media_id": await _approved_media_id(session, pack.approved_sheet_revision_id),
        "status": effective_status,
        "views": [await serialize_view(session, view) for view in views],
        "states": [await serialize_state(state) for state in states],
        "compositions": [await serialize_composition(session, item) for item in compositions],
    }


async def reference_workspace_payload(session: AsyncSession, project_id: int) -> dict[str, Any]:
    packs = await ensure_project_reference_packs(session, project_id)
    await session.commit()
    rows = [await serialize_pack(session, pack) for pack in packs]
    approved_views = sum(
        1 for pack in rows for view in pack["views"] if view["status"] == "approved"
    )
    total_views = sum(len(pack["views"]) for pack in rows)
    return {
        "project_id": project_id,
        "packs": rows,
        "stats": {
            "pack_count": len(rows),
            "location_count": sum(pack["pack_type"] == "location" for pack in rows),
            "prop_count": sum(pack["pack_type"] == "prop" for pack in rows),
            "approved_view_count": approved_views,
            "view_count": total_views,
            "missing_view_count": max(0, total_views - approved_views),
            "composition_count": sum(len(pack["compositions"]) for pack in rows),
        },
    }


async def update_pack_contract(
    session: AsyncSession,
    *,
    pack: ProjectReferencePack,
    identity_prompt: str | None = None,
    negative_prompt: str | None = None,
) -> ProjectReferencePack:
    changed = False
    if identity_prompt is not None and identity_prompt.strip() != (pack.identity_prompt or ""):
        pack.identity_prompt = identity_prompt.strip() or None
        changed = True
    if negative_prompt is not None and negative_prompt.strip() != (pack.negative_prompt or ""):
        pack.negative_prompt = negative_prompt.strip() or None
        changed = True
    if changed:
        pack.prompt_version += 1
        pack.status = "stale" if pack.status == "approved" else "draft"
        views = await session.scalars(
            select(ProjectReferenceView).where(
                ProjectReferenceView.pack_id == pack.id,
                ProjectReferenceView.approved_revision_id.is_not(None),
                ProjectReferenceView.deleted_at.is_(None),
            )
        )
        for view in views:
            view.status = "stale"
            view.updated_at = datetime.utcnow()
        pack.updated_at = datetime.utcnow()
    await session.flush()
    return pack


async def create_element_state(
    session: AsyncSession,
    *,
    project_id: int,
    element_id: int,
    state_key: str,
    label: str,
    prompt_delta: str | None = None,
    constraints: dict[str, Any] | None = None,
) -> ProjectElementState:
    element = await session.scalar(
        select(ProjectElement).where(
            ProjectElement.id == element_id,
            ProjectElement.project_id == project_id,
            ProjectElement.deleted_at.is_(None),
        )
    )
    if element is None:
        raise ReferenceServiceError("Project element not found")
    clean_key = _slug(state_key or label)
    existing = await session.scalar(
        select(ProjectElementState).where(
            ProjectElementState.project_element_id == element_id,
            ProjectElementState.state_key == clean_key,
            ProjectElementState.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return existing
    state = ProjectElementState(
        project_id=project_id,
        project_element_id=element_id,
        state_key=clean_key,
        label=label.strip() or clean_key,
        prompt_delta=(prompt_delta or "").strip() or None,
        constraints=_dump(constraints or {}),
    )
    session.add(state)
    await session.flush()
    return state


async def sync_location_views_from_blocking(
    session: AsyncSession,
    *,
    project_id: int,
) -> dict[str, Any]:
    """Cluster blocking cameras into durable canonical location view slots."""
    packs = await ensure_project_reference_packs(session, project_id)
    location_packs = [pack for pack in packs if pack.pack_type == "location"]
    if not location_packs:
        raise ReferenceServiceError("Create a location element before syncing blocking views")
    elements = {
        pack.id: await session.get(ProjectElement, pack.project_element_id)
        for pack in location_packs
    }
    existing_blocking_views = list(await session.scalars(
        select(ProjectReferenceView).where(
            ProjectReferenceView.pack_id.in_([pack.id for pack in location_packs]),
            ProjectReferenceView.deleted_at.is_(None),
        )
    ))
    existing_blocking_views = [
        view for view in existing_blocking_views
        if json_object(view.view_spec, {}).get("source") == "blocking-cluster-v1"
    ]
    scenes = list(
        await session.scalars(
            select(ProjectScene)
            .where(ProjectScene.project_id == project_id)
            .order_by(ProjectScene.sequence_number, ProjectScene.scene_number, ProjectScene.id)
        )
    )
    shots = list(
        await session.scalars(
            select(ProjectShot)
            .where(
                ProjectShot.project_id == project_id,
                ProjectShot.deleted_at.is_(None),
            )
            .order_by(ProjectShot.scene_id, ProjectShot.shot_number, ProjectShot.id)
        )
    )
    scene_by_id = {int(scene.id): scene for scene in scenes}
    blocking_state: dict[str, Any] = {}
    clusters: list[dict[str, Any]] = []
    for shot in shots:
        scene = scene_by_id.get(int(shot.scene_id))
        if scene is None:
            continue
        settings = json_object(shot.settings, {})
        blocking = build_blocking_view(shot, scene, blocking_state, settings=settings)
        camera = blocking.get("camera") or {}
        location = blocking.get("location") or {}
        if not camera or location.get("id") in {None, "black"}:
            continue
        matched = None
        for cluster in clusters:
            if cluster["location_id"] != location.get("id"):
                continue
            distance = math.dist(
                (float(cluster["camera"]["x"]), float(cluster["camera"]["y"])),
                (float(camera.get("x", 0)), float(camera.get("y", 0))),
            )
            if distance <= 70 and _angle_delta(cluster["camera"]["facing"], camera.get("facing", 0)) <= 15:
                matched = cluster
                break
        if matched is None:
            matched = {
                "location_id": location.get("id"),
                "location_label": location.get("label") or "Location",
                "camera": dict(camera),
                "shot_ids": [],
                "shot_numbers": [],
            }
            clusters.append(matched)
        matched["shot_ids"].append(int(shot.id))
        matched["shot_numbers"].append(int(shot.shot_number))

    created = 0
    updated = 0
    stale = 0
    seen_view_ids: set[int] = set()
    per_location_index: dict[str, int] = {}
    for cluster in clusters:
        location_id = str(cluster["location_id"])
        candidates = [
            pack for pack in location_packs
            if location_id in _slug((elements[pack.id].name if elements.get(pack.id) else ""))
            or location_id in _slug((elements[pack.id].reference_id if elements.get(pack.id) else ""))
        ]
        pack = candidates[0] if candidates else location_packs[0]
        per_location_index[location_id] = per_location_index.get(location_id, 0) + 1
        view_key = f"{_slug(location_id)}_a{per_location_index[location_id]:02d}"
        spec = {
            "location": {"id": location_id, "label": cluster["location_label"]},
            "camera": cluster["camera"],
            "used_by_shots": cluster["shot_ids"],
            "shot_numbers": cluster["shot_numbers"],
            "clean_plate": True,
            "source": "blocking-cluster-v1",
        }
        view = await session.scalar(
            select(ProjectReferenceView).where(
                ProjectReferenceView.pack_id == pack.id,
                ProjectReferenceView.view_key == view_key,
                ProjectReferenceView.state_key == "default",
                ProjectReferenceView.deleted_at.is_(None),
            )
        )
        if view is None:
            current_max = max(
                [candidate.sort_order for candidate in await session.scalars(
                    select(ProjectReferenceView).where(
                        ProjectReferenceView.pack_id == pack.id,
                        ProjectReferenceView.deleted_at.is_(None),
                    )
                )] or [0]
            )
            view = ProjectReferenceView(
                project_id=project_id,
                pack_id=pack.id,
                view_key=view_key,
                label=f"{cluster['location_label']} · A{per_location_index[location_id]:02d}",
                view_type="location_camera",
                state_key="default",
                view_spec=_dump(spec),
                status="missing",
                sort_order=current_max + 1,
            )
            session.add(view)
            pack.status = "review" if pack.status == "approved" else pack.status
            await session.flush()
            created += 1
        else:
            previous_spec = json_object(view.view_spec, {})
            previous_visual_contract = {
                key: previous_spec.get(key)
                for key in ("location", "camera", "clean_plate", "source")
            }
            next_visual_contract = {
                key: spec.get(key)
                for key in ("location", "camera", "clean_plate", "source")
            }
            if previous_visual_contract != next_visual_contract and view.approved_revision_id:
                view.status = "stale"
                pack.status = "review"
                stale += 1
            view.view_spec = _dump(spec)
            view.updated_at = datetime.utcnow()
            updated += 1
        seen_view_ids.add(int(view.id))

    for view in existing_blocking_views:
        if int(view.id) in seen_view_ids:
            continue
        spec = json_object(view.view_spec, {})
        spec["used_by_shots"] = []
        spec["shot_numbers"] = []
        spec["orphaned"] = True
        view.view_spec = _dump(spec)
        if view.approved_revision_id:
            view.status = "stale"
        else:
            view.status = "missing"
        view.updated_at = datetime.utcnow()
        pack = next((candidate for candidate in location_packs if candidate.id == view.pack_id), None)
        if pack is not None:
            pack.status = "review"
        stale += 1
    await session.flush()
    return {"clusters": len(clusters), "created": created, "updated": updated, "stale": stale}


async def create_composition(
    session: AsyncSession,
    *,
    project_id: int,
    location_view_id: int,
    name: str | None,
    prompt_delta: str | None,
    placement_guide_media_id: int | None,
    items: Iterable[dict[str, Any]],
) -> ProjectComposition:
    location_view = await get_view(session, project_id=project_id, view_id=location_view_id)
    location_pack = await get_pack(session, project_id=project_id, pack_id=location_view.pack_id)
    if location_pack.pack_type != "location" or not location_view.approved_revision_id:
        raise ReferenceServiceError("Composition requires an approved location view")

    normalized_items: list[dict[str, Any]] = []
    for index, raw in enumerate(items):
        element_id = int(raw.get("project_element_id") or 0)
        view_id = int(raw.get("reference_view_id") or 0)
        element = await session.scalar(
            select(ProjectElement).where(
                ProjectElement.id == element_id,
                ProjectElement.project_id == project_id,
                ProjectElement.deleted_at.is_(None),
            )
        )
        view = await get_view(session, project_id=project_id, view_id=view_id)
        pack = await get_pack(session, project_id=project_id, pack_id=view.pack_id)
        if element is None or pack.project_element_id != element.id:
            raise ReferenceServiceError("Composition item view does not belong to its element")
        if pack.pack_type not in {"prop", "character"} or not view.approved_revision_id:
            raise ReferenceServiceError("Composition items require approved prop/character views")
        state_id = int(raw["state_id"]) if raw.get("state_id") else None
        if state_id:
            state = await session.get(ProjectElementState, state_id)
            if state is None or state.deleted_at is not None or state.project_element_id != element.id:
                raise ReferenceServiceError("Composition item state does not belong to its element")
        normalized_items.append({
            "project_element_id": element.id,
            "reference_view_id": view.id,
            "source_revision_id": int(view.approved_revision_id),
            "state_id": state_id,
            "role": raw.get("role") or ("prop" if pack.pack_type == "prop" else "character"),
            "placement": raw.get("placement") or {},
            "item_order": index,
        })
    if not normalized_items:
        raise ReferenceServiceError("Add at least one approved prop or character")

    signature_payload = {
        "location_view_id": location_view.id,
        "base_location_revision_id": int(location_view.approved_revision_id),
        "items": normalized_items,
        "prompt_delta": (prompt_delta or "").strip(),
        "placement_guide_media_id": placement_guide_media_id,
        "version": 1,
    }
    source_signature = _signature(signature_payload)
    existing = await session.scalar(
        select(ProjectComposition).where(
            ProjectComposition.project_id == project_id,
            ProjectComposition.source_signature == source_signature,
            ProjectComposition.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return existing

    composition = ProjectComposition(
        project_id=project_id,
        name=(name or "").strip() or f"{location_view.label} · composition",
        location_view_id=location_view.id,
        base_location_revision_id=int(location_view.approved_revision_id),
        placement_guide_media_id=placement_guide_media_id,
        prompt_delta=(prompt_delta or "").strip() or None,
        source_signature=source_signature,
        status="draft",
    )
    session.add(composition)
    await session.flush()
    for item in normalized_items:
        session.add(ProjectCompositionItem(
            composition_id=composition.id,
            project_element_id=item["project_element_id"],
            reference_view_id=item["reference_view_id"],
            source_revision_id=item["source_revision_id"],
            state_id=item["state_id"],
            role=item["role"],
            placement=_dump(item["placement"]),
            item_order=item["item_order"],
        ))
    await session.flush()
    return composition


async def get_composition(
    session: AsyncSession,
    *,
    project_id: int,
    composition_id: int,
) -> ProjectComposition:
    composition = await session.scalar(
        select(ProjectComposition).where(
            ProjectComposition.id == composition_id,
            ProjectComposition.project_id == project_id,
            ProjectComposition.deleted_at.is_(None),
        )
    )
    if composition is None:
        raise ReferenceServiceError("Composition not found")
    return composition


async def soft_delete_composition(
    session: AsyncSession,
    composition: ProjectComposition,
) -> None:
    now = datetime.utcnow()
    composition.deleted_at = now
    composition.updated_at = now
    items = await session.scalars(
        select(ProjectCompositionItem).where(
            ProjectCompositionItem.composition_id == composition.id,
            ProjectCompositionItem.deleted_at.is_(None),
        )
    )
    for item in items:
        item.deleted_at = now
        item.updated_at = now
    await session.flush()
