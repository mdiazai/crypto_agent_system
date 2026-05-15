from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, func

from shared.config import settings
from shared.models import EntryQuality, Trade, TradeDirection, get_session
from agents.dashboard.auth import get_current_user

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("/metrics")
async def performance_metrics(_: dict = Depends(get_current_user)):
    async with get_session() as session:
        # ── Total trades (buy side) ───────────────────────────────────────────
        total_trades: int = (
            await session.execute(
                select(func.count(Trade.id)).where(Trade.direction == TradeDirection.buy)
            )
        ).scalar_one()

        # ── Win rate (closed trades with pnl_usd > 0) ────────────────────────
        closed = (
            await session.execute(
                select(Trade).where(
                    Trade.direction == TradeDirection.buy,
                    Trade.exit_price.is_not(None),
                    Trade.pnl_usd.is_not(None),
                )
            )
        ).scalars().all()

        wins = [t for t in closed if t.pnl_usd and t.pnl_usd > 0]
        win_rate = len(wins) / len(closed) if closed else 0.0

        # ── Days operating (from first trade entry) ───────────────────────────
        first_entry: datetime | None = (
            await session.execute(
                select(func.min(Trade.entry_time)).where(Trade.direction == TradeDirection.buy)
            )
        ).scalar_one()

        days_operating = 0
        if first_entry:
            if first_entry.tzinfo is None:
                first_entry = first_entry.replace(tzinfo=timezone.utc)
            days_operating = (datetime.now(timezone.utc) - first_entry).days

        # ── Avg anticipation minutes (oldest alert → trade entry_time) ────────
        all_trades = (
            await session.execute(
                select(Trade).where(Trade.direction == TradeDirection.buy)
            )
        ).scalars().all()

        anticipation_list: list[float] = [
            t.anticipation_minutes
            for t in all_trades
            if t.anticipation_minutes is not None
        ]

        avg_anticipation_minutes = (
            sum(anticipation_list) / len(anticipation_list) if anticipation_list else 0.0
        )

        # ── Classic fail rate ─────────────────────────────────────────────────
        classic_trades = (
            await session.execute(
                select(Trade).where(
                    Trade.direction == TradeDirection.buy,
                    Trade.pattern_detected == "classic",
                )
            )
        ).scalars().all()

        classic_fails = sum(
            1 for t in classic_trades
            if t.entry_quality in (EntryQuality.bad, EntryQuality.late)
        )
        classic_fail_rate = classic_fails / len(classic_trades) if classic_trades else 0.0

    capital_usd = settings.capital_total_usd
    glassnode_cost_pct = (99.0 / capital_usd) * 100.0 if capital_usd > 0 else 0.0

    return {
        "win_rate": round(win_rate, 4),
        "total_trades": total_trades,
        "days_operating": days_operating,
        "avg_anticipation_minutes": round(avg_anticipation_minutes, 1),
        "classic_fail_rate": round(classic_fail_rate, 4),
        "capital_usd": capital_usd,
        "paper_trading": settings.paper_trading,
        "glassnode_cost_pct": round(glassnode_cost_pct, 2),
    }
