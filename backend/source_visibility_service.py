"""Visibility transitions for Sources removed from profile configuration."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import Asset, AssetRevision, MediaItem, StorageObject
from media_scanner import path_is_within_resolved_roots


@dataclass(frozen=True)
class SourceDeactivationResult:
    media_ids: list[int]
    asset_ids: list[int]


async def deactivate_removed_sources(
    session: AsyncSession,
    *,
    removed_paths: set[str],
    active_paths: set[str],
) -> SourceDeactivationResult:
    """Make media from explicitly removed Sources immediately unavailable.

    The rows and their Asset history remain retained. Re-adding a Source lets
    the ingestion scanner restore unchanged rows through its normal
    unavailable-file path.
    """
    if not removed_paths:
        return SourceDeactivationResult(media_ids=[], asset_ids=[])

    removed_roots = [
        Path(path).expanduser().resolve(strict=False) for path in removed_paths
    ]
    active_roots = [
        Path(path).expanduser().resolve(strict=False) for path in active_paths
    ]
    rows = await session.execute(
        select(MediaItem, StorageObject.kind)
        .outerjoin(StorageObject, StorageObject.id == MediaItem.storage_object_id)
        .where(
            MediaItem.deleted_at.is_(None),
            or_(
                MediaItem.storage_object_id.is_(None),
                StorageObject.kind == "external",
            ),
        )
    )

    now = datetime.utcnow()
    deactivated_ids: list[int] = []
    for media, _storage_kind in rows:
        candidate = Path(media.file_path).expanduser().resolve(strict=False)
        if not path_is_within_resolved_roots(candidate, removed_roots):
            continue
        # Be conservative if an old/hand-edited config contains overlapping
        # Sources: removing one must not hide files still covered by another.
        if path_is_within_resolved_roots(candidate, active_roots):
            continue
        if not media.file_unavailable:
            media.file_unavailable = True
            media.file_unavailable_since = now
        deactivated_ids.append(media.id)

    if not deactivated_ids:
        return SourceDeactivationResult(media_ids=[], asset_ids=[])

    asset_ids = list(await session.scalars(
        select(Asset.id)
        .join(AssetRevision, AssetRevision.id == Asset.current_revision_id)
        .where(AssetRevision.primary_media_id.in_(deactivated_ids))
        .order_by(Asset.id)
    ))
    await session.flush()
    return SourceDeactivationResult(
        media_ids=sorted(deactivated_ids),
        asset_ids=asset_ids,
    )
