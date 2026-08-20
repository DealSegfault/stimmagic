"""Shot-level continuity contracts and acceptance records.

Scene rows describe a whole scene; production decisions happen at shot level.
This module keeps that boundary explicit and stores accepted shot outputs in
the existing append-only Direction event stream so the mechanism works for
every project without a Maya-specific schema.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    Asset,
    AssetMarker,
    AssetRevision,
    GenerationJob,
    Marker,
    MediaItem,
    ProjectDirectionEvent,
    ProjectScene,
    ProjectShot,
)


VIDEO_FORMATS = {"mp4", "webm", "mov", "avi", "mkv", "ogg"}
_DURATION_RE = re.compile(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(?:s|sec|secs|second|seconds|seconde|secondes)\b", re.I)


def parse_shot_duration(value: Any) -> float | None:
    """Parse the duration cell from a script row."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    match = _DURATION_RE.search(str(value or ""))
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _event_payload(event: ProjectDirectionEvent) -> dict[str, Any]:
    try:
        value = json.loads(event.payload or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        value = {}
    return value if isinstance(value, dict) else {}


async def latest_shot_acceptance(
    session: AsyncSession,
    *,
    project_id: int,
    scene_id: int,
    shot_number: int,
) -> dict[str, Any] | None:
    """Return the latest accepted output for one exact shot coordinate."""
    canonical = await session.scalar(
        select(ProjectShot).where(
            ProjectShot.project_id == project_id,
            ProjectShot.scene_id == scene_id,
            ProjectShot.shot_number == shot_number,
            ProjectShot.deleted_at.is_(None),
            ProjectShot.accepted_media_id.is_not(None),
        )
    )
    if canonical is not None:
        return {
            "project_id": project_id,
            "scene_id": scene_id,
            "shot_number": shot_number,
            "media_id": canonical.accepted_media_id,
            "last_frame_media_id": canonical.accepted_last_frame_media_id or canonical.accepted_media_id,
            "accepted_at": canonical.updated_at.isoformat() if canonical.updated_at else None,
            "canonical_shot_id": canonical.id,
        }
    result = await session.execute(
        select(ProjectDirectionEvent)
        .where(
            ProjectDirectionEvent.project_id == project_id,
            ProjectDirectionEvent.scene_id == scene_id,
            ProjectDirectionEvent.kind == "shot_accepted",
        )
        .order_by(desc(ProjectDirectionEvent.created_at), desc(ProjectDirectionEvent.id))
    )
    for event in result.scalars().all():
        payload = _event_payload(event)
        if payload.get("shot_number") != shot_number:
            continue
        return {
            **payload,
            "event_id": event.id,
            "accepted_at": event.created_at.isoformat() if event.created_at else None,
        }
    return None


async def latest_previous_shot_acceptance(
    session: AsyncSession,
    *,
    project_id: int,
    scene_id: int,
    shot_number: int,
) -> dict[str, Any] | None:
    current_shot = await session.scalar(
        select(ProjectShot).where(
            ProjectShot.project_id == project_id,
            ProjectShot.scene_id == scene_id,
            ProjectShot.shot_number == shot_number,
            ProjectShot.deleted_at.is_(None),
        )
    )
    if current_shot is None:
        return None
    ordered_shots = (await session.execute(
        select(ProjectShot)
        .join(ProjectScene, ProjectScene.id == ProjectShot.scene_id)
        .where(
            ProjectShot.project_id == project_id,
            ProjectShot.deleted_at.is_(None),
            ProjectScene.project_id == project_id,
        )
        .order_by(
            ProjectScene.sequence_number,
            ProjectScene.scene_number,
            ProjectShot.shot_number,
            ProjectShot.id,
        )
    )).scalars().all()
    current_index = next(
        (index for index, shot in enumerate(ordered_shots) if shot.id == current_shot.id),
        None,
    )
    if current_index is None or current_index == 0:
        return None
    previous_shot = ordered_shots[current_index - 1]
    return await latest_shot_acceptance(
        session,
        project_id=project_id,
        scene_id=previous_shot.scene_id,
        shot_number=previous_shot.shot_number,
    )


def build_shot_generation_contract(
    *,
    project_id: int,
    scene: dict[str, Any],
    shot_context: dict[str, Any],
    reference_manifest: list[dict[str, Any]],
    previous_acceptance: dict[str, Any] | None,
) -> dict[str, Any]:
    """Create the machine-readable contract passed from World State to tools."""
    current = shot_context.get("current") or {}
    duration = parse_shot_duration(current.get("duration"))
    context = scene.get("context") if isinstance(scene.get("context"), dict) else {}
    generation = context.get("generation") if isinstance(context.get("generation"), dict) else {}
    dimensions = current.get("dimensions") or generation.get("dimensions") or context.get("dimensions")
    if not dimensions and current.get("width") and current.get("height"):
        dimensions = [current["width"], current["height"]]
    if not (
        isinstance(dimensions, (list, tuple))
        and len(dimensions) == 2
        and all(isinstance(value, (int, float)) for value in dimensions)
    ):
        # The product's canonical landscape video canvas. Projects can override
        # it through scene.context.generation.dimensions without code changes.
        dimensions = [1344, 768]

    previous_frame_id = (previous_acceptance or {}).get("last_frame_media_id")
    allowed_ids = [item.get("media_id") for item in reference_manifest if item.get("media_id")]
    previous_row = shot_context.get("previous") or {}
    workflow = "direct_reference_to_video"
    if bool(current.get("requires_keyframe_composition")) or bool(shot_context.get("requires_keyframe_composition")):
        workflow = "compose_opening_keyframe_then_i2v"
    return {
        "version": 1,
        "project_id": project_id,
        "scene_id": scene.get("id"),
        "sequence_number": scene.get("sequence_number"),
        "scene_number": scene.get("scene_number"),
        "shot_id": current.get("id"),
        "shot_number": shot_context.get("shot_number"),
        "expected_duration": duration,
        "expected_dimensions": [int(dimensions[0]), int(dimensions[1])],
        "reference_manifest": reference_manifest,
        "allowed_reference_media_ids": list(dict.fromkeys(int(value) for value in allowed_ids)),
        "previous_accepted": previous_acceptance,
        "previous_last_frame_media_id": previous_frame_id,
        "requires_previous_last_frame": (
            current.get("transition_policy", "continuity") != "independent"
            and bool(shot_context.get("previous"))
            and shot_context.get("shot_number", 1) > 1
        ),
        "current_script_row": current,
        "previous_script_row": shot_context.get("previous"),
        "workflow": workflow,
    }


def validate_generation_request(
    contract: dict[str, Any] | None,
    *,
    task_type: str,
    final_params: dict[str, Any],
    input_media_ids: list[int],
    session_media_ids: list[int] | None = None,
) -> list[str]:
    """Return hard preflight errors; an empty list means the job may launch."""
    if not contract:
        return []

    errors: list[str] = []
    workflow = contract.get("workflow")
    task_name = str(task_type).lower()
    is_video = "video" in task_name
    is_image_composition = (
        workflow == "compose_opening_keyframe_then_i2v"
        and not is_video
        and any(token in task_name for token in ("image-to-image", "image-edit", "inpaint", "text-to-image"))
    )
    if not is_video and not is_image_composition:
        return []

    current_run_ids = {int(value) for value in session_media_ids or []}
    if workflow == "compose_opening_keyframe_then_i2v":
        if "reference-to-video" in task_name or "ref2va" in task_name:
            manifest_ids = [
                int(value)
                for value in contract.get("allowed_reference_media_ids") or []
            ]
            errors.append(
                "workflow mismatch: this shot requires a composed opening keyframe followed by I2V, not direct multi-reference R2V. "
                f"First run image-to-image with input_images={manifest_ids}, then run I2V with only the returned keyframe.media_id."
            )
        elif "image-to-video" in task_name:
            opening_keyframe_id = contract.get("opening_keyframe_media_id")
            if not opening_keyframe_id:
                errors.append(
                    "workflow mismatch: the composed shot has no bound opening_keyframe_media_id; "
                    "the image edit must succeed and bind its returned media before I2V"
                )
            elif len(input_media_ids) != 1 or int(input_media_ids[0]) != int(opening_keyframe_id):
                errors.append(
                    "workflow mismatch: I2V must receive exactly the bound opening keyframe "
                    f"media {int(opening_keyframe_id)}; received {input_media_ids or 'no media references'}"
                )
            elif int(opening_keyframe_id) not in current_run_ids:
                errors.append(
                    "workflow mismatch: the bound opening keyframe is not present in the current run; "
                    "do not reuse a stale keyframe from another run"
                )
        elif is_image_composition:
            previous_frame_id = contract.get("previous_last_frame_media_id")
            if not previous_frame_id:
                errors.append(
                    "workflow mismatch: the opening keyframe must be composed from the previous accepted last frame"
                )
            elif int(previous_frame_id) not in set(input_media_ids):
                errors.append(
                    f"opening keyframe must include previous last-frame media {previous_frame_id}, "
                    f"received {input_media_ids or 'no media references'}"
                )
    if is_video:
        expected_duration = contract.get("expected_duration")
        actual_duration = final_params.get("duration")
        if expected_duration is not None and actual_duration is not None:
            if abs(float(actual_duration) - float(expected_duration)) > 0.26:
                errors.append(
                    f"duration mismatch: shot {contract.get('shot_number')} requires "
                    f"{expected_duration:g}s, request is {actual_duration:g}s"
                )

        expected_dimensions = contract.get("expected_dimensions") or []
        if len(expected_dimensions) == 2:
            actual_dimensions = (final_params.get("width"), final_params.get("height"))
            if all(value is not None for value in actual_dimensions):
                if [int(actual_dimensions[0]), int(actual_dimensions[1])] != [int(expected_dimensions[0]), int(expected_dimensions[1])]:
                    errors.append(
                        f"dimensions mismatch: shot requires {expected_dimensions[0]}x{expected_dimensions[1]}, "
                        f"request is {actual_dimensions[0]}x{actual_dimensions[1]}"
                    )

    previous_frame_id = contract.get("previous_last_frame_media_id")
    if contract.get("requires_previous_last_frame") and not previous_frame_id:
        errors.append(
            "missing continuity anchor: the previous accepted shot has no materialized last frame"
        )
    if previous_frame_id and int(previous_frame_id) not in set(input_media_ids):
        # A composed opening keyframe generated earlier in this same run is a
        # valid carrier for the previous frame; the image edit must have
        # consumed the anchor before the I2V call. A stale library image is not.
        is_current_run_keyframe = (
            is_video
            and "image-to-video" in str(task_type).lower()
            and bool(set(input_media_ids) & current_run_ids)
        )
        if not is_current_run_keyframe:
            errors.append(
                f"wrong continuity anchor: required previous last-frame media {previous_frame_id}, "
                f"received {input_media_ids or 'no media references'}"
            )

    allowed_ids = {int(value) for value in contract.get("allowed_reference_media_ids") or []}
    unexpected = [value for value in input_media_ids if value not in allowed_ids and value not in current_run_ids]
    if unexpected:
        errors.append(
            "references outside the resolved shot manifest: "
            + ", ".join(str(value) for value in unexpected)
        )
    return errors


async def validate_shot_output(
    session: AsyncSession,
    *,
    contract: dict[str, Any] | None,
    media_id: int,
) -> list[str]:
    """Validate hard media metadata before a final output is accepted."""
    if not contract:
        return []
    media = await session.get(MediaItem, media_id)
    if not media:
        return [f"output media {media_id} is unavailable"]
    errors: list[str] = []
    expected_dimensions = contract.get("expected_dimensions") or []
    if len(expected_dimensions) == 2 and [media.width, media.height] != [int(expected_dimensions[0]), int(expected_dimensions[1])]:
        errors.append(
            f"output dimensions mismatch: expected {expected_dimensions[0]}x{expected_dimensions[1]}, "
            f"got {media.width}x{media.height}"
        )
    expected_duration = contract.get("expected_duration")
    if expected_duration is not None and media.duration is not None and abs(float(media.duration) - float(expected_duration)) > 0.26:
        errors.append(
            f"output duration mismatch: expected {expected_duration:g}s, got {float(media.duration):.2f}s"
        )
    return errors


async def record_shot_acceptance(
    session: AsyncSession,
    *,
    contract: dict[str, Any],
    media_id: int,
    generation_job_id: int | None = None,
    last_frame_media_id: int | None = None,
) -> None:
    """Update the canonical shot and retain an audit event for compatibility."""
    shot = None
    if contract.get("shot_id"):
        shot = await session.scalar(
            select(ProjectShot).where(
                ProjectShot.id == int(contract["shot_id"]),
                ProjectShot.project_id == int(contract["project_id"]),
                ProjectShot.deleted_at.is_(None),
            )
        )
    if shot is None and contract.get("scene_id") is not None and contract.get("shot_number") is not None:
        shot = await session.scalar(
            select(ProjectShot).where(
                ProjectShot.project_id == int(contract["project_id"]),
                ProjectShot.scene_id == int(contract["scene_id"]),
                ProjectShot.shot_number == int(contract["shot_number"]),
                ProjectShot.deleted_at.is_(None),
            )
        )
    if shot is not None:
        shot.accepted_media_id = int(media_id)
        shot.accepted_last_frame_media_id = int(last_frame_media_id or media_id)
        shot.status = "complete"
        shot.validation_status = "approved"
        shot.revision += 1
        shot.updated_at = datetime.utcnow()
    payload = {
        "project_id": contract.get("project_id"),
        "scene_id": contract.get("scene_id"),
        "sequence_number": contract.get("sequence_number"),
        "scene_number": contract.get("scene_number"),
        "shot_number": contract.get("shot_number"),
        "media_id": media_id,
        "last_frame_media_id": last_frame_media_id or media_id,
        "generation_job_id": generation_job_id,
        "reference_manifest": contract.get("reference_manifest") or [],
        "accepted_at": datetime.utcnow().isoformat(),
    }
    existing = await session.scalar(
        select(ProjectDirectionEvent).where(
            ProjectDirectionEvent.project_id == int(contract["project_id"]),
            ProjectDirectionEvent.scene_id == contract.get("scene_id"),
            ProjectDirectionEvent.kind == "shot_accepted",
            ProjectDirectionEvent.generation_job_id == generation_job_id,
        ).limit(1)
    ) if generation_job_id is not None else None
    if existing is None:
        session.add(ProjectDirectionEvent(
            project_id=int(contract["project_id"]),
            scene_id=contract.get("scene_id"),
            generation_job_id=generation_job_id,
            kind="shot_accepted",
            actor="agent",
            payload=json.dumps(payload),
        ))
    await session.commit()


async def generation_job_for_media(session: AsyncSession, media_id: int) -> GenerationJob | None:
    return await session.scalar(
        select(GenerationJob)
        .where(GenerationJob.result_media_id == media_id)
        .order_by(desc(GenerationJob.completed_at), desc(GenerationJob.id))
        .limit(1)
    )


async def list_shot_generation_candidates(
    session: AsyncSession,
    *,
    project_id: int,
    scene_id: int,
    shot_number: int,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Return recent completed outputs that carry an exact shot contract."""
    shot_path = "$.prompt_metadata.shot_contract.shot_number"
    scene_path = "$.prompt_metadata.shot_contract.scene_id"
    direction_scene_path = "$._direction_scene_id"
    exact_filter = [
        GenerationJob.project_id == project_id,
        GenerationJob.status == "completed",
        GenerationJob.result_media_id.is_not(None),
        func.json_extract(GenerationJob.parameters, '$._ephemeral_run_id').is_(None),
        func.json_extract(GenerationJob.parameters, shot_path) == int(shot_number),
        or_(
            func.json_extract(GenerationJob.parameters, scene_path) == int(scene_id),
            func.json_extract(GenerationJob.parameters, direction_scene_path) == int(scene_id),
        ),
    ]
    result = await session.execute(
        select(GenerationJob, MediaItem)
        .outerjoin(MediaItem, GenerationJob.result_media_id == MediaItem.id)
        .where(*exact_filter)
        .order_by(GenerationJob.completed_at.desc(), GenerationJob.created_at.desc(), GenerationJob.id.desc())
        .limit(max(1, min(int(limit), 20)))
    )
    rows = result.all()
    match_confidence = "exact_shot"
    if not rows:
        # Older jobs may predate shot_contract.scene_id/shot_number metadata.
        # Keep the answer useful without pretending those scene-level outputs
        # are an exact match; the agent can present them as review candidates.
        result = await session.execute(
            select(GenerationJob, MediaItem)
            .outerjoin(MediaItem, GenerationJob.result_media_id == MediaItem.id)
            .where(
                GenerationJob.project_id == project_id,
                GenerationJob.status == "completed",
                GenerationJob.result_media_id.is_not(None),
                func.json_extract(GenerationJob.parameters, '$._ephemeral_run_id').is_(None),
                func.json_extract(GenerationJob.parameters, direction_scene_path) == int(scene_id),
            )
            .order_by(GenerationJob.completed_at.desc(), GenerationJob.created_at.desc(), GenerationJob.id.desc())
            .limit(max(1, min(int(limit), 20)))
        )
        rows = result.all()
        match_confidence = "scene_recent"
    if not rows:
        return []

    media_ids = [int(media.id) for _, media in rows if media is not None]
    revision_rows = (await session.execute(
        select(AssetRevision.primary_media_id, Asset.id)
        .join(Asset, Asset.id == AssetRevision.asset_id)
        .where(AssetRevision.primary_media_id.in_(media_ids), AssetRevision.deleted_at.is_(None))
    )).all() if media_ids else []
    asset_by_media = {int(media_id): int(asset_id) for media_id, asset_id in revision_rows}
    asset_ids = list(asset_by_media.values())
    favorite_asset_ids: set[int] = set()
    if asset_ids:
        marker_rows = (await session.execute(
            select(AssetMarker.asset_id)
            .join(Marker, Marker.id == AssetMarker.marker_id)
            .where(
                AssetMarker.asset_id.in_(asset_ids),
                AssetMarker.deleted_at.is_(None),
                func.lower(Marker.name).in_(("favorite", "like", "liked")),
            )
        )).all()
        favorite_asset_ids = {int(row[0]) for row in marker_rows}

    accepted = await latest_shot_acceptance(
        session, project_id=project_id, scene_id=scene_id, shot_number=shot_number
    )
    accepted_media_id = int(accepted["media_id"]) if accepted and accepted.get("media_id") else None
    accepted_last_frame_id = int(accepted["last_frame_media_id"]) if accepted and accepted.get("last_frame_media_id") else None
    candidates: list[dict[str, Any]] = []
    for job, media in rows:
        if media is None:
            continue
        media_id = int(media.id)
        asset_id = asset_by_media.get(media_id)
        candidates.append({
            "index": len(candidates) + 1,
            "job_id": int(job.id),
            "media_id": media_id,
            "asset_id": asset_id,
            "task_type": job.task_type,
            "status": job.status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "file_format": media.file_format,
            "is_favorite": bool(asset_id and asset_id in favorite_asset_ids),
            "is_accepted": media_id == accepted_media_id,
            "last_frame_media_id": accepted_last_frame_id if media_id == accepted_media_id else None,
            "media_deleted": bool(media.deleted_at),
            "match_confidence": match_confidence,
        })
    return candidates


async def ensure_last_frame_media(
    session: AsyncSession,
    *,
    source_media_id: int,
    workspace_dir: str | Path | None,
    project_id: int | None,
) -> int:
    """Return an image media id for a source image/video's final frame."""
    source = await session.get(MediaItem, int(source_media_id))
    if not source or not source.file_path:
        raise ValueError(f"Media {source_media_id} is unavailable")
    if (source.file_format or "").lower() not in VIDEO_FORMATS:
        return int(source_media_id)
    if workspace_dir is None:
        raise ValueError("A workspace is required to materialize a video last frame")

    from utils.video_frames import extract_frame_to_image
    from agent.v2.tools.library import save_workspace_file

    image, _, _, _ = await __import__("asyncio").to_thread(
        extract_frame_to_image, source.file_path, "last"
    )
    workspace = Path(workspace_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    frame_path = workspace / f"continuity_last_frame_media_{source_media_id}.png"
    image.convert("RGB").save(frame_path, "PNG")
    raw = await save_workspace_file(
        session=session,
        path=str(frame_path),
        workspace_dir=workspace,
        save_tags=["continuity:last-frame"],
        provenance={
            "task_type": "frame-extraction",
            "tool_id": "stimma:extract-last-frame",
            "source_media_ids": [int(source_media_id)],
        },
        project_id=project_id,
        materialize_asset=False,
    )
    try:
        payload = json.loads(raw)
        return int(payload["media_id"])
    except (TypeError, ValueError, json.JSONDecodeError, KeyError) as exc:
        raise RuntimeError(f"Could not save continuity last frame: {raw}") from exc


async def resolve_contract_last_frame(
    session: AsyncSession,
    *,
    contract: dict[str, Any],
    workspace_dir: str | Path | None,
) -> int | None:
    """Materialize and update the contract's previous-shot anchor in place."""
    source_id = contract.get("previous_last_frame_media_id")
    if not source_id:
        return None
    resolved_id = await ensure_last_frame_media(
        session,
        source_media_id=int(source_id),
        workspace_dir=workspace_dir,
        project_id=contract.get("project_id"),
    )
    contract["previous_last_frame_media_id"] = resolved_id
    for item in contract.get("reference_manifest") or []:
        if item.get("role") == "continuity_anchor":
            item["media_id"] = resolved_id
    allowed = [
        int(item["media_id"])
        for item in contract.get("reference_manifest") or []
        if item.get("media_id")
    ]
    contract["allowed_reference_media_ids"] = list(dict.fromkeys(allowed))
    return resolved_id
