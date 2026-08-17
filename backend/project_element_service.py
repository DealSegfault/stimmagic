"""Durable project element identities shared by the API and agent tools."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from asset_association_service import attach_asset_to_project
from asset_service import AssetServiceError, create_asset_from_media
from database import Asset, AssetRevision, MediaItem, Project, ProjectElement


ELEMENT_TYPES = {"location", "character", "prop"}
ELEMENT_PREFIXES = {"location": "loc", "character": "char", "prop": "prop"}


class ProjectElementError(ValueError):
    """A project element request violates a user-facing invariant."""


def slugify_element_part(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_value).strip("_")
    return slug


def normalize_element_type(value: str | None) -> str:
    normalized = (value or "prop").strip().lower()
    aliases = {
        "loc": "location",
        "lieu": "location",
        "char": "character",
        "personnage": "character",
        "accessoire": "prop",
        "objet": "prop",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in ELEMENT_TYPES:
        raise ProjectElementError("Element type must be location, character, or prop")
    return normalized


def build_element_reference(element_type: str, project_name: str, name: str) -> str:
    normalized_type = normalize_element_type(element_type)
    project_slug = slugify_element_part(project_name)
    name_slug = slugify_element_part(name)
    if not project_slug:
        raise ProjectElementError("Project name cannot produce a valid element identifier")
    if not name_slug:
        raise ProjectElementError("Element name cannot be empty")
    return f"{ELEMENT_PREFIXES[normalized_type]}_{project_slug}_{name_slug}"


async def _live_project(session: AsyncSession, project_id: int) -> Project:
    project = await session.scalar(
        select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    )
    if project is None:
        raise ProjectElementError(f"Project {project_id} not found")
    return project


async def _resolve_asset(
    session: AsyncSession,
    *,
    asset_id: int | None,
    media_id: int | None,
    path: str | Path | None = None,
    workspace_dir: str | Path | None = None,
    project_id: int | None = None,
    title: str,
) -> Asset:
    asset: Asset | None = None

    if path is not None:
        p = Path(path)
        if not p.is_absolute() and workspace_dir:
            p = Path(workspace_dir) / p
        if p.exists() and p.is_file():
            media = await session.scalar(
                select(MediaItem).where(
                    MediaItem.file_path == str(p),
                    MediaItem.deleted_at.is_(None),
                    MediaItem.deletion_pending_at.is_(None),
                )
            )
            if media is not None:
                media_id = media.id
            else:
                import json
                from agent.v2.tools.library import save_workspace_file
                ws_path = Path(workspace_dir) if workspace_dir else (p.parent if p.is_absolute() else None)
                save_resp = await save_workspace_file(
                    session,
                    path=str(p),
                    workspace_dir=ws_path,
                    save_tags=None,
                    project_id=project_id,
                    materialize_asset=True,
                )
                if save_resp and not save_resp.startswith("Error:"):
                    try:
                        save_data = json.loads(save_resp)
                        media_id = save_data.get("media_id")
                        asset_id = save_data.get("asset_id")
                    except Exception:
                        pass

    # A Media ID is the unambiguous identity carried by chat attachments and
    # workspace references. If both values are present, use it as the source
    # of truth and only reject a *live* Asset ID that points somewhere else.
    # This keeps stale/model-guessed asset IDs from masking a valid upload.
    if asset_id is not None and media_id is not None:
        candidate = await session.scalar(
            select(Asset).where(
                Asset.id == asset_id,
                Asset.state == "active",
                Asset.deleted_at.is_(None),
            )
        )
        if candidate is not None:
            asset = candidate

    if asset_id is not None and media_id is None:
        asset = await session.scalar(
            select(Asset).where(
                Asset.id == asset_id,
                Asset.state == "active",
                Asset.deleted_at.is_(None),
            )
        )
        if asset is None:
            media = await session.scalar(
                select(MediaItem).where(
                    MediaItem.id == asset_id,
                    MediaItem.deleted_at.is_(None),
                    MediaItem.deletion_pending_at.is_(None),
                )
            )
            if media is not None:
                media_id = asset_id
                asset_id = None
            else:
                raise ProjectElementError(f"Asset {asset_id} not found")

    if media_id is not None:
        media = await session.scalar(
            select(MediaItem).where(
                MediaItem.id == media_id,
                MediaItem.deleted_at.is_(None),
                MediaItem.deletion_pending_at.is_(None),
            )
        )
        if media is None:
            raise ProjectElementError(f"Media {media_id} not found")
        try:
            media_asset = await create_asset_from_media(
                session,
                media_id=media_id,
                title=title,
                origin_type="project_element",
                origin_id=str(media_id),
            )
        except AssetServiceError as exc:
            raise ProjectElementError(str(exc)) from exc
        if asset is not None and asset.id != media_asset.id:
            raise ProjectElementError("asset_id and media_id refer to different Assets")
        asset = media_asset

    if asset is None:
        raise ProjectElementError("asset_id, media_id, or path is required")
    return asset


async def create_project_element(
    session: AsyncSession,
    *,
    project_id: int,
    name: str,
    element_type: str | None = "prop",
    asset_id: int | None = None,
    media_id: int | None = None,
    path: str | Path | None = None,
    workspace_dir: str | Path | None = None,
    description: str | None = None,
) -> tuple[ProjectElement, bool]:
    project = await _live_project(session, project_id)
    clean_name = (name or "").strip()
    normalized_type = normalize_element_type(element_type)
    reference_id = build_element_reference(normalized_type, project.name, clean_name)
    asset = await _resolve_asset(
        session,
        asset_id=asset_id,
        media_id=media_id,
        path=path,
        workspace_dir=workspace_dir,
        project_id=project_id,
        title=clean_name,
    )

    existing = await session.scalar(
        select(ProjectElement).where(
            ProjectElement.project_id == project_id,
            ProjectElement.reference_id == reference_id,
            ProjectElement.deleted_at.is_(None),
        )
    )
    if existing is not None:
        if existing.asset_id != asset.id:
            raise ProjectElementError(
                f"@{reference_id} already exists with another asset"
            )
        return existing, False

    await attach_asset_to_project(session, project_id, asset.id)
    element = ProjectElement(
        project_id=project_id,
        asset_id=asset.id,
        element_type=normalized_type,
        name=clean_name,
        reference_id=reference_id,
        description=(description or "").strip() or None,
    )
    session.add(element)
    await session.flush()
    return element, True


async def list_project_elements(
    session: AsyncSession,
    *,
    project_id: int,
    element_type: str | None = None,
    query: str | None = None,
) -> list[dict]:
    await _live_project(session, project_id)
    stmt = select(ProjectElement).where(
        ProjectElement.project_id == project_id,
        ProjectElement.deleted_at.is_(None),
    )
    if element_type:
        stmt = stmt.where(ProjectElement.element_type == normalize_element_type(element_type))
    if query and query.strip():
        term = f"%{query.strip()}%"
        stmt = stmt.where(
            or_(
                ProjectElement.name.ilike(term),
                ProjectElement.reference_id.ilike(term),
            )
        )
    elements = (
        await session.scalars(
            stmt.order_by(ProjectElement.updated_at.desc(), ProjectElement.id.desc())
        )
    ).all()
    return [await serialize_project_element(session, element) for element in elements]


async def get_project_element(
    session: AsyncSession, *, project_id: int, element_id: int
) -> ProjectElement:
    element = await session.scalar(
        select(ProjectElement).where(
            ProjectElement.id == element_id,
            ProjectElement.project_id == project_id,
            ProjectElement.deleted_at.is_(None),
        )
    )
    if element is None:
        raise ProjectElementError(f"Element {element_id} not found")
    return element


async def delete_project_element(
    session: AsyncSession, *, project_id: int, element_id: int
) -> ProjectElement:
    element = await get_project_element(
        session, project_id=project_id, element_id=element_id
    )
    element.deleted_at = datetime.utcnow()
    element.updated_at = element.deleted_at
    await session.flush()
    return element


async def serialize_project_element(
    session: AsyncSession, element: ProjectElement
) -> dict:
    asset = await session.get(Asset, element.asset_id) if element.asset_id else None
    revision = None
    media = None
    if asset is not None and asset.current_revision_id is not None:
        revision = await session.get(AssetRevision, asset.current_revision_id)
        if revision is not None and revision.deleted_at is None:
            media = await session.get(MediaItem, revision.primary_media_id)

    return {
        "id": element.id,
        "project_id": element.project_id,
        "asset_id": asset.id if asset else None,
        "revision_id": revision.id if revision else None,
        "media_id": media.id if media else None,
        "file_hash": media.file_hash if media else None,
        "file_format": media.file_format if media else None,
        "element_type": element.element_type,
        "name": element.name,
        "reference_id": element.reference_id,
        "description": element.description,
        "created_at": element.created_at.isoformat() if element.created_at else None,
        "updated_at": element.updated_at.isoformat() if element.updated_at else None,
    }
