"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── ENUMS (idempotent via exception handling) ─────────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE token_status AS ENUM ('active', 'removed');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE pattern_type AS ENUM ('long_pump', 'classic', 'unknown');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE trade_direction AS ENUM ('buy', 'sell');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE entry_quality AS ENUM ('perfect', 'good', 'early', 'late', 'bad');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # ── token_candidates ─────────────────────────────────────────────────────
    op.create_table(
        "token_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("exchange", sa.String(32), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", postgresql.ENUM("active", "removed", name="token_status", create_type=False), nullable=False),
        sa.Column("detection_score", sa.Float(), nullable=True),
        sa.Column("pattern_type", postgresql.ENUM("long_pump", "classic", "unknown", name="pattern_type", create_type=False), nullable=False),
        sa.Column("holder_concentration_pct", sa.Float(), nullable=True),
        sa.Column("inflow_usd", sa.Float(), nullable=True),
        sa.Column("alert_sent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_token_candidates"),
    )
    op.create_index("ix_token_candidates_symbol", "token_candidates", ["symbol"])
    op.create_index("ix_token_candidates_status", "token_candidates", ["status"])

    # ── trades ───────────────────────────────────────────────────────────────
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token_symbol", sa.String(32), nullable=False),
        sa.Column("exchange", sa.String(32), nullable=False),
        sa.Column("direction", postgresql.ENUM("buy", "sell", name="trade_direction", create_type=False), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("capital_used_usd", sa.Float(), nullable=False),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pnl_usd", sa.Float(), nullable=True),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("pattern_detected", sa.String(32), nullable=True),
        sa.Column("entry_quality", postgresql.ENUM("perfect", "good", "early", "late", "bad", name="entry_quality", create_type=False), nullable=True),
        sa.Column("score_at_entry", sa.Float(), nullable=True),
        sa.Column("is_paper", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id", name="pk_trades"),
    )
    op.create_index("ix_trades_token_symbol", "trades", ["token_symbol"])

    # ── alerts ───────────────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token_symbol", sa.String(32), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("pattern_type", sa.String(32), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_alerts"),
    )
    op.create_index("ix_alerts_token_symbol", "alerts", ["token_symbol"])
    op.create_index("ix_alerts_sent_at", "alerts", ["sent_at"])

    # ── learning_logs ────────────────────────────────────────────────────────
    op.create_table(
        "learning_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tokens_evaluated", sa.Integer(), nullable=False),
        sa.Column("accuracy_rate", sa.Float(), nullable=True),
        sa.Column("avg_entry_quality", sa.Float(), nullable=True),
        sa.Column("weights_adjusted", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_learning_logs"),
    )
    op.create_index("ix_learning_logs_created_at", "learning_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("learning_logs")
    op.drop_table("alerts")
    op.drop_table("trades")
    op.drop_table("token_candidates")

    op.execute("DROP TYPE IF EXISTS entry_quality")
    op.execute("DROP TYPE IF EXISTS trade_direction")
    op.execute("DROP TYPE IF EXISTS pattern_type")
    op.execute("DROP TYPE IF EXISTS token_status")
