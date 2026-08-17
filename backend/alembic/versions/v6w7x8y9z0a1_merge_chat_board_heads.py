"""merge chat board association migration heads

Revision ID: v6w7x8y9z0a1
Revises: q1r2s3t4u5v6, t1u2v3w4x5y6
Create Date: 2026-08-17

The board association migration is kept as a merge point because the workspace
already contains a project-elements branch from the same historical base.
"""

from typing import Sequence, Union


revision: str = "v6w7x8y9z0a1"
down_revision: Union[str, Sequence[str], None] = (
    "q1r2s3t4u5v6",
    "t1u2v3w4x5y6",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
