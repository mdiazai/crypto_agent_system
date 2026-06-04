"""
TradeEvaluator: clasifica y mide la calidad de trades cerrados.

entry_quality ya fue asignado por el Executor al cierre.
Aquí re-evaluamos los que no tienen quality y calculamos métricas agregadas.
"""
from typing import Optional
import structlog
from sqlalchemy import select, update

from shared.models import Trade, EntryQuality, TradeDirection, get_session
from .schemas import TradeMetrics, PatternMetrics, QUALITY_SCORE

log = structlog.get_logger(__name__)

MIN_TRADES_FOR_LEARNING = 5


class TradeEvaluator:
    async def load_closed_trades(self, days: int = 30) -> list[Trade]:
        """Carga trades cerrados de los últimos N días."""
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        async with get_session() as session:
            rows = (
                await session.execute(
                    select(Trade).where(
                        Trade.direction == TradeDirection.buy,
                        Trade.exit_price.is_not(None),
                        Trade.entry_time >= cutoff,
                    )
                )
            ).scalars().all()

        log.info("trade_evaluator.trades_loaded", count=len(rows), days=days)
        return list(rows)

    async def fill_missing_quality(self, trades: list[Trade]) -> int:
        """
        Para trades sin entry_quality (edge case), lo infiere del pnl_pct.
        Retorna el número de trades actualizados.
        """
        updated = 0
        async with get_session() as session:
            for trade in trades:
                if trade.entry_quality is not None:
                    continue
                quality = self._infer_quality(trade.pnl_pct)
                if quality:
                    await session.execute(
                        update(Trade)
                        .where(Trade.id == trade.id)
                        .values(entry_quality=quality)
                    )
                    trade.entry_quality = quality
                    updated += 1

        if updated:
            log.info("trade_evaluator.quality_filled", count=updated)
        return updated

    @staticmethod
    def _infer_quality(pnl_pct: Optional[float]) -> Optional[str]:
        if pnl_pct is None:
            return None
        if pnl_pct >= 20:
            return EntryQuality.perfect
        if pnl_pct >= 10:
            return EntryQuality.good
        if pnl_pct >= 2:
            return EntryQuality.early
        if 0 <= pnl_pct < 2:
            return EntryQuality.late
        return EntryQuality.bad

    def compute_metrics(self, trades: list[Trade], period_days: int = 30) -> TradeMetrics:
        """Calcula métricas agregadas globales y por patrón."""
        closed = [t for t in trades if t.entry_quality is not None and t.pnl_pct is not None]
        metrics = TradeMetrics(period_days=period_days, total_trades=len(closed))

        if not closed:
            return metrics

        wins = [t for t in closed if t.pnl_pct and t.pnl_pct > 0]
        metrics.win_rate = len(wins) / len(closed)
        metrics.avg_pnl_pct = sum(t.pnl_pct for t in closed if t.pnl_pct) / len(closed)

        quality_counts: dict[str, int] = {}
        quality_scores: list[float] = []
        for trade in closed:
            q = str(trade.entry_quality)
            quality_counts[q] = quality_counts.get(q, 0) + 1
            quality_scores.append(QUALITY_SCORE.get(q, 0.0))

        metrics.avg_quality_score = sum(quality_scores) / len(quality_scores)
        metrics.perfect_count = quality_counts.get("perfect", 0)
        metrics.good_count = quality_counts.get("good", 0)
        metrics.early_count = quality_counts.get("early", 0)
        metrics.late_count = quality_counts.get("late", 0)
        metrics.bad_count = quality_counts.get("bad", 0)

        # Por patrón
        for pattern_name in ("long_pump", "classic"):
            pattern_trades = [
                t for t in closed
                if t.pattern_detected and pattern_name in str(t.pattern_detected)
            ]
            metrics.__setattr__(
                pattern_name.replace("long_pump", "long_pump"),
                self._pattern_metrics(pattern_name, pattern_trades),
            )

        log.info(
            "trade_evaluator.metrics_computed",
            total=len(closed),
            win_rate=f"{metrics.win_rate:.1%}",
            avg_pnl=f"{metrics.avg_pnl_pct:.2f}%",
            avg_quality=f"{metrics.avg_quality_score:.2f}",
        )
        return metrics

    @staticmethod
    def _pattern_metrics(pattern: str, trades: list[Trade]) -> PatternMetrics:
        if not trades:
            return PatternMetrics(pattern=pattern)

        wins = [t for t in trades if t.pnl_pct and t.pnl_pct > 0]
        quality_dist: dict[str, int] = {}
        quality_scores = []

        for t in trades:
            q = str(t.entry_quality) if t.entry_quality else "unknown"
            quality_dist[q] = quality_dist.get(q, 0) + 1
            quality_scores.append(QUALITY_SCORE.get(q, 0.0))

        return PatternMetrics(
            pattern=pattern,
            total_trades=len(trades),
            win_count=len(wins),
            win_rate=len(wins) / len(trades),
            avg_pnl_pct=sum(t.pnl_pct for t in trades if t.pnl_pct) / len(trades),
            avg_quality_score=sum(quality_scores) / len(quality_scores),
            quality_distribution=quality_dist,
        )
