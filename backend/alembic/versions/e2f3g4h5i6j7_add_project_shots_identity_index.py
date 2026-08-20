"""enforce one live canonical shot identity per sequence"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f3g4h5i6j7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3g4h5i6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "project_shots" not in inspector.get_table_names():
        return
    index_names = {item["name"] for item in inspector.get_indexes("project_shots")}
    if "idx_project_shots_live_identity" not in index_names:
        op.create_index(
            "idx_project_shots_live_identity",
            "project_shots",
            ["project_id", "scene_id", "shot_number"],
            unique=True,
            sqlite_where=sa.text("deleted_at IS NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "project_shots" not in inspector.get_table_names():
        return
    index_names = {item["name"] for item in inspector.get_indexes("project_shots")}
    if "idx_project_shots_live_identity" in index_names:
        op.drop_index("idx_project_shots_live_identity", table_name="project_shots")
