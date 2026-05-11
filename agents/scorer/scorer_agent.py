import asyncio
from datetime import datetime, timezone, timedelta

import structlog
from prometheus_client import Counter, Gauge, start_http_server
from sqlalchemy import select

from shared.config import settings
from shared.models import Alert, get_session
from shared.redis_bus import bus, Channel
from agents.detector.schemas import ScoredToken

from .telegram_client import TelegramClient
from .message_formatter import format_alert, format_system_alert

log = structlog.get_logger(__name__)

DEDUP_WINDOW = timedelta(hours=2)

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

        try:
            while True:
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            await bus.disconnect()

    async def _handle_scored_token(self, payload: dict) -> None:
        try:
            scored = ScoredToken(**payload)
        except Exception as e:
            log.warning("scorer_agent.invalid_payload", error=str(e))
            return

        if not scored.above_alert_threshold:
            return

        PENDING_ALERTS.inc()

        # Deduplicación vía PostgreSQL
        if await self._is_duplicate(scored.symbol):
            ALERTS_DEDUPED.inc()
            log.info("scorer_agent.deduped", symbol=scored.symbol)
            PENDING_ALERTS.dec()
            return

        # Formatear y enviar
        message = format_alert(scored)
        message_id = await self._telegram.send_alert(
            text=message,
            symbol=scored.symbol,
            exchange=scored.exchange,
        )

        if message_id is None:
            ALERTS_FAILED.inc()
            PENDING_ALERTS.dec()
            log.error("scorer_agent.send_failed", symbol=scored.symbol)
            return

        # Persistir en DB
        await self._save_alert(scored, message_id)

        ALERTS_SENT.labels(pattern=scored.dominant_pattern).inc()
        PENDING_ALERTS.dec()

        log.info(
            "scorer_agent.alert_sent",
            symbol=scored.symbol,
            score=scored.composite_score,
            pattern=scored.dominant_pattern,
            message_id=message_id,
        )

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

    async def _save_alert(self, scored: ScoredToken, message_id: int) -> None:
        async with get_session() as session:
            session.add(Alert(
                token_symbol=scored.symbol,
                score=scored.composite_score,
                pattern_type=scored.dominant_pattern,
                sent_at=datetime.now(timezone.utc),
                telegram_message_id=message_id,
            ))

    async def send_system_alert(self, title: str, body: str) -> None:
        """Para alertas del sistema: circuit breaker, errores críticos, etc."""
        text = format_system_alert(title, body)
        await self._telegram.send_text(text)
