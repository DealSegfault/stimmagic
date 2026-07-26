"""per_role_project_model_overrides

Revision ID: m4n5o6p7q8r9
Revises: l3m4n5o6p7q8
Create Date: 2026-07-25

Projects used to carry a single `default_model_slug`, which only ever applied to
chats. Each LLM role (chats, quick tasks, tool assistant, flows) is now
separately overridable per project, so the column is renamed to say which role
it governs and three siblings join it. NULL means inherit the profile setting.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'm4n5o6p7q8r9'
down_revision: Union[str, Sequence[str], None] = 'l3m4n5o6p7q8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_COLUMNS = (
    'quick_task_model_slug',
    'tool_assistant_model_slug',
    'flow_model_slug',
)


def upgrade() -> None:
    connection = op.get_bind()
    columns = {col['name'] for col in sa.inspect(connection).get_columns('projects')}

    if 'default_model_slug' in columns and 'chat_model_slug' not in columns:
        op.alter_column(
            'projects',
            'default_model_slug',
            new_column_name='chat_model_slug',
            existing_type=sa.String(),
            existing_nullable=True,
        )
    elif 'chat_model_slug' not in columns:
        op.add_column('projects', sa.Column('chat_model_slug', sa.String(), nullable=True))

    for name in NEW_COLUMNS:
        if name not in columns:
            op.add_column('projects', sa.Column(name, sa.String(), nullable=True))


def downgrade() -> None:
    for name in NEW_COLUMNS:
        op.drop_column('projects', name)
    op.alter_column(
        'projects',
        'chat_model_slug',
        new_column_name='default_model_slug',
        existing_type=sa.String(),
        existing_nullable=True,
    )
