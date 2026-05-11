"""
Mantiene el estado de posiciones abiertas en memoria.
Al arrancar, recarga posiciones sin cerrar desde PostgreSQL.
"""
from datetime import datetime, timezone
from typing import Optional
import structlog
from sqlalchemy import select

from shared.models import Trade, TradeDirection, get_session
from shared.config import settings
from .schemas import PositionState, TakeProfitLevel
from .risk_manager import RiskManager

log = structlog.get_logger(__name__)

# clave compuesta: (symbol, exchange)
PositionKey = tuple[str, str]


class PositionTracker:
    def __init__(self, risk_manager: RiskManager) -> None:
        self._positions: dict[PositionKey, PositionState] = {}
        self._risk = risk_manager

    async def load_from_db(self) -> None:
        """Recarga posiciones abiertas (exit_price IS NULL) desde la DB al arrancar."""
        async with get_session() as session:
            rows = (
                await session.execute(
                    select(Trade).where(
                        Trade.direction == TradeDirection.buy,
                        Trade.exit_price.is_(None),
                        Trade.is_paper == settings.paper_trading,
                    )
                )
            ).scalars().all()

        for trade in rows:
            sl_price = self._risk.calc_stop_loss_price(trade.entry_price)
            tp_levels = self._risk.build_take_profit_levels(trade.quantity)
            position = PositionState(
                trade_id=trade.id,
                symbol=trade.token_symbol,
                exchange=trade.exchange,
                entry_price=trade.entry_price,
                total_quantity=trade.quantity,
                remaining_quantity=trade.quantity,
                capital_usd=trade.capital_used_usd,
                stop_loss_price=sl_price,
                take_profit_levels=tp_levels,
                opened_at=trade.entry_time,
                is_paper=trade.is_paper,
                score_at_entry=trade.score_at_entry or 0.0,
                pattern_detected=trade.pattern_detected or "",
            )
            key: PositionKey = (trade.token_symbol, trade.exchange)
            self._positions[key] = position

        log.info("position_tracker.loaded", count=len(self._positions))

    def has_position(self, symbol: str, exchange: str) -> bool:
        return (symbol, exchange) in self._positions

    def open(self, position: PositionState) -> None:
        key: PositionKey = (position.symbol, position.exchange)
        self._positions[key] = position
        log.info(
            "position_tracker.opened",
            symbol=position.symbol,
            exchange=position.exchange,
            entry=position.entry_price,
            qty=position.total_quantity,
        )

    def get(self, symbol: str, exchange: str) -> Optional[PositionState]:
        return self._positions.get((symbol, exchange))

    def all_positions(self) -> list[PositionState]:
        return list(self._positions.values())

    def close(self, symbol: str, exchange: str) -> None:
        key: PositionKey = (symbol, exchange)
        if key in self._positions:
            del self._positions[key]
            log.info("position_tracker.closed", symbol=symbol, exchange=exchange)

    def update_remaining(self, symbol: str, exchange: str, qty_sold: float) -> None:
        pos = self._positions.get((symbol, exchange))
        if pos:
            pos.remaining_quantity = max(0.0, pos.remaining_quantity - qty_sold)
            if pos.remaining_quantity < 1e-8:
                self.close(symbol, exchange)
