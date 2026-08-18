"""add generic persisted agent run traces

Revision ID: c0d1e2f3g4h5
Revises: v6w7x8y9z0a1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c0d1e2f3g4h5"
down_revision: Union[str, Sequence[str], None] = "v6w7x8y9z0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "agent_runs" not in tables:
        op.create_table(
            "agent_runs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
            sa.Column("chat_id", sa.Integer(), sa.ForeignKey("chats.id", ondelete="SET NULL"), nullable=True),
            sa.Column("workflow", sa.String(), nullable=False, server_default="agent_chat"),
            sa.Column("mode", sa.String(), nullable=False, server_default="trace"),
            sa.Column("status", sa.String(), nullable=False, server_default="running"),
            sa.Column("request_summary", sa.Text(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        for name, cols in (
            ("ix_agent_runs_project_id", ["project_id"]),
            ("ix_agent_runs_chat_id", ["chat_id"]),
            ("ix_agent_runs_workflow", ["workflow"]),
            ("ix_agent_runs_mode", ["mode"]),
            ("ix_agent_runs_status", ["status"]),
            ("ix_agent_runs_started_at", ["started_at"]),
            ("idx_agent_runs_project_started", ["project_id", "started_at"]),
            ("idx_agent_runs_chat_started", ["chat_id", "started_at"]),
        ):
            op.create_index(name, "agent_runs", cols)

    if "agent_run_steps" not in tables:
        op.create_table(
            "agent_run_steps",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("run_id", sa.String(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("stage", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="running"),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("tool_call_id", sa.String(), nullable=True),
            sa.Column("generation_job_id", sa.Integer(), nullable=True),
            sa.Column("media_ids", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
            sa.PrimaryKeyConstraint("id"),
        )
        for name, cols in (
            ("ix_agent_run_steps_run_id", ["run_id"]),
            ("ix_agent_run_steps_stage", ["stage"]),
            ("ix_agent_run_steps_status", ["status"]),
            ("ix_agent_run_steps_tool_call_id", ["tool_call_id"]),
            ("ix_agent_run_steps_generation_job_id", ["generation_job_id"]),
            ("idx_agent_run_steps_run_sequence", ["run_id", "sequence"]),
            ("idx_agent_run_steps_run_status", ["run_id", "status"]),
        ):
            op.create_index(name, "agent_run_steps", cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "agent_run_steps" in tables:
        op.drop_table("agent_run_steps")
    if "agent_runs" in tables:
        op.drop_table("agent_runs")
