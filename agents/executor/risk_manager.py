"""
RiskManager: stop loss, take profit escalonado, circuit breaker y drawdown diario.

Estado efímero (consecutive_losses, daily_pnl) en memoria.
Circuit breaker persiste en Redis con TTL para sobrevivir reinicios.
"""
from datetime import datetime, timezone, date
from typing import Optional
import structlog
import redis.asyncio as aioredis

from shared.config import settings
from .schemas import PositionState, TakeProfitLevel

log = structlog.get_logger(__name__)

_CB_KEY = "executor:circuit_breaker"         # Redis key
_CB_TRIGGERED_AT_KEY = "executor:cb_triggered_at"


class RiskManager:
    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None
        self._consecutive_losses: int = 0
        self._daily_pnl: float = 0.0
        self._daily_date: str = ""           # YYYY-MM-DD UTC

    async def connect(self, redis_url: str) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    # ── Stop Loss ─────────────────────────────────────────────────────────────

    def should_stop_loss(self, position: PositionState, current_price: float) -> bool:
        return current_price <= position.stop_loss_price

    @staticmethod
    def calc_stop_loss_price(entry_price: float) -> float:
        return entry_price * (1 - settings.stop_loss_pct / 100)

    # ── Take Profit Escalonado ────────────────────────────────────────────────

    @staticmethod
    def build_take_profit_levels(quantity: float) -> list[TakeProfitLevel]:
        """
        Level 1: +30% → vende 50% de la posición original
        Level 2: +60% → vende 30% de la posición original
        Level 3: +100% → vende 20% restante
        """
        return [
            TakeProfitLevel(
                gain_pct=settings.take_profit_1_pct,
                sell_pct=50.0,
            ),
            TakeProfitLevel(
                gain_pct=settings.take_profit_2_pct,
                sell_pct=30.0,
            ),
            TakeProfitLevel(
                gain_pct=settings.take_profit_3_pct,
                sell_pct=20.0,
            ),
        ]

    def triggered_levels(
        self, position: PositionState, current_price: float
    ) -> list[TakeProfitLevel]:
        """Retorna los niveles de TP que se acaban de activar (no disparados aún)."""
        pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100
        triggered = []
        for level in position.take_profit_levels:
            if not level.triggered and pnl_pct >= level.gain_pct:
                triggered.append(level)
        return triggered

    def qty_to_sell(self, position: PositionState, level: TakeProfitLevel) -> float:
        """Calcula la cantidad a vender para este nivel (% de la cantidad ORIGINAL)."""
        qty = position.total_quantity * (level.sell_pct / 100)
        return min(qty, position.remaining_quantity)

    # ── Daily Drawdown ────────────────────────────────────────────────────────

    def _today_utc(self) -> str:
        return date.today().isoformat()

    def record_pnl(self, pnl_usd: float, is_loss: bool) -> None:
        today = self._today_utc()
        if today != self._daily_date:
            self._daily_pnl = 0.0
            self._daily_date = today

        self._daily_pnl += pnl_usd

        if is_loss:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

        log.info(
            "risk_manager.pnl_recorded",
            pnl_usd=pnl_usd,
            daily_pnl=self._daily_pnl,
            consecutive_losses=self._consecutive_losses,
        )

    def daily_drawdown_breached(self) -> bool:
        today = self._today_utc()
        if today != self._daily_date:
            return False
        max_loss = settings.capital_total_usd * (settings.max_daily_loss_pct / 100)
        return self._daily_pnl < -max_loss

    # ── Circuit Breaker ───────────────────────────────────────────────────────

    async def is_circuit_breaker_active(self) -> bool:
        if self._redis is None:
            return self._consecutive_losses >= settings.max_consecutive_losses
        exists = await self._redis.exists(_CB_KEY)
        return bool(exists)

    async def trigger_circuit_breaker(self) -> None:
        ttl_seconds = settings.circuit_breaker_hours * 3600
        log.warning(
            "risk_manager.circuit_breaker_triggered",
            consecutive_losses=self._consecutive_losses,
            pause_hours=settings.circuit_breaker_hours,
        )
        if self._redis:
            await self._redis.setex(_CB_KEY, ttl_seconds, "1")
            await self._redis.setex(
                _CB_TRIGGERED_AT_KEY, ttl_seconds,
                datetime.now(timezone.utc).isoformat(),
            )

    async def reset_circuit_breaker(self) -> None:
        if self._redis:
            await self._redis.delete(_CB_KEY, _CB_TRIGGERED_AT_KEY)
        self._consecutive_losses = 0
        log.info("risk_manager.circuit_breaker_reset")

    # ── Safety Gate ───────────────────────────────────────────────────────────

    async def can_trade(self) -> tuple[bool, str]:
        """
        Puerta de entrada antes de ejecutar cualquier compra.
        Retorna (allowed, reason).
        """
        if await self.is_circuit_breaker_active():
            return False, "circuit_breaker_active"
        if self.daily_drawdown_breached():
            return False, "daily_drawdown_breached"
        return True, "ok"
