"""
Router del dashboard para el Narrative Swing Module — candidatos, trades
paper y progreso hacia el gate de produccion.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, func

from shared.config import settings
from shared.models import NarrativeCandidate, NarrativeTrade, NarrativeTradeStatus, get_session
from agents.dashboard.auth import get_current_user
from agents.dashboard.schemas import NarrativeCandidateResponse, NarrativeTradeResponse, NarrativeGateResponse

router = APIRouter(prefix="/narrative", tags=["narrative"])


@router.get("/candidates", response_model=list[NarrativeCandidateResponse])
async def list_candidates(_: dict = Depends(get_current_user)):
    """Ultimo score de cada token del universo, ordenado por combined_score."""
    async with get_session() as session:
        rows = (
            await session.execute(
                select(NarrativeCandidate).order_by(NarrativeCandidate.combined_score.desc().nulls_last())
            )
        ).scalars().all()

    return [
        NarrativeCandidateResponse(
            symbol=r.symbol,
            exchange=r.exchange,
            narrative_score=r.narrative_score,
            onchain_score=r.onchain_score,
            technical_score=r.technical_score,
            combined_score=r.combined_score,
            narrative_description=r.narrative_description,
            galaxy_score=r.galaxy_score,
            alt_rank=r.alt_rank,
            smart_money_netflow=r.smart_money_netflow,
            holder_concentration=r.holder_concentration,
            rsi_1d=r.rsi_1d,
            price_usd=r.price_usd,
            status=r.status.value,
            last_checked=r.last_checked,
        )
        for r in rows
    ]


@router.get("/trades", response_model=list[NarrativeTradeResponse])
async def list_trades(_: dict = Depends(get_current_user)):
    """Trades paper del Narrative Swing Module, abiertos y cerrados."""
    async with get_session() as session:
        rows = (
            await session.execute(select(NarrativeTrade).order_by(NarrativeTrade.entry_time.desc()))
        ).scalars().all()

    return [
        NarrativeTradeResponse(
            id=r.id,
            symbol=r.symbol,
            direction=r.direction.value,
            entry_price=r.entry_price,
            exit_price=r.exit_price,
            quantity=r.quantity,
            capital_usd=r.capital_usd,
            stop_loss_price=r.stop_loss_price,
            target1_price=r.target1_price,
            target2_price=r.target2_price,
            entry_score=r.entry_score,
            pnl_usd=r.pnl_usd,
            pnl_pct=r.pnl_pct,
            is_paper=r.is_paper,
            status=r.status.value,
            close_reason=r.close_reason,
            entry_time=r.entry_time,
            exit_time=r.exit_time,
        )
        for r in rows
    ]


@router.get("/gate", response_model=NarrativeGateResponse)
async def gate_progress(_: dict = Depends(get_current_user)):
    """Progreso hacia el gate de produccion (30 dias, 10 trades, 55% WR, PF 1.3)."""
    async with get_session() as session:
        first_checked = (
            await session.execute(select(func.min(NarrativeCandidate.created_at)))
        ).scalar_one_or_none()

        closed = (
            await session.execute(
                select(NarrativeTrade).where(NarrativeTrade.status == NarrativeTradeStatus.closed)
            )
        ).scalars().all()

    days_elapsed = 0
    if first_checked is not None:
        ref = first_checked if first_checked.tzinfo else first_checked.replace(tzinfo=timezone.utc)
        days_elapsed = max(0, (datetime.now(timezone.utc) - ref).days)

    trades_closed = len(closed)
    wins = [t for t in closed if (t.pnl_usd or 0) > 0]
    losses = [t for t in closed if (t.pnl_usd or 0) < 0]
    win_rate = (len(wins) / trades_closed) if trades_closed else 0.0

    gross_profit = sum(t.pnl_usd for t in wins) if wins else 0.0
    gross_loss = abs(sum(t.pnl_usd for t in losses)) if losses else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float(gross_profit > 0) and 999.0 or 0.0)

    days_required = settings.narrative_paper_trading_days
    trades_required = settings.narrative_min_trades_gate
    win_rate_required = settings.narrative_min_win_rate
    profit_factor_required = settings.narrative_min_profit_factor

    passed = (
        days_elapsed >= days_required
        and trades_closed >= trades_required
        and win_rate >= win_rate_required
        and profit_factor >= profit_factor_required
    )

    return NarrativeGateResponse(
        days_elapsed=days_elapsed,
        days_required=days_required,
        trades_closed=trades_closed,
        trades_required=trades_required,
        win_rate=round(win_rate, 4),
        win_rate_required=win_rate_required,
        profit_factor=round(profit_factor, 2),
        profit_factor_required=profit_factor_required,
        gate_status="passed" if passed else "in_progress",
    )
