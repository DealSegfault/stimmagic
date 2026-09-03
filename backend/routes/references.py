"""Project reference generation, view-sheet and composition API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db_session
from database import ProjectReferenceView
from inpaint_service import (
    InpaintServiceError,
    compile_inpaint_prompt,
    execute_inpaint,
    execute_reference_generation,
    save_mask_image,
)
from project_service import get_project_or_404
from reference_generation_service import (
    approve_composition_candidate,
    approve_view_candidate,
    generate_composition_candidate,
    generate_view_candidate,
    reject_composition_candidate,
    reject_view_candidate,
    render_reference_sheet,
)
from reference_service import (
    ReferenceServiceError,
    create_composition,
    create_element_state,
    get_composition,
    get_pack,
    reference_workspace_payload,
    serialize_composition,
    serialize_pack,
    serialize_state,
    soft_delete_composition,
    sync_location_views_from_blocking,
    update_pack_contract,
)
from utils.websocket import ws_manager


router = APIRouter(
    prefix="/api/projects/{project_id}/references",
    tags=["project-references"],
)

global_router = APIRouter(
    prefix="/api/references",
    tags=["references"],
)


class InpaintZoneRequest(BaseModel):
    color_name: str
    color_hex: str | None = None
    target: str = "@image1"
    operation: str = "replace"
    instruction: str = ""
    reference_media_ids: list[int] = Field(default_factory=list)


class InpaintRequest(BaseModel):
    source_media_id: int = Field(gt=0)
    mask_media_id: int | None = None
    mask_image_base64: str | None = None
    zones: list[InpaintZoneRequest] = Field(default_factory=list)
    prompt_override: str | None = None
    reference_media_ids: list[int] = Field(default_factory=list)
    dimensions: list[int] | None = None


class ReferenceGenRequest(BaseModel):
    prompt: str = Field(min_length=1)
    reference_media_ids: list[int] = Field(default_factory=list)
    negative_prompt: str | None = None
    dimensions: list[int] | None = None



class PackUpdateRequest(BaseModel):
    identity_prompt: str | None = None
    negative_prompt: str | None = None


class StateCreateRequest(BaseModel):
    state_key: str | None = Field(default=None, max_length=80)
    label: str = Field(min_length=1, max_length=160)
    prompt_delta: str | None = None
    constraints: dict[str, Any] | None = None


class CompositionItemRequest(BaseModel):
    project_element_id: int = Field(gt=0)
    reference_view_id: int = Field(gt=0)
    state_id: int | None = Field(default=None, gt=0)
    role: str = "prop"
    placement: dict[str, Any] = Field(default_factory=dict)


class CompositionCreateRequest(BaseModel):
    location_view_id: int = Field(gt=0)
    name: str | None = Field(default=None, max_length=255)
    prompt_delta: str | None = None
    placement_guide_media_id: int | None = Field(default=None, gt=0)
    items: list[CompositionItemRequest] = Field(min_length=1, max_length=7)


class CompositionApproveRequest(BaseModel):
    force: bool = False


def _http_error(exc: ReferenceServiceError) -> HTTPException:
    detail = str(exc)
    status = 404 if "not found" in detail.casefold() or "unavailable" in detail.casefold() else 422
    return HTTPException(status_code=status, detail=detail)


async def _broadcast(project_id: int, **payload: Any) -> None:
    await ws_manager.broadcast(
        "project_references_updated",
        {"project_id": project_id, **payload},
    )


@router.get("")
async def get_reference_workspace(
    project_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    await get_project_or_404(session, project_id)
    try:
        return await reference_workspace_payload(session, project_id)
    except ReferenceServiceError as exc:
        raise _http_error(exc) from exc


@router.patch("/packs/{pack_id}")
async def update_pack(
    project_id: int,
    pack_id: int,
    request: PackUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        pack = await get_pack(session, project_id=project_id, pack_id=pack_id)
        await update_pack_contract(
            session,
            pack=pack,
            identity_prompt=request.identity_prompt,
            negative_prompt=request.negative_prompt,
        )
        await session.commit()
        await _broadcast(project_id, pack_id=pack.id, action="contract_updated")
        return await serialize_pack(session, pack)
    except ReferenceServiceError as exc:
        await session.rollback()
        raise _http_error(exc) from exc


@router.post("/sync-blocking")
async def sync_blocking_views(
    project_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        result = await sync_location_views_from_blocking(session, project_id=project_id)
        await session.commit()
        await _broadcast(project_id, action="blocking_synced")
        return result
    except ReferenceServiceError as exc:
        await session.rollback()
        raise _http_error(exc) from exc


@router.post("/packs/{pack_id}/states")
async def create_state(
    project_id: int,
    pack_id: int,
    request: StateCreateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        pack = await get_pack(session, project_id=project_id, pack_id=pack_id)
        state = await create_element_state(
            session,
            project_id=project_id,
            element_id=pack.project_element_id,
            state_key=request.state_key or request.label,
            label=request.label,
            prompt_delta=request.prompt_delta,
            constraints=request.constraints,
        )
        await session.commit()
        await _broadcast(project_id, pack_id=pack.id, state_id=state.id, action="state_created")
        return await serialize_state(state)
    except ReferenceServiceError as exc:
        await session.rollback()
        raise _http_error(exc) from exc


@router.post("/views/{view_id}/generate")
async def generate_view(
    project_id: int,
    view_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        payload = await generate_view_candidate(session, project_id=project_id, view_id=view_id)
        await _broadcast(project_id, view_id=view_id, action="view_candidate_ready")
        return payload
    except ReferenceServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/packs/{pack_id}/generate-missing")
async def generate_missing_views(
    project_id: int,
    pack_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        pack = await get_pack(session, project_id=project_id, pack_id=pack_id)
        views = list(
            await session.scalars(
                select(ProjectReferenceView)
                .where(
                    ProjectReferenceView.pack_id == pack.id,
                    ProjectReferenceView.status.in_(["missing", "stale", "rejected", "error"]),
                    ProjectReferenceView.deleted_at.is_(None),
                )
                .order_by(ProjectReferenceView.sort_order, ProjectReferenceView.id)
                .limit(6)
            )
        )
        results = []
        errors = []
        for view in views:
            try:
                results.append(await generate_view_candidate(
                    session, project_id=project_id, view_id=view.id
                ))
            except ReferenceServiceError as exc:
                errors.append({"view_id": view.id, "error": str(exc)})
        await _broadcast(project_id, pack_id=pack.id, action="view_batch_finished")
        return {"generated": results, "errors": errors}
    except ReferenceServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/views/{view_id}/approve")
async def approve_view(
    project_id: int,
    view_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        payload = await approve_view_candidate(session, project_id=project_id, view_id=view_id)
        await _broadcast(project_id, view_id=view_id, action="view_approved")
        return payload
    except ReferenceServiceError as exc:
        await session.rollback()
        raise _http_error(exc) from exc


@router.post("/views/{view_id}/reject")
async def reject_view(
    project_id: int,
    view_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        payload = await reject_view_candidate(session, project_id=project_id, view_id=view_id)
        await _broadcast(project_id, view_id=view_id, action="view_rejected")
        return payload
    except ReferenceServiceError as exc:
        await session.rollback()
        raise _http_error(exc) from exc


@router.post("/packs/{pack_id}/render-sheet")
async def render_sheet(
    project_id: int,
    pack_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        payload = await render_reference_sheet(session, project_id=project_id, pack_id=pack_id)
        await _broadcast(project_id, pack_id=pack_id, action="sheet_rendered")
        return payload
    except ReferenceServiceError as exc:
        await session.rollback()
        raise _http_error(exc) from exc


@router.post("/compositions")
async def create_project_composition(
    project_id: int,
    request: CompositionCreateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        composition = await create_composition(
            session,
            project_id=project_id,
            location_view_id=request.location_view_id,
            name=request.name,
            prompt_delta=request.prompt_delta,
            placement_guide_media_id=request.placement_guide_media_id,
            items=[item.model_dump() for item in request.items],
        )
        await session.commit()
        await _broadcast(project_id, composition_id=composition.id, action="composition_created")
        return await serialize_composition(session, composition)
    except ReferenceServiceError as exc:
        await session.rollback()
        raise _http_error(exc) from exc


@router.post("/compositions/{composition_id}/generate")
async def generate_composition(
    project_id: int,
    composition_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        payload = await generate_composition_candidate(
            session, project_id=project_id, composition_id=composition_id
        )
        await _broadcast(project_id, composition_id=composition_id, action="composition_candidate_ready")
        return payload
    except ReferenceServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/compositions/{composition_id}/approve")
async def approve_composition(
    project_id: int,
    composition_id: int,
    request: CompositionApproveRequest,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        payload = await approve_composition_candidate(
            session,
            project_id=project_id,
            composition_id=composition_id,
            force=request.force,
        )
        await _broadcast(project_id, composition_id=composition_id, action="composition_approved")
        return payload
    except ReferenceServiceError as exc:
        await session.rollback()
        raise _http_error(exc) from exc


@router.post("/compositions/{composition_id}/reject")
async def reject_composition(
    project_id: int,
    composition_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        payload = await reject_composition_candidate(
            session, project_id=project_id, composition_id=composition_id
        )
        await _broadcast(project_id, composition_id=composition_id, action="composition_rejected")
        return payload
    except ReferenceServiceError as exc:
        await session.rollback()
        raise _http_error(exc) from exc


@router.delete("/compositions/{composition_id}")
async def delete_composition(
    project_id: int,
    composition_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        composition = await get_composition(
            session, project_id=project_id, composition_id=composition_id
        )
        await soft_delete_composition(session, composition)
        await session.commit()
        await _broadcast(project_id, composition_id=composition_id, action="composition_deleted")
        return {"status": "success"}
    except ReferenceServiceError as exc:
        await session.rollback()
        raise _http_error(exc) from exc


async def _handle_inpaint(
    request: InpaintRequest,
    project_id: int | None,
    session: AsyncSession,
) -> dict[str, Any]:
    try:
        mask_id = request.mask_media_id
        if not mask_id and request.mask_image_base64:
            mask_media = await save_mask_image(
                session,
                request.mask_image_base64,
                project_id=project_id,
                source_media_id=request.source_media_id,
            )
            mask_id = mask_media.id

        if not mask_id:
            raise HTTPException(status_code=400, detail="Either mask_media_id or mask_image_base64 is required.")

        compiled_prompt = compile_inpaint_prompt(
            [z.model_dump() for z in request.zones],
            prompt_override=request.prompt_override,
        )

        all_reference_ids = list(request.reference_media_ids or [])
        for z in request.zones:
            for rid in z.reference_media_ids:
                if rid not in all_reference_ids:
                    all_reference_ids.append(rid)

        result = await execute_inpaint(
            session,
            source_media_id=request.source_media_id,
            mask_media_id=mask_id,
            prompt=compiled_prompt,
            reference_media_ids=all_reference_ids,
            project_id=project_id,
            expected_dimensions=request.dimensions,
        )
        if project_id:
            await _broadcast(project_id, action="inpaint_candidate_ready", media_id=result.get("result_media_id"))
        return result
    except InpaintServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _handle_reference_generation(
    request: ReferenceGenRequest,
    project_id: int | None,
    session: AsyncSession,
) -> dict[str, Any]:
    try:
        result = await execute_reference_generation(
            session,
            prompt=request.prompt,
            reference_media_ids=request.reference_media_ids,
            negative_prompt=request.negative_prompt,
            dimensions=request.dimensions,
            project_id=project_id,
        )
        if project_id:
            await _broadcast(project_id, action="reference_candidate_ready", media_id=result.get("result_media_id"))
        return result
    except InpaintServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/inpaint")
async def inpaint_project_image(
    project_id: int,
    request: InpaintRequest,
    session: AsyncSession = Depends(get_db_session),
):
    await get_project_or_404(session, project_id)
    return await _handle_inpaint(request, project_id, session)


@router.post("/generate-with-reference")
async def generate_project_with_reference(
    project_id: int,
    request: ReferenceGenRequest,
    session: AsyncSession = Depends(get_db_session),
):
    await get_project_or_404(session, project_id)
    return await _handle_reference_generation(request, project_id, session)


@global_router.post("/inpaint")
async def inpaint_global_image(
    request: InpaintRequest,
    session: AsyncSession = Depends(get_db_session),
):
    return await _handle_inpaint(request, None, session)


@global_router.post("/generate-with-reference")
async def generate_global_with_reference(
    request: ReferenceGenRequest,
    session: AsyncSession = Depends(get_db_session),
):
    return await _handle_reference_generation(request, None, session)
