"""per_role_project_effort_overrides

Revision ID: n5o6p7q8r9s0
Revises: m4n5o6p7q8r9
Create Date: 2026-07-26

Each per-role model override gains a reasoning-effort sibling, so a project can
say "flows run on Sonnet at low" and not just "flows run on Sonnet". NULL means
inherit the profile's effort, which itself defaults to what the role is worth.
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
    connection = op.get_bind()
    columns = {col['name'] for col in sa.inspect(connection).get_columns('projects')}
    for name in EFFORT_COLUMNS:
        if name not in columns:
            op.add_column('projects', sa.Column(name, sa.String(), nullable=True))


def downgrade() -> None:
    for name in EFFORT_COLUMNS:
        op.drop_column('projects', name)
