"""add contract_address to token_candidates

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-14 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE token_candidates ADD COLUMN IF NOT EXISTS contract_address TEXT"
    )


def downgrade() -> None:
    op.drop_column("token_candidates", "contract_address")
