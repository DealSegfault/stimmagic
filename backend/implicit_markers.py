"""System-owned markers derived from Media provenance.

Implicit markers share the browser presentation and filter grammar of user
markers, but they are never rows in the configurable ``markers`` table and
cannot be assigned or removed by users.
"""

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from database import AssetRevision, MediaItem, MediaToolLineage


IMPLICIT_MARKER_PREFIX = "implicit:"
EDITED_MARKER_KEY = "edited"
EDITED_MARKER_ID = f"{IMPLICIT_MARKER_PREFIX}{EDITED_MARKER_KEY}"
IMAGE_EDITOR_TOOL_ID = "builtin:stimma:image-editor"
# Add future first-party video/audio editor tool IDs here. The public marker
# contract stays "edited" while the provenance sources can expand.
EDITED_TOOL_IDS = (IMAGE_EDITOR_TOOL_ID,)

EDITED_MARKER = {
    "id": EDITED_MARKER_ID,
    "key": EDITED_MARKER_KEY,
    "name": "edited",
    "icon_svg": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'fill="currentColor" aria-hidden="true" data-slot="icon">'
        '<path d="M21.731 2.269a2.625 2.625 0 0 0-3.712 0l-1.157 '
        '1.157 3.712 3.712 1.157-1.157a2.625 2.625 0 0 0 0-3.712ZM19.513 '
        '8.199l-3.712-3.712-12.15 12.15a5.25 5.25 0 0 0-1.32 '
        '2.214l-.8 2.685a.75.75 0 0 0 .933.933l2.685-.8a5.25 5.25 0 0 '
        '0 2.214-1.32L19.513 8.2Z" />'
        '</svg>'
    ),
    "color": "#14b8a6",
    "implicit": True,
    "source": "system",
}


def split_marker_filter_tokens(value: str | None) -> tuple[list[int], list[str]]:
    """Split a mixed user/implicit marker filter into canonical identities."""
    user_ids: list[int] = []
    implicit_keys: list[str] = []
    for raw_token in (value or "").split(","):
        token = raw_token.strip()
        if not token:
            continue
        if token.startswith(IMPLICIT_MARKER_PREFIX):
            key = token.removeprefix(IMPLICIT_MARKER_PREFIX)
            if key == EDITED_MARKER_KEY:
                implicit_keys.append(key)
            continue
        try:
            user_ids.append(int(token))
        except ValueError:
            continue
    return user_ids, implicit_keys


def media_has_implicit_marker(marker_key: str, media_id_column=None):
    """Return the SQL predicate for a computed marker on a Media payload."""
    media_id_column = media_id_column if media_id_column is not None else MediaItem.id
    if marker_key != EDITED_MARKER_KEY:
        raise ValueError(f"Unknown implicit marker: {marker_key}")
    return (
        select(1)
        .select_from(MediaToolLineage)
        .where(
            MediaToolLineage.media_id == media_id_column,
            MediaToolLineage.full_tool_id.in_(EDITED_TOOL_IDS),
        )
        .correlate_except(MediaToolLineage)
        .exists()
    )


def implicit_marker_predicates(marker_keys: Iterable[str], media_id_column=None) -> list:
    """Build predicates for all recognized implicit marker keys."""
    return [
        media_has_implicit_marker(key, media_id_column)
        for key in dict.fromkeys(marker_keys)
        if key == EDITED_MARKER_KEY
    ]


async def implicit_markers_by_media(
    session: AsyncSession, media_ids: Iterable[int]
) -> dict[int, list[dict]]:
    """Return computed marker projections for the requested Media IDs."""
    ids = list(dict.fromkeys(media_ids))
    result = {media_id: [] for media_id in ids}
    if not ids:
        return result

    edited_ids = set(
        await session.scalars(
            select(MediaToolLineage.media_id).where(
                MediaToolLineage.media_id.in_(ids),
                MediaToolLineage.full_tool_id.in_(EDITED_TOOL_IDS),
            )
        )
    )
    for media_id in edited_ids:
        result[media_id] = [dict(EDITED_MARKER)]
    return result


def latest_edited_revision_at(asset_id_column):
    """Latest Revision timestamp that satisfies the edited-marker criteria.

    The marker is lineage-based, so the sort timestamp must be lineage-based as
    well. This keeps inherited editor provenance and direct editor output under
    the same definition instead of independently consulting ``MediaItem.tool_id``.
    """
    revision = aliased(AssetRevision)
    media = aliased(MediaItem)
    tool_lineage = aliased(MediaToolLineage)
    return (
        select(func.max(revision.created_at))
        .select_from(revision)
        .join(media, media.id == revision.primary_media_id)
        .join(tool_lineage, tool_lineage.media_id == media.id)
        .where(
            revision.asset_id == asset_id_column,
            revision.deleted_at.is_(None),
            media.deleted_at.is_(None),
            tool_lineage.full_tool_id.in_(EDITED_TOOL_IDS),
        )
        .correlate_except(revision, media, tool_lineage)
        .scalar_subquery()
    )
