"""Repair self-referential image-editor lineage traces.

Revision ID: r9s0t1u2v3w4
Revises: q8r9s0t1u2v3
Create Date: 2026-08-02

Image-editor saves briefly wrote the output Media id into its own
``lineage_trace`` as a synthetic ``image-to-image`` ancestor. The relational
``media_lineage`` edge remained correct, so rebuild only that exact malformed
shape from the recorded parent and its generation metadata.
"""

import json
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "r9s0t1u2v3w4"
down_revision = "q8r9s0t1u2v3"
branch_labels = None
depends_on = None

IMAGE_EDITOR_TOOL_ID = "builtin:stimma:image-editor"


def _parse_metadata(raw: Any) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parent_entry(parent: dict, metadata: dict) -> dict:
    parameters = dict(metadata.get("parameters") or {})
    if parameters.get("seed") is None and metadata.get("seed") is not None:
        parameters["seed"] = metadata["seed"]

    generated_at = metadata.get("generated_at")
    if generated_at is None and parent.get("created_date") is not None:
        created_date = parent["created_date"]
        generated_at = (
            created_date.isoformat() + "Z"
            if hasattr(created_date, "isoformat")
            else str(created_date)
        )

    entry = {
        "media_id": parent["id"],
        "task_type": metadata.get("task_type"),
        "tool_id": metadata.get("tool_id"),
        "model": metadata.get("model"),
        "generator": metadata.get("generator"),
        "prompt": metadata.get("prompt"),
        "negative_prompt": metadata.get("negative_prompt"),
        "parameters": parameters,
        "generated_at": generated_at,
        "source_inputs": (
            metadata.get("source_inputs")
            if isinstance(metadata.get("source_inputs"), list)
            else []
        ),
    }
    if metadata.get("seed") is not None:
        entry["seed"] = metadata["seed"]
    return entry


def upgrade() -> None:
    connection = op.get_bind()
    children = list(connection.execute(
        sa.text(
            "SELECT id, generation_metadata FROM media_items "
            "WHERE tool_id = :tool_id AND generation_metadata IS NOT NULL "
            "ORDER BY id"
        ),
        {"tool_id": IMAGE_EDITOR_TOOL_ID},
    ).mappings())

    for child in children:
        metadata = _parse_metadata(child["generation_metadata"])
        trace = metadata.get("lineage_trace")
        if not (
            isinstance(trace, list)
            and len(trace) == 1
            and isinstance(trace[0], dict)
            and trace[0].get("media_id") == child["id"]
            and trace[0].get("task_type") == "image-to-image"
            and isinstance(trace[0].get("source_media_ids"), list)
        ):
            continue

        parent = connection.execute(
            sa.text(
                "SELECT mi.id, mi.created_date, mi.generation_metadata "
                "FROM media_lineage ml "
                "JOIN media_items mi ON mi.id = ml.source_media_id "
                "WHERE ml.media_id = :child_id "
                "ORDER BY ml.source_order LIMIT 1"
            ),
            {"child_id": child["id"]},
        ).mappings().first()
        if parent is None:
            continue

        parent_metadata = _parse_metadata(parent["generation_metadata"])
        inherited = [
            dict(entry)
            for entry in (parent_metadata.get("lineage_trace") or [])
            if isinstance(entry, dict) and entry.get("media_id") != parent["id"]
        ]
        inherited.append(_parent_entry(parent, parent_metadata))
        metadata["lineage_trace"] = inherited
        connection.execute(
            sa.text(
                "UPDATE media_items SET generation_metadata = :metadata "
                "WHERE id = :media_id"
            ),
            {
                "media_id": child["id"],
                "metadata": json.dumps(metadata),
            },
        )


def downgrade() -> None:
    # Restoring corrupt self-references would destroy recovered provenance.
    pass
