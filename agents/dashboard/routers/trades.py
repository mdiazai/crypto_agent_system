from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, func, update
from datetime import datetime, timezone
from typing import Optional

from shared.models import Trade, TradeDirection, get_session
from shared.config import settings
from shared.redis_bus import bus, Channel
from agents.dashboard.auth import get_current_user
from agents.dashboard.schemas import (
    TradeResponse, TradeSummaryResponse, ManualTradeRequest, MessageResponse,
)

router = APIRouter(prefix="/trades", tags=["trades"])


def _trade_to_response(t: Trade) -> TradeResponse:
    return TradeResponse(
        id=t.id,
        token_symbol=t.token_symbol,
        exchange=t.exchange,
        direction=str(t.direction),
        entry_price=t.entry_price,
        exit_price=t.exit_price,
        quantity=t.quantity,
        capital_used_usd=t.capital_used_usd,
        entry_time=t.entry_time,
        exit_time=t.exit_time,
        pnl_usd=t.pnl_usd,
        pnl_pct=t.pnl_pct,
        pattern_detected=t.pattern_detected,
        entry_quality=str(t.entry_quality) if t.entry_quality else None,
        score_at_entry=t.score_at_entry,
        is_paper=t.is_paper,
    )


@router.get("", response_model=list[TradeResponse])
async def list_trades(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    symbol: Optional[str] = Query(None),
    exchange: Optional[str] = Query(None),
    is_paper: Optional[bool] = Query(None),
    open_only: bool = Query(False),
    _: dict = Depends(get_current_user),
):
    """Historial de trades con paginación y filtros."""
    offset = (page - 1) * page_size
    async with get_session() as session:
        query = (
            select(Trade)
            .where(Trade.direction == TradeDirection.buy)
            .order_by(desc(Trade.entry_time))
            .offset(offset)
            .limit(page_size)
        )
        if symbol:
            query = query.where(Trade.token_symbol == symbol.upper())
        if exchange:
            query = query.where(Trade.exchange == exchange)
        if is_paper is not None:
            query = query.where(Trade.is_paper == is_paper)
        if open_only:
            query = query.where(Trade.exit_price.is_(None))

        rows = (await session.execute(query)).scalars().all()

    return [_trade_to_response(t) for t in rows]


@router.get("/summary", response_model=TradeSummaryResponse)
async def trades_summary(
    is_paper: Optional[bool] = Query(None),
    _: dict = Depends(get_current_user),
):
    """P&L total, win rate y estadísticas agregadas."""
    async with get_session() as session:
        query = select(Trade).where(
            Trade.direction == TradeDirection.buy,
            Trade.exit_price.is_not(None),
        )
        if is_paper is not None:
            query = query.where(Trade.is_paper == is_paper)

        closed = (await session.execute(query)).scalars().all()

        open_query = select(func.count(Trade.id)).where(
            Trade.direction == TradeDirection.buy,
            Trade.exit_price.is_(None),
        )
        if is_paper is not None:
            open_query = open_query.where(Trade.is_paper == is_paper)
        open_count = (await session.execute(open_query)).scalar_one()

    wins = [t for t in closed if t.pnl_usd and t.pnl_usd > 0]
    total_pnl = sum(t.pnl_usd for t in closed if t.pnl_usd)
    pnl_pcts = [t.pnl_pct for t in closed if t.pnl_pct is not None]

    return TradeSummaryResponse(
        total_trades=len(closed) + open_count,
        open_trades=open_count,
        closed_trades=len(closed),
        win_rate=len(wins) / len(closed) if closed else 0.0,
        total_pnl_usd=total_pnl,
        avg_pnl_pct=sum(pnl_pcts) / len(pnl_pcts) if pnl_pcts else 0.0,
        best_trade_pct=max(pnl_pcts) if pnl_pcts else None,
        worst_trade_pct=min(pnl_pcts) if pnl_pcts else None,
        is_paper=is_paper if is_paper is not None else settings.paper_trading,
    )


@router.post("/execute", response_model=MessageResponse, status_code=202)
async def manual_execute(
    req: ManualTradeRequest,
    _: dict = Depends(get_current_user),
):
    """
    Encola una orden de trade manual vía Redis.
    El Executor la procesará en su próximo ciclo.
    """
    await bus.publish(Channel.DETECTOR_SCORED_TOKEN, {
        "symbol": req.symbol.upper(),
        "exchange": req.exchange,
        "composite_score": 100.0,        # override manual siempre ejecuta
        "dominant_pattern": "manual",
        "above_alert_threshold": True,
        "current_price": 0.0,
        "long_pump": {"score": 0.0},
        "classic_squeeze": {"score": 0.0},
        "_manual_override": True,
        "_capital_override_usd": req.capital_usd,
    })
    return MessageResponse(
        message=f"Orden manual encolada: {req.direction} {req.symbol.upper()} en {req.exchange}",
        detail={"capital_usd": req.capital_usd},
    )


@router.post("/{trade_id}/close", response_model=MessageResponse, status_code=202)
async def close_trade(
    trade_id: int,
    _: dict = Depends(get_current_user),
):
    """Solicita el cierre manual de una posición abierta."""
    async with get_session() as session:
        trade = (
            await session.execute(select(Trade).where(Trade.id == trade_id))
        ).scalar_one_or_none()

        if not trade:
            raise HTTPException(status_code=404, detail="Trade no encontrado")
        if trade.exit_price is not None:
            raise HTTPException(status_code=400, detail="Trade ya está cerrado")

    await bus.publish(Channel.EXECUTOR_TRADE_RESULT, {
        "_manual_close": True,
        "trade_id": trade_id,
        "symbol": trade.token_symbol,
        "exchange": trade.exchange,
    })
    return MessageResponse(
        message=f"Cierre manual solicitado para trade #{trade_id} ({trade.token_symbol})"
    )
