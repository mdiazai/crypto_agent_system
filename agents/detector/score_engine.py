"""
ScoreEngine: combina ambos patrones y calcula el composite_score final.
Los pesos son actualizados por el Learner vía Redis.
"""
import structlog
from agents.monitor.schemas import TokenSnapshot
from .schemas import ScoreWeights, ScoredToken, PatternBreakdown
from . import pattern_long_pump, pattern_classic_squeeze

log = structlog.get_logger(__name__)


class ScoreEngine:
    def __init__(self) -> None:
        self._weights = ScoreWeights()

    def update_weights(self, weights: ScoreWeights) -> None:
        self._weights = weights
        log.info("score_engine.weights_updated", weights=weights.model_dump())

    def compute(self, snapshot: TokenSnapshot) -> ScoredToken:
        lp: PatternBreakdown = pattern_long_pump.score(snapshot, self._weights)
        cl: PatternBreakdown = pattern_classic_squeeze.score(snapshot, self._weights)

        # El patrón dominante es el de mayor score
        if lp.score >= cl.score:
            composite = lp.score
            dominant = "long_pump"
        else:
            composite = cl.score
            dominant = "classic"

        # Bonus si ambos patrones suenan fuerte al mismo tiempo (convergencia)
        if lp.score >= 50 and cl.score >= 50:
            convergence_bonus = min(10.0, (lp.score + cl.score - 100) * 0.2)
            composite = min(100.0, composite + convergence_bonus)

        from shared.config import settings

        scored = ScoredToken(
            symbol=snapshot.symbol,
            exchange=snapshot.exchange,
            long_pump=lp,
            classic_squeeze=cl,
            composite_score=round(composite, 2),
            dominant_pattern=dominant,
            current_price=snapshot.current_price,
            inflow_4h_usd=snapshot.inflow_4h_usd,
            holder_top10_pct=snapshot.holder_top10_pct,
            volume_24h_usd=snapshot.volume_24h_usd,
            funding_rate=snapshot.funding_rate,
            above_alert_threshold=composite >= settings.alert_threshold,
        )

        log.debug(
            "score_engine.computed",
            symbol=snapshot.symbol,
            composite=composite,
            lp=lp.score,
            cl=cl.score,
            dominant=dominant,
        )
        return scored
