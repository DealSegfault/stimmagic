"""add canonical project production shots and attempts"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d1e2f3g4h5i6"
down_revision: Union[str, Sequence[str], None] = "c0d1e2f3g4h5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "project_shots" not in tables:
        op.create_table(
            "project_shots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("scene_id", sa.Integer(), sa.ForeignKey("project_scenes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("shot_number", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("source_key", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False, server_default="Plan 1"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("prompt", sa.Text(), nullable=True),
            sa.Column("duration", sa.Float(), nullable=False, server_default="4"),
            sa.Column("width", sa.Integer(), nullable=False, server_default="1344"),
            sa.Column("height", sa.Integer(), nullable=False, server_default="768"),
            sa.Column("transition_policy", sa.String(), nullable=False, server_default="continuity"),
            sa.Column("status", sa.String(), nullable=False, server_default="planned"),
            sa.Column("validation_status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("accepted_media_id", sa.Integer(), sa.ForeignKey("media_items.id", ondelete="SET NULL"), nullable=True),
            sa.Column("accepted_last_frame_media_id", sa.Integer(), sa.ForeignKey("media_items.id", ondelete="SET NULL"), nullable=True),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("references", sa.Text(), nullable=True),
            sa.Column("settings", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_project_shots_project_id", "project_shots", ["project_id"])
        op.create_index("ix_project_shots_scene_id", "project_shots", ["scene_id"])
        op.create_index("ix_project_shots_status", "project_shots", ["status"])
        op.create_index("ix_project_shots_validation_status", "project_shots", ["validation_status"])
        op.create_index("ix_project_shots_accepted_media_id", "project_shots", ["accepted_media_id"])
        op.create_index("ix_project_shots_accepted_last_frame_media_id", "project_shots", ["accepted_last_frame_media_id"])
        op.create_index("idx_project_shots_order", "project_shots", ["project_id", "scene_id", "shot_number"])
        op.create_index(
            "idx_project_shots_live_identity",
            "project_shots",
            ["project_id", "scene_id", "shot_number"],
            unique=True,
            sqlite_where=sa.text("deleted_at IS NULL"),
        )

    if "shot_attempts" not in tables:
        op.create_table(
            "shot_attempts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("shot_id", sa.Integer(), sa.ForeignKey("project_shots.id", ondelete="CASCADE"), nullable=False),
            sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("generation_job_id", sa.Integer(), sa.ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("idempotency_key", sa.String(), nullable=False, unique=True),
            sa.Column("status", sa.String(), nullable=False, server_default="queued"),
            sa.Column("prompt", sa.Text(), nullable=True),
            sa.Column("parameters", sa.Text(), nullable=True),
            sa.Column("reference_manifest", sa.Text(), nullable=True),
            sa.Column("validation", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("superseded_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_shot_attempts_project_id", "shot_attempts", ["project_id"])
        op.create_index("ix_shot_attempts_shot_id", "shot_attempts", ["shot_id"])
        op.create_index("ix_shot_attempts_generation_job_id", "shot_attempts", ["generation_job_id"])
        op.create_index("ix_shot_attempts_status", "shot_attempts", ["status"])
        op.create_index("idx_shot_attempts_shot_number", "shot_attempts", ["shot_id", "attempt_number"], unique=True)

    # Backfill exactly one explicit shot for every existing sequence. This is
    # intentionally conservative: it preserves history and makes no guesses
    # about how a Markdown scene should be split into multiple shots.
    op.execute(sa.text("""
        INSERT INTO project_shots (
            project_id, scene_id, shot_number, source_key, title, description,
            prompt, duration, width, height, transition_policy, status,
            validation_status, revision, created_at, updated_at
        )
        SELECT s.project_id, s.id, 1,
               'legacy:scene:' || CAST(s.id AS TEXT) || ':shot:1',
               'Plan 1 · ' || s.title, s.description, s.prompt,
               4.0, 1344, 768, 'continuity', s.status,
               s.validation_status, 1, s.created_at, s.updated_at
        FROM project_scenes s
        WHERE NOT EXISTS (
            SELECT 1 FROM project_shots p
            WHERE p.scene_id = s.id AND p.shot_number = 1 AND p.deleted_at IS NULL
        )
    """))


def downgrade() -> None:
    op.drop_table("shot_attempts")
    op.drop_table("project_shots")
