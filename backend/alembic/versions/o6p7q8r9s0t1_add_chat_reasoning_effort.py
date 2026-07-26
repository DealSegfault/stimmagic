"""add_chat_reasoning_effort

Revision ID: o6p7q8r9s0t1
Revises: n5o6p7q8r9s0
Create Date: 2026-07-26

Chats get their own reasoning effort, for the same reason they own their model:
the picker used to write a GLOBAL per-model level, so turning one chat up to Max
turned every chat on that model up with it. NULL = inherit from the project,
then the profile.

This is a separate revision on purpose. The column was first added to
n5o6p7q8r9s0 after that revision had already run, so the stamp said "applied"
while the statement never executed — a migration that has run is history and
cannot be edited into doing more.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'o6p7q8r9s0t1'
down_revision: Union[str, Sequence[str], None] = 'n5o6p7q8r9s0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {col['name'] for col in sa.inspect(connection).get_columns('chats')}
    if 'reasoning_effort' not in columns:
        op.add_column('chats', sa.Column('reasoning_effort', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('chats', 'reasoning_effort')
