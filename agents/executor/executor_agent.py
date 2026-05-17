"""
ExecutorAgent: compra, monitorea y vende posiciones automáticamente.

Flujo principal:
  1. Recibe ScoredToken de channel:detector:scored_token
  2. Verifica safety gate (circuit breaker, drawdown)
  3. Abre posición en MEXC y Bitget simultáneamente
  4. Loop de monitoreo cada 30s: stop loss + take profit escalonado
  5. Publica TradeResult en channel:executor:trade_result
"""
import asyncio
from datetime import datetime, timezone

import structlog
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from sqlalchemy import update

from sqlalchemy import select

from shared.config import settings
from shared.models import Alert, Trade, TradeDirection, EntryQuality, get_session
from shared.redis_bus import bus, Channel
from agents.detector.schemas import ScoredToken

from .exchange_client import ExchangeClient
from .risk_manager import RiskManager
from .position_tracker import PositionTracker
from .schemas import PositionState, TradeResult, TakeProfitLevel

log = structlog.get_logger(__name__)

_MONITOR_INTERVAL = 30  # segundos entre chequeos de posiciones

# ── Prometheus ────────────────────────────────────────────────────────────────
TRADES_OPENED = Counter("executor_trades_opened_total", "Compras ejecutadas", ["exchange", "mode"])
TRADES_CLOSED = Counter("executor_trades_closed_total", "Ventas ejecutadas", ["reason", "mode"])
OPEN_POSITIONS = Gauge("executor_open_positions", "Posiciones abiertas actualmente")
REALIZED_PNL = Histogram(
    "executor_realized_pnl_pct",
    "P&L realizado por trade (%)",
    buckets=[-50, -20, -10, -8, 0, 10, 30, 60, 100, 200],
)


class ExecutorAgent:
    def __init__(self) -> None:
        self._client = ExchangeClient()
        self._risk = RiskManager()
        self._tracker = PositionTracker(self._risk)

    async def start(self) -> None:
        await bus.connect()
        await self._risk.connect(settings.redis_url)
        await self._tracker.load_from_db()

        start_http_server(9104)
        log.info(
            "executor_agent.started",
            paper_trading=settings.paper_trading,
            open_positions=len(self._tracker.all_positions()),
        )

        await bus.subscribe(Channel.DETECTOR_SCORED_TOKEN, self._handle_signal)
        await bus.subscribe("channel:control:executor:run", self._handle_manual_trigger)
        await bus.start_listening()

        # Lanzar loop de monitoreo de posiciones en segundo plano
        monitor_task = asyncio.create_task(self._position_monitor_loop())

        try:
            while True:
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            monitor_task.cancel()
            await self._client.close()
            await bus.disconnect()

    async def _handle_manual_trigger(self, payload: dict) -> None:
        log.info("executor_agent.manual_trigger", source=payload.get("source", "unknown"))
        for pos in self._tracker.all_positions():
            try:
                await self._check_position(pos)
            except Exception:
                log.exception("executor_agent.monitor_error", symbol=pos.symbol)

    # ── Señal de entrada ──────────────────────────────────────────────────────

    async def _handle_signal(self, payload: dict) -> None:
        try:
            scored = ScoredToken(**payload)
        except Exception as e:
            log.warning("executor_agent.invalid_payload", error=str(e))
            return

        if not scored.above_alert_threshold:
            return

        allowed, reason = await self._risk.can_trade()
        if not allowed:
            log.warning("executor_agent.trading_blocked", reason=reason, symbol=scored.symbol)
            return

        # Verificar capital disponible antes de abrir
        capital_en_uso = sum(p.capital_usd for p in self._tracker.all_positions())
        capital_disponible = settings.capital_total_usd - capital_en_uso
        capital_minimo = settings.capital_total_usd * 0.10
        if capital_disponible < capital_minimo:
            log.warning(
                "executor_agent.capital_insuficiente",
                symbol=scored.symbol,
                capital_disponible=round(capital_disponible, 2),
                capital_minimo=round(capital_minimo, 2),
            )
            return

        # Abrir en MEXC y Bitget en paralelo
        await asyncio.gather(
            self._open_position(scored, "mexc", settings.mexc_capital_usd),
            self._open_position(scored, "bitget", settings.bitget_capital_usd),
        )

    async def _open_position(
        self,
        scored: ScoredToken,
        exchange_id: str,
        capital_usd: float,
    ) -> None:
        if self._tracker.has_position(scored.symbol, exchange_id):
            log.info(
                "executor_agent.position_exists",
                symbol=scored.symbol,
                exchange=exchange_id,
            )
            return

        result = await self._client.buy(scored.symbol, capital_usd, exchange_id)
        if not result.success or not result.price or not result.quantity:
            log.error(
                "executor_agent.buy_failed",
                symbol=scored.symbol,
                exchange=exchange_id,
                error=result.error,
            )
            return

        mode = "paper" if settings.paper_trading else "real"
        TRADES_OPENED.labels(exchange=exchange_id, mode=mode).inc()

        # Persistir en DB
        entry_time = datetime.now(timezone.utc)
        trade = Trade(
            token_symbol=scored.symbol,
            exchange=exchange_id,
            direction=TradeDirection.buy,
            entry_price=result.price,
            quantity=result.quantity,
            capital_used_usd=capital_usd,
            entry_time=entry_time,
            pattern_detected=scored.dominant_pattern,
            score_at_entry=scored.composite_score,
            is_paper=settings.paper_trading,
        )
        async with get_session() as session:
            # Buscar la alerta más antigua del token para medir cuánto antes la detectamos
            oldest_alert = (
                await session.execute(
                    select(Alert)
                    .where(Alert.token_symbol == scored.symbol)
                    .order_by(Alert.sent_at.asc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            if oldest_alert:
                sent = oldest_alert.sent_at
                if sent.tzinfo is None:
                    sent = sent.replace(tzinfo=timezone.utc)
                trade.anticipation_minutes = (entry_time - sent).total_seconds() / 60

            session.add(trade)
            await session.flush()
            trade_id = trade.id

        sl_price = self._risk.calc_stop_loss_price(result.price)
        tp_levels = self._risk.build_take_profit_levels(result.quantity)

        position = PositionState(
            trade_id=trade_id,
            symbol=scored.symbol,
            exchange=exchange_id,
            entry_price=result.price,
            total_quantity=result.quantity,
            remaining_quantity=result.quantity,
            capital_usd=capital_usd,
            stop_loss_price=sl_price,
            take_profit_levels=tp_levels,
            opened_at=entry_time,
            is_paper=settings.paper_trading,
            score_at_entry=scored.composite_score,
            pattern_detected=scored.dominant_pattern,
        )
        self._tracker.open(position)
        OPEN_POSITIONS.set(len(self._tracker.all_positions()))

        log.info(
            "executor_agent.position_opened",
            symbol=scored.symbol,
            exchange=exchange_id,
            entry=result.price,
            qty=result.quantity,
            sl=sl_price,
            paper=settings.paper_trading,
        )

        await bus.publish(Channel.EXECUTOR_TRADE_RESULT, TradeResult(
            trade_id=trade_id,
            symbol=scored.symbol,
            exchange=exchange_id,
            action="buy",
            price=result.price,
            quantity=result.quantity,
            is_paper=settings.paper_trading,
            reason="signal_above_threshold",
        ).model_dump())

    # ── Monitor de posiciones ─────────────────────────────────────────────────

    async def _position_monitor_loop(self) -> None:
        while True:
            await asyncio.sleep(_MONITOR_INTERVAL)
            positions = self._tracker.all_positions()

            # Heartbeat para que el Orchestrator detecte actividad aunque no haya trades
            if bus._client:
                await bus._client.setex("executor:heartbeat", 120, str(len(positions)))

            if not positions:
                continue

            for pos in positions:
                try:
                    await self._check_position(pos)
                except Exception:
                    log.exception(
                        "executor_agent.monitor_error",
                        symbol=pos.symbol,
                        exchange=pos.exchange,
                    )

    async def _check_position(self, pos: PositionState) -> None:
        # Intentar precio en el exchange primario; si falla, intentar el fallback.
        # Sin precio no se pueden verificar SL ni TP — se loguea y se omite el ciclo.
        _FALLBACK = {"mexc": "bitget", "bitget": "mexc"}
        current_price: float | None = None
        for attempt_exchange in (pos.exchange, _FALLBACK.get(pos.exchange, "")):
            if not attempt_exchange:
                break
            try:
                current_price = await self._client.get_price(pos.symbol, attempt_exchange)
                break
            except Exception as e:
                log.warning(
                    "executor_agent.price_fetch_failed",
                    symbol=pos.symbol,
                    exchange=attempt_exchange,
                    error=str(e),
                )

        if current_price is None:
            log.error(
                "executor_agent.price_unavailable",
                symbol=pos.symbol,
                note="SL/TP/MaxHold omitidos este ciclo",
            )
            return

        # ── Max Hold Time ─────────────────────────────────────────────────────
        if self._risk.should_max_hold_exit(pos):
            log.warning(
                "executor_agent.max_hold_exit",
                symbol=pos.symbol,
                exchange=pos.exchange,
                max_hold_hours=settings.max_hold_hours,
            )
            await self._execute_sell(
                pos, pos.remaining_quantity, current_price, "sell_max_hold", "max_hold_timeout"
            )
            return

        # ── Stop Loss ─────────────────────────────────────────────────────────
        if self._risk.should_stop_loss(pos, current_price):
            await self._execute_sell(
                pos, pos.remaining_quantity, current_price, "sell_stop_loss", "stop_loss"
            )
            return

        # ── Take Profit ───────────────────────────────────────────────────────
        for level in self._risk.triggered_levels(pos, current_price):
            qty = self._risk.qty_to_sell(pos, level)
            action = f"sell_tp{pos.take_profit_levels.index(level) + 1}"
            if action not in ("sell_tp1", "sell_tp2", "sell_final"):
                action = "sell_final"

            await self._execute_sell(pos, qty, current_price, action, f"take_profit_{level.gain_pct}pct")

            level.triggered = True
            level.triggered_at = datetime.now(timezone.utc)
            level.fill_price = current_price
            self._tracker.update_remaining(pos.symbol, pos.exchange, qty)

            # Verificar si la posición está completamente cerrada
            if not self._tracker.has_position(pos.symbol, pos.exchange):
                break

    async def _execute_sell(
        self,
        pos: PositionState,
        quantity: float,
        current_price: float,
        action: str,
        reason: str,
    ) -> None:
        if quantity <= 0:
            return

        result = await self._client.sell(pos.symbol, quantity, pos.exchange)
        if not result.success or not result.price:
            log.error(
                "executor_agent.sell_failed",
                symbol=pos.symbol,
                exchange=pos.exchange,
                reason=reason,
                error=result.error,
            )
            return

        fill_price = result.price
        pnl_pct = ((fill_price - pos.entry_price) / pos.entry_price) * 100
        pnl_usd = (fill_price - pos.entry_price) * quantity
        is_loss = pnl_usd < 0
        mode = "paper" if settings.paper_trading else "real"

        TRADES_CLOSED.labels(reason=reason, mode=mode).inc()
        REALIZED_PNL.observe(pnl_pct)
        self._risk.record_pnl(pnl_usd, is_loss)

        # Actualizar trade en DB
        async with get_session() as session:
            quality = _entry_quality(pnl_pct, reason)
            await session.execute(
                update(Trade)
                .where(Trade.id == pos.trade_id)
                .values(
                    exit_price=fill_price,
                    exit_time=datetime.now(timezone.utc),
                    pnl_usd=pnl_usd,
                    pnl_pct=pnl_pct,
                    entry_quality=quality,
                )
            )

        # Circuit breaker
        if self._risk._consecutive_losses >= settings.max_consecutive_losses:
            await self._risk.trigger_circuit_breaker()
            await bus.publish(Channel.DETECTOR_SCORED_TOKEN, {
                "_system_alert": True,
                "title": "Circuit Breaker Activado",
                "body": f"{settings.max_consecutive_losses} pérdidas consecutivas. Trading pausado {settings.circuit_breaker_hours}h.",
            })

        # Drawdown diario
        if self._risk.daily_drawdown_breached():
            log.error("executor_agent.daily_drawdown_breached", daily_pnl=self._risk._daily_pnl)

        OPEN_POSITIONS.set(len(self._tracker.all_positions()))

        log.info(
            "executor_agent.sell_executed",
            symbol=pos.symbol,
            exchange=pos.exchange,
            action=action,
            fill_price=fill_price,
            pnl_pct=f"{pnl_pct:.2f}%",
            pnl_usd=f"${pnl_usd:.2f}",
            paper=settings.paper_trading,
        )

        await bus.publish(Channel.EXECUTOR_TRADE_RESULT, TradeResult(
            trade_id=pos.trade_id,
            symbol=pos.symbol,
            exchange=pos.exchange,
            action=action,
            price=fill_price,
            quantity=quantity,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            reason=reason,
            is_paper=settings.paper_trading,
        ).model_dump())

        if action in ("sell_stop_loss", "sell_final", "sell_max_hold"):
            self._tracker.close(pos.symbol, pos.exchange)


def _entry_quality(pnl_pct: float, reason: str) -> str:
    from shared.models import EntryQuality
    if reason == "stop_loss" or pnl_pct < 0:
        return EntryQuality.bad
    if pnl_pct >= 20:
        return EntryQuality.perfect
    if pnl_pct >= 10:
        return EntryQuality.good
    return EntryQuality.early
