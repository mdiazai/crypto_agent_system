"""add score_breakdown to token_candidates

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-13 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE token_candidates ADD COLUMN IF NOT EXISTS score_breakdown TEXT"
    )


def downgrade() -> None:
    op.drop_column("token_candidates", "score_breakdown")
