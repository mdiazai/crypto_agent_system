"""add chain to token_candidates

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-18 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE token_candidates ADD COLUMN IF NOT EXISTS chain VARCHAR(16)"
    )


def downgrade() -> None:
    op.drop_column("token_candidates", "chain")
