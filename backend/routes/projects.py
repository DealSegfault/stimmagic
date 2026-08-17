"""Project routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db_session
from database import (
    Asset,
    AssetRevision,
    Board,
    BoardSection,
    Chat,
    MediaItem,
    Project,
    ProjectAsset,
    ProjectElement,
    ProjectMedia,
)
from models.api_models import (
    ProjectCreateRequest,
    ProjectResponse,
    ProjectSummaryResponse,
    ProjectUpdateRequest,
)
from llm_resolver import PROJECT_EFFORT_COLUMNS, PROJECT_ROLE_COLUMNS, normalize_model_slug
from project_service import get_project_or_404, initialize_project_root
from project_element_service import (
    ProjectElementError,
    create_project_element,
    delete_project_element,
    list_project_elements,
    serialize_project_element,
)
from utils.websocket import ws_manager

router = APIRouter(prefix="/api/projects", tags=["projects"])

# Per-role model override columns, in the order the settings UI shows them.
PROJECT_MODEL_COLUMNS = tuple(PROJECT_ROLE_COLUMNS.values())
# Effort overrides carry no slug normalization — they are level names.
PROJECT_EFFORT_COLS = tuple(PROJECT_EFFORT_COLUMNS.values())


async def _serialize_project(project: Project, session: AsyncSession) -> ProjectResponse:
    chat_count = await session.scalar(
        select(func.count()).select_from(Chat).where(
            Chat.project_id == project.id,
            Chat.deleted_at.is_(None),
        )
    )
    board_count = await session.scalar(
        select(func.count()).select_from(Board).where(
            Board.project_id == project.id,
            Board.deleted_at.is_(None),
        )
    )
    asset_count = await session.scalar(
        select(func.count(MediaItem.id))
        .select_from(ProjectAsset)
        .join(Asset, Asset.id == ProjectAsset.asset_id)
        .join(AssetRevision, AssetRevision.id == Asset.current_revision_id)
        .join(MediaItem, MediaItem.id == AssetRevision.primary_media_id)
        .where(
            ProjectAsset.project_id == project.id,
            ProjectAsset.deleted_at.is_(None),
            Asset.state == "active",
            Asset.deleted_at.is_(None),
            MediaItem.deleted_at.is_(None),
            or_(
                MediaItem.file_unavailable.is_(False),
                MediaItem.file_unavailable.is_(None),
            ),
        )
    )
    return ProjectResponse(
        **project.to_dict(),
        chat_count=chat_count or 0,
        board_count=board_count or 0,
        asset_count=asset_count or 0,
    )


@router.get("", response_model=list[ProjectSummaryResponse])
async def list_projects(session: AsyncSession = Depends(get_db_session)):
    result = await session.execute(
        select(
            Project,
            func.count(func.distinct(Chat.id)).label("chat_count"),
            func.count(func.distinct(Board.id)).label("board_count"),
            func.count(func.distinct(MediaItem.id)).label("asset_count"),
        )
        .outerjoin(Chat, and_(Chat.project_id == Project.id, Chat.deleted_at.is_(None)))
        .outerjoin(Board, and_(Board.project_id == Project.id, Board.deleted_at.is_(None)))
        .outerjoin(
            ProjectAsset,
            (ProjectAsset.project_id == Project.id)
            & ProjectAsset.deleted_at.is_(None),
        )
        .outerjoin(
            Asset,
            and_(
                Asset.id == ProjectAsset.asset_id,
                Asset.state == "active",
                Asset.deleted_at.is_(None),
            ),
        )
        .outerjoin(AssetRevision, AssetRevision.id == Asset.current_revision_id)
        .outerjoin(
            MediaItem,
            and_(
                MediaItem.id == AssetRevision.primary_media_id,
                MediaItem.deleted_at.is_(None),
                or_(
                    MediaItem.file_unavailable.is_(False),
                    MediaItem.file_unavailable.is_(None),
                ),
            ),
        )
        .where(Project.deleted_at.is_(None))
        .group_by(Project.id)
        .order_by(Project.updated_at.desc(), Project.id.desc())
    )
    return [
        ProjectSummaryResponse(
            **project.to_dict(),
            chat_count=chat_count or 0,
            board_count=board_count or 0,
            asset_count=asset_count or 0,
        )
        for project, chat_count, board_count, asset_count in result.all()
    ]


@router.post("", response_model=ProjectResponse)
async def create_project(
    request: ProjectCreateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    project = Project(
        name=(request.name or "").strip(),
        **{
            column: normalize_model_slug(getattr(request, column))
            for column in PROJECT_MODEL_COLUMNS
        },
        **{column: getattr(request, column) for column in PROJECT_EFFORT_COLS},
    )
    session.add(project)
    await session.flush()
    await initialize_project_root(session, project)
    await session.commit()
    await session.refresh(project)

    from object_hash import salted_hash
    from telemetry import get_telemetry_client
    get_telemetry_client().track("project_created", {
        "projectHash": salted_hash(f"project:{project.id}"),
    }, category="organize")

    result = await _serialize_project(project, session)
    await ws_manager.broadcast("project_created", {"project": result.model_dump()})
    return result


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int, session: AsyncSession = Depends(get_db_session)):
    project = await get_project_or_404(session, project_id)
    return await _serialize_project(project, session)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    request: ProjectUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    project = await get_project_or_404(session, project_id)
    if request.name is not None:
        project.name = request.name.strip()
    if request.additional_instructions is not None:
        project.additional_instructions = request.additional_instructions
    if request.memory is not None:
        project.memory = request.memory
    if request.agent_tool_config is not None:
        import json
        project.agent_tool_config = json.dumps(request.agent_tool_config)
    for column in PROJECT_MODEL_COLUMNS:
        value = getattr(request, column)
        if value is not None:
            # "" clears the override back to inheriting the profile setting.
            setattr(project, column, normalize_model_slug(value) if value else None)
    for column in PROJECT_EFFORT_COLS:
        value = getattr(request, column)
        if value is not None:
            setattr(project, column, value or None)
    project.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(project)
    result = await _serialize_project(project, session)
    await ws_manager.broadcast("project_updated", {"project": result.model_dump()})
    return result


@router.delete("/{project_id}")
async def delete_project(project_id: int, session: AsyncSession = Depends(get_db_session)):
    project = await get_project_or_404(session, project_id)
    deleted_at = datetime.utcnow()

    chat_result = await session.execute(
        select(Chat.id).where(Chat.project_id == project_id, Chat.deleted_at.is_(None))
    )
    deleted_chat_ids = [row[0] for row in chat_result.all()]
    if deleted_chat_ids:
        await session.execute(
            update(Chat)
            .where(Chat.id.in_(deleted_chat_ids))
            .values(deleted_at=deleted_at)
        )
        from routes.chats import _cancel_chat_work

        await _cancel_chat_work(session, deleted_chat_ids, deleted_at)

    board_result = await session.execute(
        select(Board.id).where(Board.project_id == project_id, Board.deleted_at.is_(None))
    )
    deleted_board_ids = [row[0] for row in board_result.all()]
    if deleted_board_ids:
        await session.execute(
            update(Board)
            .where(Board.id.in_(deleted_board_ids))
            .values(deleted_at=deleted_at, updated_at=deleted_at)
        )
        await session.execute(
            update(BoardSection)
            .where(BoardSection.board_id.in_(deleted_board_ids), BoardSection.deleted_at.is_(None))
            .values(deleted_at=deleted_at, updated_at=deleted_at, is_default=False)
        )

    # Assets are independent roots. Soft-delete organizational membership.
    await session.execute(
        update(ProjectAsset)
        .where(
            ProjectAsset.project_id == project_id,
            ProjectAsset.deleted_at.is_(None),
        )
        .values(deleted_at=deleted_at)
    )
    await session.execute(
        update(ProjectElement)
        .where(
            ProjectElement.project_id == project_id,
            ProjectElement.deleted_at.is_(None),
        )
        .values(deleted_at=deleted_at, updated_at=deleted_at)
    )
    # Historical staging edges have no soft-delete column.
    await session.execute(
        delete(ProjectMedia).where(ProjectMedia.project_id == project_id)
    )

    project.deleted_at = deleted_at
    project.updated_at = deleted_at
    await session.commit()

    for chat_id in deleted_chat_ids:
        await ws_manager.broadcast("chat_deleted", {"chat_id": chat_id})
    for board_id in deleted_board_ids:
        await ws_manager.broadcast("board_deleted", {"board_id": board_id})
    await ws_manager.broadcast("project_deleted", {"project_id": project_id})

    from object_hash import salted_hash
    from telemetry import get_telemetry_client
    get_telemetry_client().track("project_deleted", {
        "projectHash": salted_hash(f"project:{project_id}"),
    }, category="organize")

    return {"status": "success"}


class _ProjectMediaRequest(BaseModel):
    media_ids: list[int]


class _ProjectElementCreateRequest(BaseModel):
    name: str
    element_type: str = "prop"
    asset_id: int | None = None
    media_id: int | None = None
    description: str | None = None


@router.get("/{project_id}/elements")
async def list_elements(
    project_id: int,
    element_type: str | None = None,
    query: str | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        return await list_project_elements(
            session,
            project_id=project_id,
            element_type=element_type,
            query=query,
        )
    except ProjectElementError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/elements")
async def create_element(
    project_id: int,
    request: _ProjectElementCreateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        element, created = await create_project_element(
            session,
            project_id=project_id,
            name=request.name,
            element_type=request.element_type,
            asset_id=request.asset_id,
            media_id=request.media_id,
            description=request.description,
        )
        await session.commit()
        payload = await serialize_project_element(session, element)
        payload["created"] = created
        return payload
    except ProjectElementError as exc:
        await session.rollback()
        status_code = 409 if "already exists" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.delete("/{project_id}/elements/{element_id}")
async def delete_element(
    project_id: int,
    element_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        await delete_project_element(
            session, project_id=project_id, element_id=element_id
        )
        await session.commit()
        return {"status": "success"}
    except ProjectElementError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/assets")
async def add_media_to_project(
    project_id: int,
    request: _ProjectMediaRequest,
    session: AsyncSession = Depends(get_db_session),
):
    await get_project_or_404(session, project_id)
    result = await session.execute(
        select(MediaItem.id).where(
            MediaItem.id.in_(request.media_ids),
            MediaItem.deleted_at.is_(None),
        )
    )
    valid_ids = [row[0] for row in result.all()]
    from asset_association_service import asset_for_media, attach_asset_to_project

    added = 0
    for media_id in valid_ids:
        asset = await asset_for_media(
            session,
            media_id,
            promote=True,
            origin_type="project_promotion",
        )
        if asset is None:
            continue
        await attach_asset_to_project(session, project_id, asset.id)
        added += 1
    await session.commit()
    return {"status": "success", "added": added}


@router.delete("/{project_id}/assets/{media_id}")
async def remove_project_media(
    project_id: int,
    media_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    await get_project_or_404(session, project_id)
    from asset_association_service import asset_for_media, detach_asset_from_project

    asset = await asset_for_media(session, media_id)
    removed = bool(
        asset
        and await detach_asset_from_project(session, project_id, asset.id)
    )
    await session.commit()
    if not removed:
        raise HTTPException(status_code=404, detail="Asset not in project")
    return {"status": "success"}
