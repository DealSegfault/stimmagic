"""Direction API, nested under the canonical Project resource."""
from __future__ import annotations

import asyncio
import json
from io import BytesIO
from pathlib import Path
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db_session
from database import Board, Chat, GenerationJob, MediaItem, ProjectDirectionEvent, ProjectScene
from project_service import get_project_or_404
from project_direction_service import (
    _sync_scene_chat_contexts,
    direction_payload,
    reconcile_script,
    record_event,
    scene_dict,
)
from utils.websocket import ws_manager

router = APIRouter(prefix="/api/projects/{project_id}/direction", tags=["project-direction"])

VIDEO_FORMATS = {"mp4", "webm", "mov", "avi", "mkv", "ogg"}


class ScriptImportRequest(BaseModel):
    script: str = Field(min_length=1, max_length=2_000_000)
    script_name: Optional[str] = Field(default=None, max_length=255)
    summary: Optional[str] = Field(default=None, max_length=20_000)
    context: dict[str, Any] = Field(default_factory=dict)


class SceneUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    context: Optional[dict[str, Any]] = None
    dependencies: Optional[list[Any]] = None
    blockers: Optional[list[Any]] = None
    status: Optional[str] = None
    validation_status: Optional[str] = None


def _direction_scene_job_filter(project_id: int, scene_id: int):
    event_job_ids = select(ProjectDirectionEvent.generation_job_id).where(
        ProjectDirectionEvent.project_id == project_id,
        ProjectDirectionEvent.scene_id == scene_id,
        ProjectDirectionEvent.generation_job_id.is_not(None),
    )
    return or_(
        (GenerationJob.project_id == project_id)
        & (func.json_extract(GenerationJob.parameters, '$._direction_scene_id') == scene_id),
        GenerationJob.id.in_(event_job_ids),
    )


async def _latest_scene_generation(
    session: AsyncSession,
    project_id: int,
    scene_id: int,
):
    result = await session.execute(
        select(GenerationJob, MediaItem)
        .outerjoin(MediaItem, GenerationJob.result_media_id == MediaItem.id)
        .where(
            GenerationJob.status == "completed",
            GenerationJob.result_media_id.is_not(None),
            func.json_extract(GenerationJob.parameters, '$._ephemeral_run_id').is_(None),
            _direction_scene_job_filter(project_id, scene_id),
            MediaItem.deleted_at.is_(None),
            MediaItem.file_unavailable.is_(False) | MediaItem.file_unavailable.is_(None),
        )
        .order_by(GenerationJob.completed_at.desc(), GenerationJob.created_at.desc(), GenerationJob.id.desc())
        .limit(1)
    )
    return result.first()


async def _scene_continuity_payload(session: AsyncSession, scene: ProjectScene) -> dict[str, Any]:
    ordered_scenes = (
        await session.execute(
            select(ProjectScene)
            .where(ProjectScene.project_id == scene.project_id)
            .order_by(ProjectScene.sequence_number.asc(), ProjectScene.scene_number.asc(), ProjectScene.id.asc())
        )
    ).scalars().all()
    try:
        previous_scene = next(
            ordered_scenes[index - 1]
            for index, candidate in enumerate(ordered_scenes)
            if candidate.id == scene.id and index > 0
        )
    except StopIteration:
        previous_scene = None

    if previous_scene is None:
        return {"previous_scene": None, "last_frame": None}

    generation_row = await _latest_scene_generation(session, scene.project_id, previous_scene.id)
    if not generation_row:
        return {
            "previous_scene": {
                "id": previous_scene.id,
                "scene_number": previous_scene.scene_number,
                "title": previous_scene.title,
            },
            "last_frame": None,
        }

    job, media = generation_row
    is_video = (media.file_format or "").lower() in VIDEO_FORMATS
    frame_url = f"/projects/{scene.project_id}/direction/scenes/{scene.id}/last-frame"
    return {
        "previous_scene": {
            "id": previous_scene.id,
            "scene_number": previous_scene.scene_number,
            "title": previous_scene.title,
        },
        "last_frame": {
            "media_id": media.id,
            "file_hash": media.file_hash,
            "file_format": media.file_format,
            "is_video": is_video,
            "generation_id": job.id,
            "frame_url": frame_url,
            "extracted": is_video,
        },
    }


@router.get("")
async def get_direction(project_id: int, session: AsyncSession = Depends(get_db_session)):
    await get_project_or_404(session, project_id)
    return await direction_payload(session, project_id)


@router.post("/import")
async def import_project_script(project_id: int, request: ScriptImportRequest, session: AsyncSession = Depends(get_db_session)):
    await get_project_or_404(session, project_id)
    try:
        payload, change = await reconcile_script(
            session,
            project_id,
            request.script,
            request.script_name,
            request.summary,
            request.context,
            actor="user",
            event_kind="script_imported",
        )
        await session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await ws_manager.broadcast("project_direction_updated", {"project_id": project_id, **change})
    return payload


@router.put("/script")
async def update_project_script(project_id: int, request: ScriptImportRequest, session: AsyncSession = Depends(get_db_session)):
    """Replace the canonical script and update every derived Direction record."""
    await get_project_or_404(session, project_id)
    try:
        payload, change = await reconcile_script(
            session,
            project_id,
            request.script,
            request.script_name,
            request.summary,
            request.context,
            actor="user",
            event_kind="script_updated",
        )
        await session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await ws_manager.broadcast("project_direction_updated", {"project_id": project_id, **change})
    return payload


@router.patch("/scenes/{scene_id}")
async def update_scene(project_id: int, scene_id: int, request: SceneUpdateRequest, session: AsyncSession = Depends(get_db_session)):
    scene = await session.scalar(select(ProjectScene).where(ProjectScene.id == scene_id, ProjectScene.project_id == project_id))
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    changes = request.model_dump(exclude_none=True)
    for key in ("context", "dependencies", "blockers"):
        if key in changes: changes[key] = json.dumps(changes[key])
    for key, value in changes.items(): setattr(scene, key, value)
    if scene.board_id:
        board = await session.get(Board, scene.board_id)
        if board:
            board.updated_at = datetime.utcnow()
    await _sync_scene_chat_contexts(session, scene)
    scene.updated_at = datetime.utcnow()
    await record_event(session, project_id, "scene_updated", scene_id=scene.id, payload={k: v for k, v in request.model_dump(exclude_none=True).items()})
    await session.commit(); await session.refresh(scene)
    await ws_manager.broadcast("project_direction_updated", {
        "project_id": project_id,
        "scene_id": scene_id,
        "scene_ids": [scene_id],
        "board_ids": [scene.board_id] if scene.board_id else [],
    })
    return scene_dict(scene)


@router.get("/scenes/{scene_id}/generations")
async def list_scene_generations(project_id: int, scene_id: int, session: AsyncSession = Depends(get_db_session)):
    """Return the generation history explicitly attached to one direction scene."""
    scene = await session.scalar(
        select(ProjectScene).where(ProjectScene.id == scene_id, ProjectScene.project_id == project_id)
    )
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    event_job_ids = select(ProjectDirectionEvent.generation_job_id).where(
        ProjectDirectionEvent.project_id == project_id,
        ProjectDirectionEvent.scene_id == scene_id,
        ProjectDirectionEvent.generation_job_id.is_not(None),
    )
    result = await session.execute(
        select(GenerationJob, MediaItem)
        .outerjoin(MediaItem, GenerationJob.result_media_id == MediaItem.id)
        .where(
            func.json_extract(GenerationJob.parameters, '$._ephemeral_run_id').is_(None),
            or_(
                (GenerationJob.project_id == project_id)
                & (func.json_extract(GenerationJob.parameters, '$._direction_scene_id') == scene_id),
                GenerationJob.id.in_(event_job_ids),
            ),
        )
        .order_by(GenerationJob.created_at.desc(), GenerationJob.id.desc())
        .limit(100)
    )

    generations = []
    for job, media in result.all():
        try:
            parameters = json.loads(job.parameters or "{}")
        except (TypeError, json.JSONDecodeError):
            parameters = {}
        nested_parameters = parameters.get("parameters") if isinstance(parameters.get("parameters"), dict) else {}
        prompt = (
            parameters.get("prompt")
            or parameters.get("positive_prompt")
            or nested_parameters.get("prompt")
            or nested_parameters.get("positive_prompt")
            or ""
        )
        generations.append({
            "id": job.id,
            "status": job.status,
            "task_type": job.task_type,
            "generator_name": job.generator_name,
            "model_name": job.model_name,
            "prompt": prompt,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "result_media_id": job.result_media_id,
            "result_file_hash": media.file_hash if media else None,
            "result_file_format": media.file_format if media else None,
            "media_deleted": bool(media and media.deleted_at),
            "error": job.error,
        })
    return {"generations": generations, "count": len(generations)}


@router.get("/scenes/{scene_id}/continuity")
async def get_scene_continuity(project_id: int, scene_id: int, session: AsyncSession = Depends(get_db_session)):
    """Return the previous scene and its automatically derived last-frame context."""
    scene = await session.scalar(
        select(ProjectScene).where(ProjectScene.id == scene_id, ProjectScene.project_id == project_id)
    )
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    return await _scene_continuity_payload(session, scene)


@router.get("/scenes/{scene_id}/last-frame")
async def get_scene_last_frame(project_id: int, scene_id: int, session: AsyncSession = Depends(get_db_session)):
    """Stream the last frame of the previous scene's latest completed result."""
    scene = await session.scalar(
        select(ProjectScene).where(ProjectScene.id == scene_id, ProjectScene.project_id == project_id)
    )
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    continuity = await _scene_continuity_payload(session, scene)
    frame = continuity.get("last_frame")
    if not frame:
        raise HTTPException(status_code=404, detail="No previous scene frame available")

    media = await session.get(MediaItem, frame["media_id"])
    if not media or media.deleted_at or media.file_unavailable or not media.file_path:
        raise HTTPException(status_code=404, detail="Previous scene media is unavailable")
    source_path = Path(media.file_path)
    if not source_path.exists() or not source_path.is_file():
        raise HTTPException(status_code=404, detail="Previous scene media file is unavailable")

    if not frame["is_video"]:
        media_type = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
            "gif": "image/gif",
        }.get((media.file_format or "").lower(), "application/octet-stream")
        return FileResponse(source_path, media_type=media_type, headers={"Cache-Control": "no-store"})

    from utils.video_frames import extract_frame_to_image

    try:
        image, _, _, _ = await asyncio.to_thread(extract_frame_to_image, source_path, "last")
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    buffer = BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=88)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/scenes/{scene_id}/chat")
async def create_scene_chat(project_id: int, scene_id: int, session: AsyncSession = Depends(get_db_session)):
    scene = await session.scalar(select(ProjectScene).where(ProjectScene.id == scene_id, ProjectScene.project_id == project_id))
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    continuity = await _scene_continuity_payload(session, scene)

    existing_event = await session.scalar(
        select(ProjectDirectionEvent)
        .where(
            ProjectDirectionEvent.project_id == project_id,
            ProjectDirectionEvent.scene_id == scene.id,
            ProjectDirectionEvent.chat_id.is_not(None),
            ProjectDirectionEvent.kind == "scene_chat_created",
        )
        .order_by(ProjectDirectionEvent.created_at.desc(), ProjectDirectionEvent.id.desc())
    )
    if existing_event and existing_event.chat_id:
        existing_chat = await session.get(Chat, existing_event.chat_id)
        if existing_chat and existing_chat.deleted_at is None:
            marker = "DIRECTION_CONTEXT="
            raw_instructions = existing_chat.additional_instructions or ""
            if marker in raw_instructions:
                try:
                    existing_context = json.loads(raw_instructions.split(marker, 1)[1])
                    existing_context["continuity"] = continuity
                    existing_chat.additional_instructions = raw_instructions.split(marker, 1)[0] + marker + json.dumps(existing_context)
                    await session.commit()
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass
            return {"chat_id": existing_chat.id, "scene_id": scene.id, "name": existing_chat.name, "reused": True}

    context = {
        "scene_id": scene.id,
        "sequence": scene.sequence_number,
        "scene": scene.scene_number,
        "title": scene.title,
        "description": scene.description or "",
        "prompt": scene.prompt,
        "board_id": scene.board_id,
        "dependencies": json.loads(scene.dependencies or "[]"),
        "blockers": json.loads(scene.blockers or "[]"),
        "status": scene.status,
        "validation_status": scene.validation_status,
        "continuity": continuity,
    }
    chat = Chat(name=f"Direction · {scene.title}", project_id=project_id, board_id=scene.board_id, additional_instructions="You are working on this exact project scene. Keep decisions, generations and validations tied to it.\n\nDIRECTION_CONTEXT=" + json.dumps(context))
    session.add(chat); await session.flush()
    await record_event(session, project_id, "scene_chat_created", scene_id=scene.id, chat_id=chat.id, payload=context)
    await session.commit()
    return {"chat_id": chat.id, "scene_id": scene.id}
