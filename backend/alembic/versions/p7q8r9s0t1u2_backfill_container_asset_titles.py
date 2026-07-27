"""backfill container Asset titles from their Media payloads

Container titles used to live in two places: the .stimmaset/.stimmagrid JSON
payload (written at creation) and Asset.title (written by renames). Asset.title
is now the only owner, so seed it for every container Asset that was promoted
before the payload title was carried across.

Revision ID: p7q8r9s0t1u2
Revises: o6p7q8r9s0t1
Create Date: 2026-07-26

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'p7q8r9s0t1u2'
down_revision: Union[str, Sequence[str], None] = 'o6p7q8r9s0t1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("""
        SELECT a.id AS asset_id, m.raw_metadata AS raw_metadata
        FROM assets a
        JOIN asset_revisions r ON r.id = a.current_revision_id
        JOIN media_items m ON m.id = r.primary_media_id
        WHERE a.title IS NULL
          AND a.asset_type IN ('set', 'grid')
          AND m.file_format IN ('stimmaset.json', 'stimmagrid.json')
          AND m.raw_metadata IS NOT NULL
    """)).fetchall()

    for asset_id, raw_metadata in rows:
        try:
            payload = json.loads(raw_metadata)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue
        title = payload.get('title')
        if not isinstance(title, str):
            continue
        title = title.strip()
        if not title or title == 'Untitled':
            continue
        conn.execute(
            sa.text("UPDATE assets SET title = :title WHERE id = :asset_id"),
            {"title": title, "asset_id": asset_id},
        )


def downgrade() -> None:
    # Titles are not distinguishable from user-entered ones after the fact.
    pass
