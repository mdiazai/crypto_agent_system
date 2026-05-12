"""add volume_24h_usd to token_candidates

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-11 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "token_candidates",
        sa.Column("volume_24h_usd", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("token_candidates", "volume_24h_usd")
