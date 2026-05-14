import asyncio
import json
from datetime import datetime, timezone
import structlog
from prometheus_client import Counter, Histogram, Gauge, start_http_server
from sqlalchemy import update

from shared.config import settings
from shared.models import TokenCandidate, PatternType, get_session
from shared.redis_bus import bus, Channel
from agents.monitor.schemas import TokenSnapshot

from .score_engine import ScoreEngine
from .claude_validator import ClaudeValidator
from .schemas import ScoredToken, ScoreWeights, WeightUpdate

log = structlog.get_logger(__name__)

# ── Prometheus metrics ────────────────────────────────────────────────────────
SNAPSHOTS_PROCESSED = Counter("detector_snapshots_processed_total", "Snapshots evaluados")
ALERTS_GENERATED = Counter("detector_alerts_generated_total", "Tokens sobre umbral de alerta", ["pattern"])
LLM_CALLS = Counter("detector_llm_calls_total", "Llamadas a Claude API")
SCORE_DIST = Histogram(
    "detector_composite_score",
    "Distribución de scores compuestos",
    buckets=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
)
HIGH_SCORE_TOKENS = Gauge("detector_tokens_above_threshold", "Tokens sobre umbral en el ciclo actual")


class DetectorAgent:
    def __init__(self) -> None:
        self._engine = ScoreEngine()
        self._validator = ClaudeValidator()
        self._high_score_count = 0

    async def start(self) -> None:
        await bus.connect()

        start_http_server(9102)
        log.info("detector_agent.prometheus_started", port=9102)

        # Suscribirse a snapshots del Monitor
        await bus.subscribe(Channel.MONITOR_PUMP_SIGNAL, self._handle_snapshot)

        # Suscribirse a actualizaciones de pesos del Learner
        await bus.subscribe(Channel.LEARNER_FEEDBACK, self._handle_weight_update)

        await bus.start_listening()
        log.info("detector_agent.listening", channels=[
            Channel.MONITOR_PUMP_SIGNAL,
            Channel.LEARNER_FEEDBACK,
        ])

        try:
            while True:
                # Resetear gauge cada 5 minutos (un ciclo de monitor)
                await asyncio.sleep(settings.monitor_interval_seconds)
                HIGH_SCORE_TOKENS.set(self._high_score_count)
                self._high_score_count = 0
        except asyncio.CancelledError:
            await bus.disconnect()

    async def _handle_snapshot(self, payload: dict) -> None:
        try:
            snapshot = TokenSnapshot(**payload)
        except Exception as e:
            log.warning("detector_agent.invalid_snapshot", error=str(e))
            return

        scored: ScoredToken = self._engine.compute(snapshot)
        SNAPSHOTS_PROCESSED.inc()
        SCORE_DIST.observe(scored.composite_score)

        # Persistir score en DB para que el dashboard lo muestre
        try:
            try:
                pattern = PatternType(scored.dominant_pattern)
            except (ValueError, KeyError):
                pattern = PatternType.unknown
            breakdown_json = json.dumps({
                "dominant": scored.dominant_pattern,
                "lp_inflow": scored.long_pump.inflow_signal,
                "lp_holder": scored.long_pump.holder_signal,
                "lp_price": scored.long_pump.price_stability_signal,
                "lp_funding": scored.long_pump.funding_rate_signal,
                "cl_short": scored.classic_squeeze.short_interest_signal,
                "cl_funding": scored.classic_squeeze.funding_rate_signal,
                "cl_inflow": scored.classic_squeeze.inflow_signal,
                "cl_holder": scored.classic_squeeze.holder_signal,
            })
            async with get_session() as session:
                await session.execute(
                    update(TokenCandidate)
                    .where(TokenCandidate.symbol == snapshot.symbol)
                    .values(
                        detection_score=scored.composite_score,
                        pattern_type=pattern,
                        last_checked=datetime.now(timezone.utc),
                        inflow_usd=scored.inflow_4h_usd,
                        volume_24h_usd=scored.volume_24h_usd,
                        score_breakdown=breakdown_json,
                    )
                )
        except Exception as e:
            log.warning("detector_agent.db_update_failed", symbol=snapshot.symbol, error=str(e))

        if scored.composite_score < 10:
            return  # descartar ruido bajo

        # Validación con Claude si score muy alto
        if scored.composite_score >= settings.llm_validation_threshold:
            LLM_CALLS.inc()
            analysis = await self._validator.validate(scored)
            if analysis:
                scored = scored.model_copy(update={
                    "llm_analysis": analysis,
                    "llm_validated": True,
                })
            log.info(
                "detector_agent.llm_validated",
                symbol=scored.symbol,
                score=scored.composite_score,
                has_analysis=bool(analysis),
            )

        # Publicar en Redis para Scorer y Executor
        if scored.above_alert_threshold:
            self._high_score_count += 1
            ALERTS_GENERATED.labels(pattern=scored.dominant_pattern).inc()
            log.info(
                "detector_agent.alert_generated",
                symbol=scored.symbol,
                score=scored.composite_score,
                pattern=scored.dominant_pattern,
                llm=scored.llm_validated,
            )

        await bus.publish(Channel.DETECTOR_SCORED_TOKEN, scored.model_dump())

    async def _handle_weight_update(self, payload: dict) -> None:
        try:
            update = WeightUpdate(**payload)
            self._engine.update_weights(update.weights)
            log.info(
                "detector_agent.weights_updated",
                reason=update.reason,
                updated_at=str(update.updated_at),
            )
        except Exception as e:
            log.warning("detector_agent.invalid_weight_update", error=str(e))
