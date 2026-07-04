import asyncio
import time
from datetime import datetime, timezone, timedelta

import structlog
from prometheus_client import Counter, Gauge, start_http_server
from sqlalchemy import select, update

from shared.config import settings
from shared.models import Alert, TokenCandidate, get_session
from shared.redis_bus import bus, Channel
from agents.detector.schemas import ScoredToken

from .telegram_client import TelegramClient
from .message_formatter import format_alert, format_system_alert

log = structlog.get_logger(__name__)

DEDUP_WINDOW = timedelta(hours=2)

# Espejo del LARGE_CAP_BLACKLIST de pre_screener — el scorer no tiene acceso al módulo discovery
EXCLUDED_SYMBOLS: set[str] = {
    "BTC", "ETH", "BNB", "XRP", "SOL", "ADA", "DOGE", "TRX", "AVAX",
    "DOT", "MATIC", "LINK", "UNI", "LTC", "BCH", "ATOM", "XLM", "TON",
    "ALGO", "VET", "FIL", "THETA", "ETC", "XMR", "HBAR", "NEAR", "SHIB",
    "FTM", "SAND", "MANA", "AXS", "GALA", "ENJ", "SUI", "APT", "INJ",
    "XAUT", "PAXG", "GOLD", "SILVER", "CACHE", "DGX", "SLVT", "SLVX", "OIL",
    "GOLD(PAXG)", "GOLD(XAUT)",
    "WBTC", "STETH", "WETH", "CBBTC", "WBNB",
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDD", "USDP",
    "GUSD", "FRAX", "USD1",
    # Forex-pegged tokens (se comportan como stablecoins, no generan pumps)
    "EUR", "GBP", "JPY", "CHF", "CAD", "AUD",
    # Privacy coins large-cap
    "ZEC", "DASH", "XMR",
}

# ── Prometheus metrics ────────────────────────────────────────────────────────
ALERTS_SENT = Counter("scorer_alerts_sent_total", "Alertas Telegram enviadas", ["pattern"])
ALERTS_DEDUPED = Counter("scorer_alerts_deduped_total", "Alertas omitidas por deduplicación")
ALERTS_FAILED = Counter("scorer_alerts_failed_total", "Errores al enviar alerta")
PENDING_ALERTS = Gauge("scorer_pending_alerts", "Tokens sobre umbral en espera")


class ScorerAgent:
    def __init__(self) -> None:
        self._telegram = TelegramClient()

    async def start(self) -> None:
        await bus.connect()

        start_http_server(9103)
        log.info("scorer_agent.prometheus_started", port=9103)

        await bus.subscribe(Channel.DETECTOR_SCORED_TOKEN, self._handle_scored_token)
        await bus.start_listening()
        log.info("scorer_agent.listening", channel=Channel.DETECTOR_SCORED_TOKEN)

        heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        try:
            while True:
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            heartbeat_task.cancel()
            await bus.disconnect()

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            if bus._client:
                await bus._client.setex("scorer:heartbeat", 180, str(int(time.time())))

    async def _handle_scored_token(self, payload: dict) -> None:
        try:
            scored = ScoredToken(**payload)
        except Exception as e:
            log.warning("scorer_agent.invalid_payload", error=str(e))
            return

        if not scored.above_alert_threshold:
            return

        if scored.symbol in EXCLUDED_SYMBOLS:
            log.info("scorer_agent.excluded_symbol", symbol=scored.symbol)
            return

        # Heartbeat: scorer está activo procesando señales (TTL 12 min = 2 ciclos de monitor)
        if bus._client:
            await bus._client.setex(
                "scorer:heartbeat",
                720,
                f"{scored.symbol}:{scored.composite_score:.1f}",
            )

        PENDING_ALERTS.inc()

        # Deduplicación vía PostgreSQL
        if await self._is_duplicate(scored.symbol):
            ALERTS_DEDUPED.inc()
            log.info("scorer_agent.deduped", symbol=scored.symbol)
            PENDING_ALERTS.dec()
            return

        # Intentar envío Telegram (best-effort — no bloquea el guardado en DB)
        message = format_alert(scored)
        message_id = await self._telegram.send_alert(
            text=message,
            symbol=scored.symbol,
            exchange=scored.exchange,
        )

        if message_id is None:
            ALERTS_FAILED.inc()
            log.error("scorer_agent.telegram_failed", symbol=scored.symbol)
        else:
            ALERTS_SENT.labels(pattern=scored.dominant_pattern).inc()
            log.info(
                "scorer_agent.alert_sent",
                symbol=scored.symbol,
                score=scored.composite_score,
                pattern=scored.dominant_pattern,
                message_id=message_id,
            )

        # Siempre persistir en DB y marcar alert_sent aunque Telegram falle
        await self._save_alert(scored, message_id)
        PENDING_ALERTS.dec()

    async def _is_duplicate(self, symbol: str) -> bool:
        """Retorna True si ya se envió una alerta de este símbolo en las últimas 2 horas."""
        cutoff = datetime.now(timezone.utc) - DEDUP_WINDOW
        async with get_session() as session:
            row = (
                await session.execute(
                    select(Alert.id)
                    .where(Alert.token_symbol == symbol)
                    .where(Alert.sent_at >= cutoff)
                    .limit(1)
                )
            ).scalar_one_or_none()
        return row is not None

    async def _save_alert(self, scored: ScoredToken, message_id: int | None) -> None:
        async with get_session() as session:
            session.add(Alert(
                token_symbol=scored.symbol,
                score=scored.composite_score,
                pattern_type=scored.dominant_pattern,
                sent_at=datetime.now(timezone.utc),
                telegram_message_id=message_id,
            ))
            await session.execute(
                update(TokenCandidate)
                .where(TokenCandidate.symbol == scored.symbol)
                .values(alert_sent=True)
            )

    async def send_system_alert(self, title: str, body: str) -> None:
        """Para alertas del sistema: circuit breaker, errores críticos, etc."""
        text = format_system_alert(title, body)
        await self._telegram.send_text(text)
