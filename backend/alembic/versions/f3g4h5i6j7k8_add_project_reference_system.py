"""add project reference packs, views, states and compositions

Revision ID: f3g4h5i6j7k8
Revises: e2f3g4h5i6j7
Create Date: 2026-08-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3g4h5i6j7k8"
down_revision: Union[str, None] = "e2f3g4h5i6j7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_reference_packs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("project_element_id", sa.Integer(), nullable=False),
        sa.Column("pack_type", sa.String(), nullable=False),
        sa.Column("identity_prompt", sa.Text(), nullable=True),
        sa.Column("negative_prompt", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sheet_asset_id", sa.Integer(), nullable=True),
        sa.Column("approved_sheet_revision_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_element_id"], ["project_elements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sheet_asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_sheet_revision_id"], ["asset_revisions.id"], ondelete="SET NULL"),
        sa.CheckConstraint("pack_type IN ('location', 'character', 'prop')", name="ck_project_reference_packs_type"),
        sa.CheckConstraint("status IN ('draft', 'generating', 'review', 'approved', 'stale', 'error')", name="ck_project_reference_packs_status"),
    )
    op.create_index("ix_project_reference_packs_id", "project_reference_packs", ["id"])
    op.create_index("ix_project_reference_packs_project_id", "project_reference_packs", ["project_id"])
    op.create_index("ix_project_reference_packs_project_element_id", "project_reference_packs", ["project_element_id"])
    op.create_index("ix_project_reference_packs_pack_type", "project_reference_packs", ["pack_type"])
    op.create_index("ix_project_reference_packs_sheet_asset_id", "project_reference_packs", ["sheet_asset_id"])
    op.create_index("ix_project_reference_packs_approved_sheet_revision_id", "project_reference_packs", ["approved_sheet_revision_id"])
    op.create_index("ix_project_reference_packs_status", "project_reference_packs", ["status"])
    op.create_index("ix_project_reference_packs_deleted_at", "project_reference_packs", ["deleted_at"])
    op.create_index("idx_project_reference_packs_project_type", "project_reference_packs", ["project_id", "pack_type"])
    op.create_index(
        "idx_project_reference_packs_live_element",
        "project_reference_packs",
        ["project_element_id"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "project_reference_views",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("pack_id", sa.Integer(), nullable=False),
        sa.Column("view_key", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("view_type", sa.String(), nullable=False, server_default="identity"),
        sa.Column("state_key", sa.String(), nullable=False, server_default="default"),
        sa.Column("view_spec", sa.Text(), nullable=True),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("approved_revision_id", sa.Integer(), nullable=True),
        sa.Column("candidate_media_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="missing"),
        sa.Column("source_signature", sa.String(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pack_id"], ["project_reference_packs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_revision_id"], ["asset_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["candidate_media_id"], ["media_items.id"], ondelete="SET NULL"),
        sa.CheckConstraint("view_type IN ('identity', 'location_camera', 'detail', 'scale')", name="ck_project_reference_views_type"),
        sa.CheckConstraint("status IN ('missing', 'generating', 'review', 'approved', 'stale', 'inconsistent', 'rejected', 'error')", name="ck_project_reference_views_status"),
    )
    for name in (
        "id", "project_id", "pack_id", "view_type", "state_key", "asset_id",
        "approved_revision_id", "candidate_media_id", "status", "source_signature", "deleted_at",
    ):
        op.create_index(f"ix_project_reference_views_{name}", "project_reference_views", [name])
    op.create_index("idx_project_reference_views_pack_order", "project_reference_views", ["pack_id", "sort_order"])
    op.create_index(
        "idx_project_reference_views_live_identity",
        "project_reference_views",
        ["pack_id", "view_key", "state_key"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "project_element_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("project_element_id", sa.Integer(), nullable=False),
        sa.Column("state_key", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("prompt_delta", sa.Text(), nullable=True),
        sa.Column("constraints", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_element_id"], ["project_elements.id"], ondelete="CASCADE"),
    )
    for name in ("id", "project_id", "project_element_id", "deleted_at"):
        op.create_index(f"ix_project_element_states_{name}", "project_element_states", [name])
    op.create_index("idx_project_element_states_project", "project_element_states", ["project_id", "project_element_id"])
    op.create_index(
        "idx_project_element_states_live_key",
        "project_element_states",
        ["project_element_id", "state_key"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "project_compositions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("location_view_id", sa.Integer(), nullable=False),
        sa.Column("base_location_revision_id", sa.Integer(), nullable=False),
        sa.Column("result_asset_id", sa.Integer(), nullable=True),
        sa.Column("approved_revision_id", sa.Integer(), nullable=True),
        sa.Column("candidate_media_id", sa.Integer(), nullable=True),
        sa.Column("placement_guide_media_id", sa.Integer(), nullable=True),
        sa.Column("prompt_delta", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_signature", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("validation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_view_id"], ["project_reference_views.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["base_location_revision_id"], ["asset_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["result_asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_revision_id"], ["asset_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["candidate_media_id"], ["media_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["placement_guide_media_id"], ["media_items.id"], ondelete="SET NULL"),
        sa.CheckConstraint("status IN ('draft', 'generating', 'review', 'approved', 'stale', 'inconsistent', 'rejected', 'error')", name="ck_project_compositions_status"),
    )
    for name in (
        "id", "project_id", "location_view_id", "base_location_revision_id",
        "result_asset_id", "approved_revision_id", "candidate_media_id",
        "placement_guide_media_id", "source_signature", "status", "deleted_at",
    ):
        op.create_index(f"ix_project_compositions_{name}", "project_compositions", [name])
    op.create_index("idx_project_compositions_location", "project_compositions", ["project_id", "location_view_id"])
    op.create_index(
        "idx_project_compositions_live_signature",
        "project_compositions",
        ["project_id", "source_signature"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "project_composition_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("composition_id", sa.Integer(), nullable=False),
        sa.Column("project_element_id", sa.Integer(), nullable=False),
        sa.Column("reference_view_id", sa.Integer(), nullable=False),
        sa.Column("source_revision_id", sa.Integer(), nullable=False),
        sa.Column("state_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(), nullable=False, server_default="prop"),
        sa.Column("placement", sa.Text(), nullable=True),
        sa.Column("item_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["composition_id"], ["project_compositions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_element_id"], ["project_elements.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reference_view_id"], ["project_reference_views.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_revision_id"], ["asset_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["state_id"], ["project_element_states.id"], ondelete="SET NULL"),
        sa.CheckConstraint("role IN ('prop', 'character', 'set_dressing')", name="ck_project_composition_items_role"),
    )
    for name in (
        "id", "composition_id", "project_element_id", "reference_view_id",
        "source_revision_id", "state_id", "deleted_at",
    ):
        op.create_index(f"ix_project_composition_items_{name}", "project_composition_items", [name])
    op.create_index("idx_project_composition_items_order", "project_composition_items", ["composition_id", "item_order"])


def downgrade() -> None:
    op.drop_table("project_composition_items")
    op.drop_table("project_compositions")
    op.drop_table("project_element_states")
    op.drop_table("project_reference_views")
    op.drop_table("project_reference_packs")
