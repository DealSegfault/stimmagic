"""Routes for the op-stack image editor's working documents.

The stack document is server-persisted so a session survives app restarts and
so generated candidates can be owned by something durable. See
``image_stack_service`` for the on-disk shape.

The editor screen is the single writer for a given document; these routes are
storage, not orchestration. The one piece of policy here is the open handshake,
which resolves the base revision and reports whether a legacy ``editor_project``
sidecar exists so the client can offer to migrate it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import image_stack_service as stack
from core.dependencies import get_db_session
from core.logging import get_logger
from core.profile_context import get_current_profile
from database import Asset, AssetRevision, MediaItem, WorkingDocument

router = APIRouter(prefix="/api/image-stack", tags=["image-stack"])
log = get_logger(__name__)


class OpenStackRequest(BaseModel):
    asset_id: int
    # Open from a specific version ("Edit from this version"); defaults to head.
    revision_id: Optional[int] = None


class BaseInfo(BaseModel):
    asset_id: int
    revision_id: int
    media_id: int
    file_hash: str
    width: int
    height: int


class OpenStackResponse(BaseModel):
    document_id: int
    base: BaseInfo
    # Null when this asset has never been opened in the op-stack editor.
    document: Optional[dict] = None
    # The head at open time, so the client can tell when it has drifted.
    head_revision_id: Optional[int] = None
    # A legacy snapshot-editor sidecar exists and has not been migrated yet.
    legacy_project: Optional[dict] = None


class WriteDocumentRequest(BaseModel):
    document: dict


class AppendJournalRequest(BaseModel):
    entries: list[dict]


async def _load_document(
    session: AsyncSession, document_id: int
) -> tuple[WorkingDocument, Path]:
    document = await session.get(WorkingDocument, document_id)
    if (
        document is None
        or document.deleted_at is not None
        or document.editor_type != stack.EDITOR_TYPE
    ):
        raise HTTPException(status_code=404, detail="Stack document not found")
    directory = stack.document_dir(document, get_current_profile())
    return document, directory


@router.post("/open", response_model=OpenStackResponse)
async def open_stack(
    request: OpenStackRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Create or resume the stack document for an Asset.

    One document per (asset, branch): reopening the same asset resumes the same
    stack rather than starting a second one, which is what makes the editor's
    one-instance-per-asset rule hold across restarts.
    """
    from asset_service import create_working_document

    asset = await session.get(Asset, request.asset_id)
    if asset is None or asset.deleted_at is not None or asset.state != "active":
        raise HTTPException(status_code=404, detail="Asset not found")

    revision_id = request.revision_id or asset.current_revision_id
    revision = await session.get(AssetRevision, revision_id) if revision_id else None
    if (
        revision is None
        or revision.deleted_at is not None
        or revision.asset_id != asset.id
    ):
        raise HTTPException(status_code=400, detail="Base revision does not belong to this Asset")

    media = await session.get(MediaItem, revision.primary_media_id)
    if media is None:
        raise HTTPException(status_code=404, detail="Base revision has no media")

    # Entering the editor is a use of the Asset — the same retention boundary
    # the legacy editor honors on open.
    from asset_association_service import clear_asset_expiration
    await clear_asset_expiration(session, asset.id)

    document = await create_working_document(
        session,
        asset_id=asset.id,
        editor_type=stack.EDITOR_TYPE,
        base_revision_id=revision.id,
    )
    directory = stack.document_dir(document, get_current_profile())
    stack.ensure_layout(directory)
    if document.state_locator != str(directory):
        document.state_locator = str(directory)
    await session.commit()

    stored = await stack.read_document(directory)

    # A legacy sidecar is only interesting while the stack is still empty: once
    # v2 has written a document, that document is authoritative and the sidecar
    # is left untouched for the old editor (cross-channel divergence is by
    # design — see the channel-gated rollout).
    legacy_project = None
    if stored is None and media.has_editor_sidecar:
        legacy_project = await _read_legacy_sidecar(session, asset.id)

    return OpenStackResponse(
        document_id=document.id,
        base=BaseInfo(
            asset_id=asset.id,
            revision_id=revision.id,
            media_id=media.id,
            file_hash=media.file_hash,
            width=media.width or 0,
            height=media.height or 0,
        ),
        document=stored,
        head_revision_id=asset.current_revision_id,
        legacy_project=legacy_project,
    )


async def _read_legacy_sidecar(session: AsyncSession, asset_id: int) -> Optional[dict]:
    """The snapshot editor's serialized project, if one was ever saved."""
    from editor_service import load_working_document_state

    legacy = await session.scalar(
        select(WorkingDocument)
        .where(
            WorkingDocument.asset_id == asset_id,
            WorkingDocument.editor_type == "image",
            WorkingDocument.deleted_at.is_(None),
        )
        .order_by(WorkingDocument.id.desc())
    )
    if legacy is None or not legacy.state_locator:
        return None
    try:
        state = await load_working_document_state(legacy)
    except (FileNotFoundError, OSError, ValueError) as exc:
        log.info(f"image-stack: legacy sidecar unreadable for asset {asset_id}: {exc}")
        return None
    return state if isinstance(state, dict) else None


@router.get("/{document_id}")
async def get_stack(
    document_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    document, directory = await _load_document(session, document_id)
    return {
        "document_id": document.id,
        "asset_id": document.asset_id,
        "base_revision_id": document.base_revision_id,
        "document": await stack.read_document(directory),
        "journal_length": await stack.journal_length(directory),
    }


@router.put("/{document_id}/document")
async def put_stack_document(
    document_id: int,
    request: WriteDocumentRequest,
    session: AsyncSession = Depends(get_db_session),
):
    document, directory = await _load_document(session, document_id)
    try:
        await stack.write_document(directory, request.document)
    except stack.ImageStackError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    document.generation += 1
    await session.commit()
    return {"ok": True, "generation": document.generation}


@router.post("/{document_id}/journal")
async def append_stack_journal(
    document_id: int,
    request: AppendJournalRequest,
    session: AsyncSession = Depends(get_db_session),
):
    _, directory = await _load_document(session, document_id)
    try:
        length = await stack.append_journal(directory, request.entries)
    except stack.ImageStackError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "journal_length": length}


@router.get("/{document_id}/journal")
async def get_stack_journal(
    document_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    """The replayable suffix of the log — everything since the last checkpoint."""
    _, directory = await _load_document(session, document_id)
    return {"entries": await stack.read_journal(directory)}


@router.post("/{document_id}/payloads")
async def upload_stack_payload(
    document_id: int,
    file: UploadFile = File(...),
    name: str = Form(...),
    subdir: str = Form("payloads"),
    session: AsyncSession = Depends(get_db_session),
):
    """Store a mask, patch, stroke set or rendered layer under its op's name."""
    _, directory = await _load_document(session, document_id)
    data = await file.read()
    try:
        await stack.write_payload(directory, name, data, subdir=subdir)
    except stack.ImageStackError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ref": f"{subdir}/{name}", "bytes": len(data)}


@router.get("/{document_id}/payloads/{name}")
async def get_stack_payload(
    document_id: int,
    name: str,
    subdir: str = "payloads",
    session: AsyncSession = Depends(get_db_session),
):
    _, directory = await _load_document(session, document_id)
    try:
        path = stack.resolve_payload(directory, name, subdir=subdir)
    except stack.ImageStackError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Payload not found")
    # Paint layers are intentionally rewritten under a stable raster_ref as
    # strokes land. Force clients to revalidate that URL; otherwise WebKit can
    # keep returning the first PNG and the compositor appears to lose every
    # later stroke until a browser refresh.
    return FileResponse(path, headers={"Cache-Control": "no-cache"})


@router.delete("/{document_id}/cache")
async def clear_stack_cache(
    document_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    """Discard composite intermediates. Safe by construction: pure function of
    document + payloads + base."""
    _, directory = await _load_document(session, document_id)
    await stack.clear_cache(directory)
    return {"ok": True}
