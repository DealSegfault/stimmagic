"""TRELLIS.2 image-to-3D batch generation routes.

Stimma owns the durable job and Asset lifecycle. Modal only performs the
GPU-heavy inference and returns a GLB for each input image. Keeping the two
concerns separate means a restarted Modal container cannot orphan a Stimma
Asset, and a batch remains visible in the existing generation history.
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app_dirs
from asset_association_service import asset_for_media
from core.dependencies import get_db_session
from core.profile_context import get_current_profile, set_current_profile
from database import GenerationJob, MediaItem, Project
from database_registry import get_database_registry
from utils.websocket import ws_manager


router = APIRouter(prefix="/api/trellis2", tags=["trellis2"])

IMAGE_FORMATS = {"jpg", "jpeg", "png", "gif", "webp", "bmp"}
DEFAULT_MODEL = "microsoft/TRELLIS.2-4B"
DEFAULT_PARALLELISM = 8
MAX_PARALLELISM = 12
DEFAULT_TIMEOUT_SECONDS = 45 * 60

_batch_tasks: set[asyncio.Task] = set()


class Trellis2BatchRequest(BaseModel):
    project_id: int
    media_ids: list[int] = Field(min_length=1, max_length=100)
    resolution: Literal["512", "1024", "1536"] = "1536"
    texture_size: Literal[1024, 2048, 4096] = 4096
    decimation_target: int = Field(default=1_000_000, ge=100_000, le=2_000_000)
    parallelism: int = Field(default=DEFAULT_PARALLELISM, ge=1, le=MAX_PARALLELISM)
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)


def _modal_url() -> str | None:
    return os.environ.get("TRELLIS2_MODAL_URL", "").strip().rstrip("/") or None


def _modal_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    token_id = os.environ.get("TRELLIS2_MODAL_TOKEN_ID") or os.environ.get("MODAL_PROXY_TOKEN_ID")
    token_secret = os.environ.get("TRELLIS2_MODAL_TOKEN_SECRET") or os.environ.get("MODAL_PROXY_TOKEN_SECRET")
    if token_id and token_secret:
        headers.update({"Modal-Key": token_id, "Modal-Secret": token_secret})
    return headers


def _settings_dict(request: Trellis2BatchRequest) -> dict[str, Any]:
    return {
        "resolution": request.resolution,
        "texture_size": request.texture_size,
        "decimation_target": request.decimation_target,
        "parallelism": request.parallelism,
        "seed": request.seed,
        "model": DEFAULT_MODEL,
    }


def _job_params(job: GenerationJob) -> dict[str, Any]:
    try:
        return json.loads(job.parameters or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


async def _get_job_status(session: AsyncSession, batch_id: str) -> dict[str, Any]:
    result = await session.execute(
        select(GenerationJob)
        .where(GenerationJob.batch_id == batch_id)
        .order_by(GenerationJob.id.asc())
    )
    jobs = list(result.scalars().all())
    if not jobs:
        raise HTTPException(status_code=404, detail="TRELLIS.2 batch not found")

    statuses = [job.status for job in jobs]
    if any(status in {"queued", "assigned", "processing"} for status in statuses):
        batch_status = "processing" if any(status == "processing" for status in statuses) else "queued"
    elif any(status == "failed" for status in statuses):
        batch_status = "completed_with_errors" if any(status == "completed" for status in statuses) else "failed"
    else:
        batch_status = "completed"

    payload_jobs = []
    for job in jobs:
        params = _job_params(job)
        item: dict[str, Any] = {
            "id": job.id,
            "status": job.status,
            "source_media_id": params.get("source_media_id"),
            "source_filename": params.get("source_filename"),
            "result_media_id": job.result_media_id,
            "result_asset_id": job.result_asset_id,
            "error": job.error,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }
        if job.result_media_id:
            media = await session.get(MediaItem, job.result_media_id)
            if media:
                item["result_media"] = media.to_dict()
        payload_jobs.append(item)

    return {
        "batch_id": batch_id,
        "status": batch_status,
        "total": len(jobs),
        "completed": sum(status == "completed" for status in statuses),
        "failed": sum(status == "failed" for status in statuses),
        "processing": sum(status == "processing" for status in statuses),
        "queued": sum(status in {"queued", "assigned"} for status in statuses),
        "jobs": payload_jobs,
    }


async def _modal_submit_and_result(
    client: httpx.AsyncClient,
    *,
    image_bytes: bytes,
    filename: str,
    settings: dict[str, Any],
) -> bytes:
    url = _modal_url()
    if not url:
        raise RuntimeError("TRELLIS2_MODAL_URL is not configured")

    content_type = mimetypes.guess_type(filename)[0] or "image/png"
    response = await client.post(
        f"{url}/v1/generate",
        files={"file": (filename, image_bytes, content_type)},
        data={
            "resolution": settings["resolution"],
            "texture_size": str(settings["texture_size"]),
            "decimation_target": str(settings["decimation_target"]),
            "seed": "" if settings.get("seed") is None else str(settings["seed"]),
        },
        headers=_modal_headers(),
    )
    response.raise_for_status()
    call_id = response.json().get("call_id")
    if not call_id:
        raise RuntimeError("Modal TRELLIS.2 endpoint did not return a call_id")

    deadline = time.monotonic() + int(os.environ.get("TRELLIS2_JOB_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    while time.monotonic() < deadline:
        result = await client.get(
            f"{url}/v1/result/{call_id}",
            headers=_modal_headers(),
        )
        if result.status_code == 202:
            await asyncio.sleep(3)
            continue
        if result.status_code >= 400:
            detail = result.text[:500]
            raise RuntimeError(f"Modal TRELLIS.2 result failed ({result.status_code}): {detail}")
        if not result.content:
            raise RuntimeError("Modal TRELLIS.2 returned an empty GLB")
        return result.content

    raise TimeoutError("TRELLIS.2 generation timed out")


async def _set_job_state(
    profile_id: str,
    job_id: int,
    *,
    status: str,
    error: str | None = None,
    result_media_id: int | None = None,
    result_asset_id: int | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> None:
    set_current_profile(profile_id)
    db = get_database_registry().get_database(profile_id)
    async with db.async_session_maker() as session:
        job = await session.get(GenerationJob, job_id)
        if not job:
            return
        job.status = status
        job.error = error
        if result_media_id is not None:
            job.result_media_id = result_media_id
        if result_asset_id is not None:
            job.result_asset_id = result_asset_id
        if started_at is not None:
            job.started_at = started_at
        if completed_at is not None:
            job.completed_at = completed_at
        await session.commit()
        await ws_manager.broadcast(f"generation_job_{status}", {"job": job.to_dict()})


async def _run_one_job(profile_id: str, job_id: int) -> None:
    set_current_profile(profile_id)
    db = get_database_registry().get_database(profile_id)
    async with db.async_session_maker() as session:
        job = await session.get(GenerationJob, job_id)
        if not job:
            return
        params = _job_params(job)
        source = await session.get(MediaItem, params.get("source_media_id"))
        if not source or source.file_format.lower() not in IMAGE_FORMATS:
            await _set_job_state(profile_id, job_id, status="failed", error="Source image is unavailable")
            return
        source_path = Path(source.file_path)
        if not source_path.is_file():
            await _set_job_state(profile_id, job_id, status="failed", error="Source image file is unavailable")
            return
        image_bytes = source_path.read_bytes()
        filename = params.get("source_filename") or source.original_filename or f"source-{source.id}.png"
        settings = params.get("settings") or {}

    started = datetime.utcnow()
    await _set_job_state(profile_id, job_id, status="processing", started_at=started)
    try:
        from upload_service import UploadError, UploadService

        timeout = httpx.Timeout(None, connect=30)
        async with httpx.AsyncClient(timeout=timeout) as client:
            glb_bytes = await _modal_submit_and_result(
                client,
                image_bytes=image_bytes,
                filename=filename,
                settings=settings,
            )

        output_name = f"trellis2_{Path(filename).stem}.glb"
        media, _ = await UploadService(profile_id=profile_id).upload_file(
            glb_bytes,
            output_name,
            project_id=params.get("project_id"),
            materialize_asset=True,
        )

        set_current_profile(profile_id)
        async with db.async_session_maker() as session:
            asset = await asset_for_media(session, media.id)
            asset_id = asset.id if asset else None
            job = await session.get(GenerationJob, job_id)
            if not job:
                return
            job.status = "completed"
            job.result_media_id = media.id
            job.result_asset_id = asset_id
            job.completed_at = datetime.utcnow()
            job.error = None
            await session.commit()
            payload = job.to_dict()
        await ws_manager.broadcast("generation_job_completed", {"job": payload})
    except (UploadError, httpx.HTTPError, TimeoutError, RuntimeError, OSError) as exc:
        await _set_job_state(profile_id, job_id, status="failed", error=str(exc)[:1000], completed_at=datetime.utcnow())
    except Exception as exc:
        # Keep persisted jobs truthful even when a dependency or an unexpected
        # response fails outside the normal transport/upload error set.
        await _set_job_state(profile_id, job_id, status="failed", error=str(exc)[:1000], completed_at=datetime.utcnow())


async def _run_batch(profile_id: str, batch_id: str, job_ids: list[int], parallelism: int) -> None:
    semaphore = asyncio.Semaphore(parallelism)

    async def run(job_id: int) -> None:
        async with semaphore:
            await _run_one_job(profile_id, job_id)

    await asyncio.gather(*(run(job_id) for job_id in job_ids), return_exceptions=True)


def _retain_task(task: asyncio.Task) -> None:
    _batch_tasks.add(task)
    task.add_done_callback(_batch_tasks.discard)


@router.post("/batches")
async def create_trellis2_batch(
    request: Trellis2BatchRequest,
    session: AsyncSession = Depends(get_db_session),
):
    if not _modal_url():
        raise HTTPException(status_code=503, detail="TRELLIS.2 Modal endpoint is not configured")

    project = await session.get(Project, request.project_id)
    if not project or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await session.execute(
        select(MediaItem).where(
            MediaItem.id.in_(request.media_ids),
            MediaItem.deleted_at.is_(None),
            MediaItem.file_format.in_(IMAGE_FORMATS),
        )
    )
    sources = {item.id: item for item in result.scalars().all()}
    missing = [media_id for media_id in request.media_ids if media_id not in sources]
    if missing:
        raise HTTPException(status_code=400, detail=f"Invalid source images: {missing}")

    profile_id = get_current_profile()
    batch_id = uuid.uuid4().hex
    settings = _settings_dict(request)
    staging = str(app_dirs.get_managed_staging_dir(profile_id, "generated"))
    jobs: list[GenerationJob] = []
    for media_id in request.media_ids:
        source = sources[media_id]
        jobs.append(
            GenerationJob(
                status="queued",
                task_type="image-to-3d",
                generator_type="modal",
                generator_name="trellis2",
                model_name=DEFAULT_MODEL,
                parameters=json.dumps({
                    "source_media_id": media_id,
                    "source_filename": source.original_filename,
                    "project_id": request.project_id,
                    "settings": settings,
                }),
                folder_path=staging,
                generator_instance_id="modal-trellis2",
                backend_name="modal-trellis2",
                project_id=request.project_id,
                batch_id=batch_id,
                batch_total=len(request.media_ids),
                output_disposition="asset",
            )
        )
        session.add(jobs[-1])
    await session.flush()
    job_ids = [job.id for job in jobs]
    await session.commit()

    _retain_task(asyncio.create_task(_run_batch(profile_id, batch_id, job_ids, request.parallelism)))
    return {
        "batch_id": batch_id,
        "status": "queued",
        "total": len(job_ids),
        "job_ids": job_ids,
        "settings": settings,
    }


@router.get("/health")
async def get_trellis2_health():
    return {
        "configured": bool(_modal_url()),
        "model": DEFAULT_MODEL,
        "gpu": os.environ.get("TRELLIS2_GPU", "H100"),
    }


@router.get("/batches/{batch_id}")
async def get_trellis2_batch(batch_id: str, session: AsyncSession = Depends(get_db_session)):
    return await _get_job_status(session, batch_id)
