"""Durable project element identities shared by the API and agent tools."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime

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
    title: str,
) -> Asset:
    asset: Asset | None = None
    if asset_id is not None:
        asset = await session.scalar(
            select(Asset).where(
                Asset.id == asset_id,
                Asset.state == "active",
                Asset.deleted_at.is_(None),
            )
        )
        if asset is None:
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
        raise ProjectElementError("asset_id or media_id is required")
    return asset


async def create_project_element(
    session: AsyncSession,
    *,
    project_id: int,
    name: str,
    element_type: str | None = "prop",
    asset_id: int | None = None,
    media_id: int | None = None,
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
