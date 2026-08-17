"""add_project_direction

Revision ID: s1t2u3v4w5x6
Revises: r9s0t1u2v3w4
"""
from alembic import op
import sqlalchemy as sa

revision = "s1t2u3v4w5x6"
down_revision = "r9s0t1u2v3w4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("project_directions", sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True), sa.Column("script_name", sa.String(), nullable=True), sa.Column("script_text", sa.Text(), nullable=False, server_default=""), sa.Column("summary", sa.Text(), nullable=True), sa.Column("context", sa.Text(), nullable=True), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("project_scenes", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("board_id", sa.Integer(), sa.ForeignKey("boards.id", ondelete="SET NULL"), nullable=True), sa.Column("sequence_number", sa.Integer(), nullable=False, server_default="1"), sa.Column("scene_number", sa.Integer(), nullable=False, server_default="1"), sa.Column("title", sa.String(), nullable=False), sa.Column("description", sa.Text(), nullable=True), sa.Column("prompt", sa.Text(), nullable=True), sa.Column("context", sa.Text(), nullable=True), sa.Column("dependencies", sa.Text(), nullable=True), sa.Column("blockers", sa.Text(), nullable=True), sa.Column("status", sa.String(), nullable=False, server_default="planned"), sa.Column("validation_status", sa.String(), nullable=False, server_default="pending"), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_index("ix_project_scenes_project_id", "project_scenes", ["project_id"]); op.create_index("ix_project_scenes_board_id", "project_scenes", ["board_id"]); op.create_index("idx_project_scenes_order", "project_scenes", ["project_id", "sequence_number", "scene_number"])
    op.create_table("project_direction_events", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("scene_id", sa.Integer(), sa.ForeignKey("project_scenes.id", ondelete="SET NULL"), nullable=True), sa.Column("chat_id", sa.Integer(), sa.ForeignKey("chats.id", ondelete="SET NULL"), nullable=True), sa.Column("generation_job_id", sa.Integer(), sa.ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True), sa.Column("kind", sa.String(), nullable=False), sa.Column("actor", sa.String(), nullable=False, server_default="user"), sa.Column("payload", sa.Text(), nullable=True), sa.Column("created_at", sa.DateTime(), nullable=False))
    for name, cols in (("ix_project_direction_events_project_id", ["project_id"]), ("ix_project_direction_events_scene_id", ["scene_id"]), ("ix_project_direction_events_chat_id", ["chat_id"]), ("ix_project_direction_events_generation_job_id", ["generation_job_id"])): op.create_index(name, "project_direction_events", cols)


def downgrade() -> None:
    op.drop_table("project_direction_events"); op.drop_table("project_scenes"); op.drop_table("project_directions")
