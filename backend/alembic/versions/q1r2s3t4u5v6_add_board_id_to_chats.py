"""associate chats with boards

Revision ID: q1r2s3t4u5v6
Revises: p7q8r9s0t1u2
Create Date: 2026-08-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "q1r2s3t4u5v6"
down_revision: Union[str, Sequence[str], None] = "p7q8r9s0t1u2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("chats")}
    indexes = {index.get("name") for index in inspector.get_indexes("chats")}

    if "board_id" not in columns:
        with op.batch_alter_table("chats") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "board_id",
                    sa.Integer(),
                    sa.ForeignKey(
                        "boards.id",
                        name="fk_chats_board_id_boards",
                        ondelete="SET NULL",
                    ),
                    nullable=True,
                )
            )
    if "ix_chats_board_id" not in indexes:
        op.create_index("ix_chats_board_id", "chats", ["board_id"])


def downgrade() -> None:
    op.drop_index("ix_chats_board_id", table_name="chats")
    with op.batch_alter_table("chats") as batch_op:
        batch_op.drop_column("board_id")
