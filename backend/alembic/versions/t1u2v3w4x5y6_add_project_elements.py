"""add_project_elements

Revision ID: t1u2v3w4x5y6
Revises: s1t2u3v4w5x6
"""

from alembic import op
import sqlalchemy as sa


revision = "t1u2v3w4x5y6"
down_revision = "s1t2u3v4w5x6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_elements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            sa.Integer(),
            sa.ForeignKey("assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("element_type", sa.String(), nullable=False, server_default="prop"),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("reference_id", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "element_type IN ('location', 'character', 'prop')",
            name="ck_project_elements_type",
        ),
    )
    op.create_index("ix_project_elements_id", "project_elements", ["id"])
    op.create_index(
        "ix_project_elements_project_id", "project_elements", ["project_id"]
    )
    op.create_index("ix_project_elements_asset_id", "project_elements", ["asset_id"])
    op.create_index(
        "ix_project_elements_element_type", "project_elements", ["element_type"]
    )
    op.create_index(
        "ix_project_elements_deleted_at", "project_elements", ["deleted_at"]
    )
    op.create_index(
        "idx_project_elements_project_type",
        "project_elements",
        ["project_id", "element_type"],
    )
    op.create_index(
        "idx_project_elements_live_reference",
        "project_elements",
        ["project_id", "reference_id"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("project_elements")
