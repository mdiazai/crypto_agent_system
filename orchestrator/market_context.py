"""
MarketContextAnalyzer: detecta condiciones de mercado anómalas consultando DB y Redis.

Señales de anomalía:
  - > 5 alertas en los últimos 30 min (pump cascade)
  - Score promedio de señales recientes > 88
  - Circuit breaker activo
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import structlog
import redis.asyncio as aioredis
from sqlalchemy import select, func

from shared.config import settings
from shared.models import Alert, get_session
from .schemas import MarketContext

log = structlog.get_logger(__name__)

_ANOMALY_SIGNAL_COUNT = 5    # más de N alertas en 30 min = anómalo
_ANOMALY_AVG_SCORE = 88.0    # score promedio muy alto = ambiente caliente


class MarketContextAnalyzer:
    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    async def analyze(self) -> MarketContext:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=30)

        async with get_session() as session:
            rows = (
                await session.execute(
                    select(Alert.score)
                    .where(Alert.sent_at >= cutoff)
                )
            ).scalars().all()

        count = len(rows)
        avg_score = sum(rows) / count if rows else 0.0

        # Verificar circuit breaker
        cb_active = False
        if self._redis:
            cb_active = bool(await self._redis.exists("executor:circuit_breaker"))

        anomaly = False
        reason = ""

        if cb_active:
            anomaly = True
            reason = "circuit_breaker_active"
        elif count > _ANOMALY_SIGNAL_COUNT:
            anomaly = True
            reason = f"{count}_signals_in_30min"
        elif avg_score > _ANOMALY_AVG_SCORE and count >= 3:
            anomaly = True
            reason = f"avg_score_{avg_score:.1f}_above_{_ANOMALY_AVG_SCORE}"

        ctx = MarketContext(
            signals_last_30m=count,
            avg_score_last_30m=round(avg_score, 2),
            is_anomalous=anomaly,
            anomaly_reason=reason,
        )

        if anomaly:
            log.warning(
                "market_context.anomaly_detected",
                signals=count,
                avg_score=avg_score,
                reason=reason,
            )
        else:
            log.debug("market_context.normal", signals=count, avg_score=avg_score)

        return ctx
