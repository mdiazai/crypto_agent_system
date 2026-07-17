"""add narrative_candidates and narrative_trades tables (Narrative Swing Module)

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-12 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "narrative_candidates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("exchange", sa.String(32), nullable=False, server_default="spot"),
        sa.Column("narrative_score", sa.Float, nullable=True),
        sa.Column("onchain_score", sa.Float, nullable=True),
        sa.Column("technical_score", sa.Float, nullable=True),
        sa.Column("combined_score", sa.Float, nullable=True),
        sa.Column("narrative_description", sa.Text, nullable=True),
        sa.Column("galaxy_score", sa.Float, nullable=True),
        sa.Column("alt_rank", sa.Integer, nullable=True),
        sa.Column("social_volume_24h", sa.BigInteger, nullable=True),
        sa.Column("panic_score", sa.Float, nullable=True),
        sa.Column("latest_news", sa.Text, nullable=True),
        sa.Column("smart_money_netflow", sa.Float, nullable=True),
        sa.Column("holder_concentration", sa.Float, nullable=True),
        sa.Column("rsi_1d", sa.Float, nullable=True),
        sa.Column("volume_24h_usd", sa.Float, nullable=True),
        sa.Column("price_usd", sa.Float, nullable=True),
        sa.Column(
            "status",
            sa.Enum("candidate", "alerted", "entered", "archived", name="narrative_candidate_status"),
            nullable=False,
            server_default="candidate",
        ),
        sa.Column("alert_sent", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("last_checked", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_narrative_candidates_symbol", "narrative_candidates", ["symbol"])
    op.create_index("ix_narrative_candidates_combined_score", "narrative_candidates", ["combined_score"])
    op.create_index("ix_narrative_candidates_status", "narrative_candidates", ["status"])

    op.create_table(
        "narrative_trades",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column(
            "direction",
            sa.Enum("buy", "sell", name="narrative_trade_direction"),
            nullable=False,
            server_default="buy",
        ),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("exit_price", sa.Float, nullable=True),
        sa.Column("quantity", sa.Float, nullable=False),
        sa.Column("capital_usd", sa.Float, nullable=False),
        sa.Column("stop_loss_price", sa.Float, nullable=True),
        sa.Column("target1_price", sa.Float, nullable=True),
        sa.Column("target2_price", sa.Float, nullable=True),
        sa.Column("entry_score", sa.Float, nullable=True),
        sa.Column("narrative_at_entry", sa.Text, nullable=True),
        sa.Column("pnl_usd", sa.Float, nullable=True),
        sa.Column("pnl_pct", sa.Float, nullable=True),
        sa.Column("is_paper", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "status",
            sa.Enum("open", "closed", name="narrative_trade_status"),
            nullable=False,
            server_default="open",
        ),
        sa.Column("open_reason", sa.Text, nullable=True),
        sa.Column("close_reason", sa.Text, nullable=True),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("educational_note", sa.Text, nullable=True),
    )
    op.create_index("ix_narrative_trades_symbol", "narrative_trades", ["symbol"])
    op.create_index("ix_narrative_trades_status", "narrative_trades", ["status"])


def downgrade() -> None:
    op.drop_index("ix_narrative_trades_status", table_name="narrative_trades")
    op.drop_index("ix_narrative_trades_symbol", table_name="narrative_trades")
    op.drop_table("narrative_trades")
    op.execute("DROP TYPE IF EXISTS narrative_trade_status")
    op.execute("DROP TYPE IF EXISTS narrative_trade_direction")

    op.drop_index("ix_narrative_candidates_status", table_name="narrative_candidates")
    op.drop_index("ix_narrative_candidates_combined_score", table_name="narrative_candidates")
    op.drop_index("ix_narrative_candidates_symbol", table_name="narrative_candidates")
    op.drop_table("narrative_candidates")
    op.execute("DROP TYPE IF EXISTS narrative_candidate_status")
