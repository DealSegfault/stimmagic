"""Project Production API: explicit shots, candidates and approvals."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.v2.workspace import get_project_workspace
from core.dependencies import get_db_session
from database import GenerationJob, MediaItem
from project_service import get_project_or_404
from production_service import (
    ensure_project_shot,
    find_exact_shot_for_media,
    list_shot_candidates,
    production_payload,
    shot_dict,
)
from shot_continuity_service import ensure_last_frame_media
from utils.websocket import ws_manager

router = APIRouter(prefix="/api/projects/{project_id}/production", tags=["project-production"])


class ShotUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    prompt: str | None = None
    duration: float | None = Field(default=None, gt=0, le=60)
    width: int | None = Field(default=None, gt=0, le=8192)
    height: int | None = Field(default=None, gt=0, le=8192)
    transition_policy: str | None = Field(default=None, max_length=40)
    status: str | None = Field(default=None, max_length=40)
    validation_status: str | None = Field(default=None, max_length=40)
    references: list[dict[str, Any]] | None = None
    settings: dict[str, Any] | None = None
    revision: int | None = Field(default=None, ge=1)


class ApproveShotRequest(BaseModel):
    media_id: int = Field(gt=0)
    revision: int | None = Field(default=None, ge=1)


class RejectShotRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


@router.get("")
async def get_production(project_id: int, session: AsyncSession = Depends(get_db_session)):
    await get_project_or_404(session, project_id)
    return await production_payload(session, project_id)


@router.get("/candidates/by-media/{media_id}")
async def find_candidate_shot(project_id: int, media_id: int, session: AsyncSession = Depends(get_db_session)):
    await get_project_or_404(session, project_id)
    target = await find_exact_shot_for_media(session, project_id=project_id, media_id=media_id)
    if target is None:
        raise HTTPException(status_code=404, detail="No exact production shot found for this candidate.")
    return target


@router.get("/shots/{shot_id}/candidates")
async def get_shot_candidates(project_id: int, shot_id: int, session: AsyncSession = Depends(get_db_session)):
    shot = await ensure_project_shot(session, shot_id, project_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    # Scene-level legacy outputs are not candidates for a canonical plan.
    # Keeping them out of the default UI prevents old generations from
    # contaminating the active shot's review queue.
    return {
        "shot": shot_dict(shot),
        "candidates": await list_shot_candidates(session, shot, include_scene_fallback=False),
    }


@router.patch("/shots/{shot_id}")
async def update_shot(project_id: int, shot_id: int, request: ShotUpdateRequest, session: AsyncSession = Depends(get_db_session)):
    shot = await ensure_project_shot(session, shot_id, project_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    if request.revision is not None and request.revision != shot.revision:
        raise HTTPException(status_code=409, detail="Shot changed since it was loaded; reload before editing.")
    data = request.model_dump(exclude_none=True)
    data.pop("revision", None)
    for key in ("references", "settings"):
        if key in data:
            data[key] = json.dumps(data[key], ensure_ascii=False)
    for key, value in data.items():
        setattr(shot, key, value)
    shot.revision += 1
    shot.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(shot)
    await ws_manager.broadcast("project_production_updated", {"project_id": project_id, "shot_id": shot_id})
    return shot_dict(shot)


@router.post("/shots/{shot_id}/approve")
async def approve_shot(project_id: int, shot_id: int, request: ApproveShotRequest, session: AsyncSession = Depends(get_db_session)):
    shot = await ensure_project_shot(session, shot_id, project_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    if request.revision is not None and request.revision != shot.revision:
        raise HTTPException(status_code=409, detail="Shot changed since it was loaded; reload before approving.")
    media = await session.scalar(select(MediaItem).where(MediaItem.id == request.media_id, MediaItem.deleted_at.is_(None)))
    job = await session.scalar(
        select(GenerationJob)
        .where(
            GenerationJob.project_id == project_id,
            GenerationJob.result_media_id == request.media_id,
            GenerationJob.status == "completed",
        )
        .order_by(GenerationJob.completed_at.desc(), GenerationJob.id.desc())
        .limit(1)
    )
    if media is None or job is None:
        raise HTTPException(status_code=422, detail="Only a completed generation from this project can be approved.")
    candidate = next(
        (item for item in await list_shot_candidates(session, shot, limit=50) if int(item["media_id"]) == request.media_id),
        None,
    )
    if candidate is None or not candidate.get("approval_eligible"):
        raise HTTPException(status_code=422, detail="This generation is not an exact candidate for this shot.")
    last_frame_id = request.media_id
    if (media.file_format or "").lower() in {"mp4", "webm", "mov", "avi", "mkv", "ogg", "m4v"}:
        try:
            last_frame_id = await ensure_last_frame_media(
                session,
                source_media_id=request.media_id,
                workspace_dir=get_project_workspace(project_id),
                project_id=project_id,
            )
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    shot.accepted_media_id = request.media_id
    shot.accepted_last_frame_media_id = last_frame_id
    shot.status = "complete"
    shot.validation_status = "approved"
    shot.revision += 1
    shot.updated_at = datetime.utcnow()
    await session.commit()
    await ws_manager.broadcast("project_production_updated", {"project_id": project_id, "shot_id": shot_id, "status": "approved"})
    return {"status": "approved", "shot": shot_dict(shot), "last_frame_media_id": last_frame_id}


@router.post("/shots/{shot_id}/reject")
async def reject_shot(project_id: int, shot_id: int, request: RejectShotRequest, session: AsyncSession = Depends(get_db_session)):
    shot = await ensure_project_shot(session, shot_id, project_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    shot.status = "needs_review"
    shot.validation_status = "changes_requested"
    shot.revision += 1
    shot.updated_at = datetime.utcnow()
    settings = json.loads(shot.settings or "{}")
    settings["last_rejection_reason"] = request.reason
    shot.settings = json.dumps(settings, ensure_ascii=False)
    await session.commit()
    await ws_manager.broadcast("project_production_updated", {"project_id": project_id, "shot_id": shot_id, "status": "rejected"})
    return {"status": "rejected", "shot": shot_dict(shot)}
