"""Canonical project production read/write helpers."""
from __future__ import annotations

import json
import unicodedata
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from blocking_service import build_blocking_view
from database import (
    AssetRevision,
    GenerationJob,
    MediaItem,
    ProjectDirection,
    ProjectElement,
    ProjectReferencePack,
    ProjectReferenceView,
    ProjectScene,
    ProjectShot,
    ShotAttempt,
)


def json_value(raw: str | None, fallback: Any) -> Any:
    try:
        value = json.loads(raw) if raw else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return value if isinstance(value, type(fallback)) else fallback


def _normalized_reference_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return normalized.encode("ascii", "ignore").decode("ascii").casefold()


def shot_dict(
    shot: ProjectShot,
    *,
    generation_count: int = 0,
    blocking: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "id": shot.id,
        "project_id": shot.project_id,
        "scene_id": shot.scene_id,
        "shot_number": shot.shot_number,
        "source_key": shot.source_key,
        "title": shot.title,
        "description": shot.description or "",
        "prompt": shot.prompt or "",
        "duration": shot.duration,
        "width": shot.width,
        "height": shot.height,
        "transition_policy": shot.transition_policy,
        "status": shot.status,
        "validation_status": shot.validation_status,
        "accepted_media_id": shot.accepted_media_id,
        "accepted_last_frame_media_id": shot.accepted_last_frame_media_id,
        "revision": shot.revision,
        "references": json_value(shot.references, []),
        "settings": json_value(shot.settings, {}),
        "generation_count": generation_count,
        "created_at": shot.created_at.isoformat() if shot.created_at else None,
        "updated_at": shot.updated_at.isoformat() if shot.updated_at else None,
    }
    if blocking is not None:
        payload["blocking"] = blocking
    return payload


def _job_matches_shot(job: GenerationJob, shot: ProjectShot) -> tuple[bool, str]:
    try:
        params = json.loads(job.parameters or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        params = {}
    metadata = params.get("prompt_metadata", {})
    contract = metadata.get("shot_contract", {}) if isinstance(metadata, dict) else {}
    if not isinstance(contract, dict):
        contract = {}
    if contract.get("shot_id") is not None and str(contract["shot_id"]) == str(shot.id):
        return True, "exact_shot"
    if (
        contract.get("scene_id") is not None
        and str(contract["scene_id"]) == str(shot.scene_id)
        and contract.get("shot_number") is not None
        and str(contract["shot_number"]) == str(shot.shot_number)
    ):
        return True, "exact_shot"
    try:
        if int(params.get("_direction_scene_id")) == int(shot.scene_id):
            return False, "scene_recent"
    except (TypeError, ValueError):
        pass
    return False, "unmatched"


async def list_shot_candidates(
    session: AsyncSession,
    shot: ProjectShot,
    *,
    limit: int = 20,
    include_scene_fallback: bool = True,
) -> list[dict[str, Any]]:
    result = await session.execute(
        select(GenerationJob, MediaItem)
        .outerjoin(MediaItem, GenerationJob.result_media_id == MediaItem.id)
        .where(
            GenerationJob.project_id == shot.project_id,
            GenerationJob.status == "completed",
            GenerationJob.result_media_id.is_not(None),
            func.json_extract(GenerationJob.parameters, '$._ephemeral_run_id').is_(None),
            MediaItem.deleted_at.is_(None),
        )
        .order_by(GenerationJob.completed_at.desc(), GenerationJob.created_at.desc(), GenerationJob.id.desc())
        .limit(max(1, min(int(limit) * 4, 100)))
    )
    exact: list[dict[str, Any]] = []
    fallback: list[dict[str, Any]] = []
    for job, media in result.all():
        if media is None:
            continue
        matches, confidence = _job_matches_shot(job, shot)
        if not matches and (confidence != "scene_recent" or not include_scene_fallback):
            continue
        row = {
            "job_id": job.id,
            "media_id": media.id,
            "file_format": media.file_format,
            "duration": media.duration,
            "width": media.width,
            "height": media.height,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "match_confidence": confidence,
            "approval_eligible": matches,
            "is_accepted": int(media.id) == int(shot.accepted_media_id or -1),
        }
        (exact if matches else fallback).append(row)
    return (exact + fallback)[: max(1, min(int(limit), 50))]


async def find_exact_shot_for_media(
    session: AsyncSession,
    *,
    project_id: int,
    media_id: int,
) -> dict[str, int] | None:
    """Resolve a chat candidate to its canonical shot without chat state."""
    jobs = (await session.execute(
        select(GenerationJob)
        .where(
            GenerationJob.project_id == project_id,
            GenerationJob.result_media_id == media_id,
            GenerationJob.status == "completed",
            func.json_extract(GenerationJob.parameters, '$._ephemeral_run_id').is_(None),
        )
        .order_by(GenerationJob.completed_at.desc(), GenerationJob.id.desc())
    )).scalars().all()
    if not jobs:
        return None
    shots = (await session.execute(
        select(ProjectShot)
        .where(ProjectShot.project_id == project_id, ProjectShot.deleted_at.is_(None))
        .order_by(ProjectShot.scene_id, ProjectShot.shot_number, ProjectShot.id)
    )).scalars().all()
    for job in jobs:
        for shot in shots:
            matches, confidence = _job_matches_shot(job, shot)
            if matches and confidence == "exact_shot":
                return {"shot_id": int(shot.id), "scene_id": int(shot.scene_id), "media_id": int(media_id)}
    return None


async def production_payload(session: AsyncSession, project_id: int) -> dict[str, Any]:
    direction = await session.get(ProjectDirection, project_id)
    direction_context = json_value(direction.context if direction else None, {})
    scenes = (
        await session.execute(
            select(ProjectScene)
            .where(ProjectScene.project_id == project_id)
            .order_by(ProjectScene.sequence_number, ProjectScene.scene_number, ProjectScene.id)
        )
    ).scalars().all()
    shots = (
        await session.execute(
            select(ProjectShot)
            .where(ProjectShot.project_id == project_id, ProjectShot.deleted_at.is_(None))
            .order_by(ProjectShot.scene_id, ProjectShot.shot_number, ProjectShot.id)
        )
    ).scalars().all()
    shots_by_scene: dict[int, list[ProjectShot]] = {}
    for shot in shots:
        shots_by_scene.setdefault(int(shot.scene_id), []).append(shot)
    reference_rows = (await session.execute(
        select(ProjectReferenceView, ProjectReferencePack, ProjectElement)
        .join(ProjectReferencePack, ProjectReferencePack.id == ProjectReferenceView.pack_id)
        .join(ProjectElement, ProjectElement.id == ProjectReferencePack.project_element_id)
        .where(
            ProjectReferenceView.project_id == project_id,
            ProjectReferenceView.deleted_at.is_(None),
            ProjectReferencePack.deleted_at.is_(None),
            ProjectElement.deleted_at.is_(None),
        )
        .order_by(ProjectReferenceView.sort_order, ProjectReferenceView.id)
    )).all()
    location_reference_by_shot: dict[int, dict[str, Any]] = {}
    prop_reference_rows: list[dict[str, Any]] = []
    for view, pack, element in reference_rows:
        approved_media_id = None
        if view.approved_revision_id:
            revision = await session.get(AssetRevision, view.approved_revision_id)
            approved_media_id = revision.primary_media_id if revision and revision.deleted_at is None else None
        row = {
            "pack_id": pack.id,
            "view_id": view.id,
            "view_key": view.view_key,
            "label": view.label,
            "status": view.status,
            "approved_revision_id": view.approved_revision_id,
            "approved_media_id": approved_media_id,
            "element_id": element.id,
            "reference_id": element.reference_id,
            "element_name": element.name,
            "sheet_asset_id": pack.sheet_asset_id,
        }
        if pack.pack_type == "location":
            for shot_id in json_value(view.view_spec, {}).get("used_by_shots", []):
                location_reference_by_shot[int(shot_id)] = row
        elif pack.pack_type == "prop":
            prop_reference_rows.append(row)
    sequences: list[dict[str, Any]] = []
    total_shots = 0
    accepted_shots = 0
    reviewed_blockings = 0
    reference_covered_shots = 0
    blocking_state: dict[str, Any] = {}
    for scene in scenes:
        scene_shots = shots_by_scene.get(int(scene.id), [])
        shot_rows: list[dict[str, Any]] = []
        for shot in scene_shots:
            count = await session.scalar(
                select(func.count(ShotAttempt.id)).where(ShotAttempt.shot_id == shot.id)
            )
            shot_settings = json_value(shot.settings, {})
            blocking = build_blocking_view(shot, scene, blocking_state, settings=shot_settings)
            location_reference = location_reference_by_shot.get(int(shot.id))
            if location_reference:
                blocking["location_reference"] = location_reference
                reference_covered_shots += int(bool(location_reference.get("approved_media_id")))
            for prop in blocking.get("props") or []:
                prop_text = _normalized_reference_text(
                    f"{prop.get('id', '')} {prop.get('label', '')}"
                )
                aliases = {
                    "kettle": ("kettle", "bouilloire"),
                    "cup": ("cup", "tasse", "mug"),
                    "phone": ("phone", "telephone"),
                    "knife": ("knife", "couteau"),
                    "chair": ("chair", "chaise"),
                    "file": ("file", "dossier"),
                }
                concepts = next(
                    (terms for key, terms in aliases.items() if key in prop_text),
                    tuple(prop_text.split()),
                )
                match = next(
                    (
                        item for item in prop_reference_rows
                        if any(
                            concept in _normalized_reference_text(
                                f"{item['reference_id']} {item['element_name']}"
                            )
                            for concept in concepts
                            if concept
                        )
                    ),
                    None,
                )
                if match:
                    prop["reference"] = match
            shot_rows.append(shot_dict(shot, generation_count=int(count or 0), blocking=blocking))
            total_shots += 1
            accepted_shots += int(shot.accepted_media_id is not None)
            reviewed_blockings += int(blocking.get("status") == "approved")
        sequences.append({
            "id": scene.id,
            "sequence_number": scene.sequence_number,
            "scene_number": scene.scene_number,
            "title": scene.title,
            "description": scene.description or "",
            "status": scene.status,
            "validation_status": scene.validation_status,
            "shots": shot_rows,
        })
    return {
        "project_id": project_id,
        "script_directives": direction_context.get("script_directives", ""),
        "sequences": sequences,
        "stats": {
            "sequence_count": len(sequences),
            "shot_count": total_shots,
            "accepted_count": accepted_shots,
            "pending_count": max(0, total_shots - accepted_shots),
            "blocking_count": total_shots,
            "blocking_reviewed_count": reviewed_blockings,
            "reference_covered_shot_count": reference_covered_shots,
        },
    }


async def ensure_project_shot(session: AsyncSession, shot_id: int, project_id: int) -> ProjectShot | None:
    return await session.scalar(
        select(ProjectShot).where(
            ProjectShot.id == shot_id,
            ProjectShot.project_id == project_id,
            ProjectShot.deleted_at.is_(None),
        )
    )


async def create_attempt(
    session: AsyncSession,
    *,
    shot: ProjectShot,
    generation_job_id: int | None,
    prompt: str | None,
    parameters: dict[str, Any] | None,
    reference_manifest: list[dict[str, Any]] | None,
    idempotency_key: str,
) -> ShotAttempt:
    existing = await session.scalar(select(ShotAttempt).where(ShotAttempt.idempotency_key == idempotency_key))
    if existing is not None:
        return existing
    last_number = await session.scalar(
        select(func.max(ShotAttempt.attempt_number)).where(ShotAttempt.shot_id == shot.id)
    )
    attempt = ShotAttempt(
        project_id=shot.project_id,
        shot_id=shot.id,
        attempt_number=int(last_number or 0) + 1,
        generation_job_id=generation_job_id,
        idempotency_key=idempotency_key,
        status="queued",
        prompt=prompt,
        parameters=json.dumps(parameters or {}, ensure_ascii=False),
        reference_manifest=json.dumps(reference_manifest or [], ensure_ascii=False),
    )
    session.add(attempt)
    await session.flush()
    return attempt
