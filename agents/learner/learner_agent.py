import asyncio
import json
from datetime import datetime, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from prometheus_client import Counter, Gauge, start_http_server

from shared.config import settings
from shared.models import LearningLog, get_session
from shared.redis_bus import bus, Channel
from agents.detector.schemas import ScoreWeights, WeightUpdate

from .trade_evaluator import TradeEvaluator
from .weight_optimizer import WeightOptimizer
from .metrics_reporter import MetricsReporter
from .schemas import LearnerRun

log = structlog.get_logger(__name__)

# ── Prometheus ────────────────────────────────────────────────────────────────
LEARNER_RUNS = Counter("learner_runs_total", "Ciclos de aprendizaje completados")
TRADES_ANALYZED = Gauge("learner_trades_analyzed", "Trades analizados en el último ciclo")
WIN_RATE = Gauge("learner_win_rate", "Win rate calculado en el último ciclo")
AVG_QUALITY = Gauge("learner_avg_entry_quality", "Calidad media de entrada (0-4)")

_ANALYSIS_DAYS = 30  # ventana de análisis


class LearnerAgent:
    def __init__(self) -> None:
        self._evaluator = TradeEvaluator()
        self._optimizer = WeightOptimizer()
        self._reporter = MetricsReporter()
        self._scheduler = AsyncIOScheduler()
        self._current_weights = ScoreWeights()  # default weights

    async def start(self) -> None:
        await bus.connect()

        start_http_server(9105)
        log.info("learner_agent.prometheus_started", port=9105)

        self._scheduler.add_job(
            self.run,
            trigger="cron",
            hour=settings.learner_schedule_hour,
            minute=30,
            id="learner_daily",
            replace_existing=True,
        )
        self._scheduler.start()
        log.info("learner_agent.scheduled", hour=settings.learner_schedule_hour)

        # Cargar pesos previos desde DB si existen
        await self._load_last_weights()

        # Primer run al arrancar si hay datos
        await self.run()

        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self._scheduler.shutdown(wait=False)
            await bus.disconnect()

    async def run(self) -> LearnerRun:
        log.info("learner_agent.run_started")

        # 1. Cargar trades cerrados
        trades = await self._evaluator.load_closed_trades(days=_ANALYSIS_DAYS)
        if not trades:
            log.info("learner_agent.no_trades_to_analyze")
            return LearnerRun(
                metrics=self._evaluator.compute_metrics([], _ANALYSIS_DAYS),
                previous_weights=self._current_weights.model_dump(),
                new_weights=self._current_weights.model_dump(),
                adjustment_reason="no_trades",
            )

        # 2. Rellenar entry_quality faltante
        await self._evaluator.fill_missing_quality(trades)

        # 3. Calcular métricas
        metrics = self._evaluator.compute_metrics(trades, _ANALYSIS_DAYS)

        TRADES_ANALYZED.set(len(trades))
        WIN_RATE.set(metrics.win_rate)
        AVG_QUALITY.set(metrics.avg_quality_score)

        # 4. Optimizar pesos
        prev_weights = self._current_weights
        new_weights, reason = self._optimizer.optimize(metrics, prev_weights, trades)

        # Calcular delta para reporte
        prev_dict = prev_weights.model_dump()
        new_dict = new_weights.model_dump()
        delta = {k: new_dict[k] - prev_dict[k] for k in prev_dict}

        run = LearnerRun(
            metrics=metrics,
            previous_weights=prev_dict,
            new_weights=new_dict,
            weight_delta=delta,
            adjustment_reason=reason,
            trades_analyzed=len(trades),
            min_trades_met=len(trades) >= 5,
        )

        # 5. Persistir en DB
        await self._save_to_db(metrics, new_weights, reason)

        # 6. Actualizar pesos en memoria y publicar al Detector
        self._current_weights = new_weights
        await bus.publish(
            Channel.LEARNER_FEEDBACK,
            WeightUpdate(
                weights=new_weights,
                reason=reason,
            ).model_dump(),
        )

        LEARNER_RUNS.inc()
        log.info(
            "learner_agent.run_completed",
            trades=len(trades),
            win_rate=f"{metrics.win_rate:.1%}",
            avg_quality=f"{metrics.avg_quality_score:.2f}",
            reason=reason,
        )

        # 7. Reporte semanal los lunes
        if datetime.now(timezone.utc).weekday() == 0:
            await self._reporter.send_weekly_report(run)

        return run

    async def _load_last_weights(self) -> None:
        """Carga los pesos más recientes desde PostgreSQL al arrancar."""
        from sqlalchemy import select, desc
        async with get_session() as session:
            row = (
                await session.execute(
                    select(LearningLog)
                    .where(LearningLog.weights_adjusted.is_not(None))
                    .order_by(desc(LearningLog.created_at))
                    .limit(1)
                )
            ).scalar_one_or_none()

        if row and row.weights_adjusted:
            try:
                self._current_weights = ScoreWeights(**row.weights_adjusted)
                log.info(
                    "learner_agent.weights_loaded",
                    from_db=str(row.created_at),
                )
            except Exception as e:
                log.warning("learner_agent.weights_load_failed", error=str(e))

    async def _save_to_db(
        self,
        metrics,
        new_weights: ScoreWeights,
        reason: str,
    ) -> None:
        async with get_session() as session:
            session.add(LearningLog(
                created_at=datetime.now(timezone.utc),
                tokens_evaluated=metrics.total_trades,
                accuracy_rate=metrics.win_rate,
                avg_entry_quality=metrics.avg_quality_score,
                weights_adjusted=new_weights.model_dump(),
                notes=reason,
            ))
