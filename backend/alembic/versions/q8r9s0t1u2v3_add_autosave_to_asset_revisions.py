"""add autosave flag to asset_revisions

Leaving the image editor commits the applied stack as a Revision, so the
asset's thumbnail and downstream consumers always see the current edit state.
Consecutive autosaves coalesce: the marker is what lets a later commit
recognize and swallow the head it is replacing.

Revision ID: q8r9s0t1u2v3
Revises: p7q8r9s0t1u2
Create Date: 2026-07-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'q8r9s0t1u2v3'
down_revision: Union[str, Sequence[str], None] = 'p7q8r9s0t1u2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'asset_revisions',
        sa.Column('autosave', sa.Boolean(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('asset_revisions', 'autosave')
