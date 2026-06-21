"""add diagnostics_log table

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-06 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "diagnostics_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "run_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("diagnosis", sa.Text, nullable=False),
        sa.Column("fix_command", sa.Text, nullable=True),
        sa.Column("approved", sa.Boolean, nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_diagnostics_log_run_at", "diagnostics_log", ["run_at"])


def downgrade() -> None:
    op.drop_index("ix_diagnostics_log_run_at", table_name="diagnostics_log")
    op.drop_table("diagnostics_log")
