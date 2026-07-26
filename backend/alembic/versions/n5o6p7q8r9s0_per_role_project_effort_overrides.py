"""per_role_project_effort_overrides

Revision ID: n5o6p7q8r9s0
Revises: m4n5o6p7q8r9
Create Date: 2026-07-26

Each per-role model override gains a reasoning-effort sibling, so a project can
say "flows run on Sonnet at low" and not just "flows run on Sonnet". NULL means
inherit the profile's effort, which itself defaults to what the role is worth.

Chats gain their own effort for the same reason they own their model: the model
picker used to write a GLOBAL per-model reasoning level, so turning one chat up
to Max turned every chat on that model up with it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'n5o6p7q8r9s0'
down_revision: Union[str, Sequence[str], None] = 'm4n5o6p7q8r9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


EFFORT_COLUMNS = (
    'chat_effort',
    'quick_task_effort',
    'tool_assistant_effort',
    'flow_effort',
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    columns = {col['name'] for col in inspector.get_columns('projects')}
    for name in EFFORT_COLUMNS:
        if name not in columns:
            op.add_column('projects', sa.Column(name, sa.String(), nullable=True))

    chat_columns = {col['name'] for col in inspector.get_columns('chats')}
    if 'reasoning_effort' not in chat_columns:
        op.add_column('chats', sa.Column('reasoning_effort', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('chats', 'reasoning_effort')
    for name in EFFORT_COLUMNS:
        op.drop_column('projects', name)
