"""
WeightOptimizer: ajusta los pesos del ScoreEngine basándose en resultados históricos.

Fase 1 (< 50 trades): ajuste heurístico basado en win rate por patrón.
Fase 2 (>= 50 trades): XGBoost sobre features numéricas para refinar pesos.

Los pesos están clampeados a [0.3, 3.0] para evitar degeneración del scoring.
"""
import structlog
import numpy as np

from agents.detector.schemas import ScoreWeights
from shared.models import Trade
from .schemas import TradeMetrics, QUALITY_SCORE

log = structlog.get_logger(__name__)

_WEIGHT_MIN = 0.3
_WEIGHT_MAX = 3.0
_MIN_TRADES_FOR_ML = 50


def _clamp(v: float) -> float:
    return max(_WEIGHT_MIN, min(_WEIGHT_MAX, v))


def _performance_factor(win_rate: float, avg_quality: float) -> float:
    """
    Retorna un multiplicador (0.75–1.35) basado en rendimiento.
    Por encima de 60% win rate y calidad > 2.5 → aumentar pesos.
    Por debajo de 40% → reducir.
    """
    # Factor de win rate
    if win_rate >= 0.70:
        wr_factor = 1.35
    elif win_rate >= 0.60:
        wr_factor = 1.15
    elif win_rate >= 0.50:
        wr_factor = 1.0
    elif win_rate >= 0.40:
        wr_factor = 0.90
    else:
        wr_factor = 0.75

    # Factor de calidad (0-4 scale)
    quality_factor = 0.85 + (avg_quality / 4.0) * 0.30  # rango [0.85, 1.15]

    return (wr_factor + quality_factor) / 2.0


class WeightOptimizer:
    def optimize(
        self,
        metrics: TradeMetrics,
        current: ScoreWeights,
        trades: list[Trade],
    ) -> tuple[ScoreWeights, str]:
        """
        Retorna (nuevos pesos, razón del ajuste).
        """
        if metrics.total_trades < 5:
            return current, "insufficient_data"

        lp = metrics.long_pump
        cl = metrics.classic

        # ── Ajuste heurístico base ────────────────────────────────────────────
        lp_factor = _performance_factor(
            lp.win_rate if lp.total_trades >= 3 else 0.5,
            lp.avg_quality_score if lp.total_trades >= 3 else 2.0,
        )
        cl_factor = _performance_factor(
            cl.win_rate if cl.total_trades >= 3 else 0.5,
            cl.avg_quality_score if cl.total_trades >= 3 else 2.0,
        )

        new_weights = ScoreWeights(
            lp_inflow=_clamp(current.lp_inflow * lp_factor),
            lp_holder=_clamp(current.lp_holder * lp_factor),
            lp_price_stability=_clamp(current.lp_price_stability * lp_factor),
            lp_short_pressure=_clamp(current.lp_short_pressure * lp_factor),
            cl_short_interest=_clamp(current.cl_short_interest * cl_factor),
            cl_funding_rate=_clamp(current.cl_funding_rate * cl_factor),
            cl_inflow=_clamp(current.cl_inflow * cl_factor),
            cl_holder=_clamp(current.cl_holder * cl_factor),
        )

        # ── Refinamiento ML si hay suficientes datos ──────────────────────────
        eligible_trades = [
            t for t in trades
            if t.score_at_entry and t.entry_quality and not t.is_paper
        ]
        reason = f"heuristic lp_factor={lp_factor:.2f} cl_factor={cl_factor:.2f}"

        if len(eligible_trades) >= _MIN_TRADES_FOR_ML:
            try:
                ml_weights, ml_reason = self._ml_refine(eligible_trades, new_weights)
                new_weights = ml_weights
                reason = f"{reason} | {ml_reason}"
            except Exception as e:
                log.warning("weight_optimizer.ml_failed", error=str(e))

        log.info(
            "weight_optimizer.optimized",
            lp_factor=round(lp_factor, 3),
            cl_factor=round(cl_factor, 3),
            new_lp_inflow=new_weights.lp_inflow,
            new_cl_funding=new_weights.cl_funding_rate,
            reason=reason,
        )
        return new_weights, reason

    def _ml_refine(
        self, trades: list[Trade], current: ScoreWeights
    ) -> tuple[ScoreWeights, str]:
        """
        XGBoost: predice good/perfect entry basándose en score_at_entry y patrón.
        Usa los coeficientes para refinar la distribución de pesos entre LP y Classic.
        """
        try:
            from xgboost import XGBClassifier
        except ImportError:
            from sklearn.linear_model import LogisticRegression as XGBClassifier  # type: ignore

        X = np.array([
            [
                t.score_at_entry or 0.0,
                1.0 if t.pattern_detected and "long_pump" in str(t.pattern_detected) else 0.0,
            ]
            for t in trades
        ])
        y = np.array([
            1 if str(t.entry_quality) in ("perfect", "good") else 0
            for t in trades
        ])

        if y.sum() < 3 or (len(y) - y.sum()) < 3:
            return current, "ml_skipped_class_imbalance"

        model = XGBClassifier(n_estimators=50, max_depth=3, random_state=42, eval_metric="logloss")
        model.fit(X, y)

        # feature_importances_[1] = importancia del patrón
        # Si el patrón es importante (> 0.4), amplificamos el patrón ganador
        try:
            importance = model.feature_importances_
        except AttributeError:
            return current, "ml_no_importances"

        pattern_importance = float(importance[1]) if len(importance) > 1 else 0.5

        # Predecir con LP=1 y LP=0 para ver qué patrón favorece el modelo
        lp_prob = float(model.predict_proba([[75.0, 1.0]])[0][1])
        cl_prob = float(model.predict_proba([[75.0, 0.0]])[0][1])

        # Amplificar ligeramente el patrón preferido por el modelo
        if pattern_importance > 0.3 and lp_prob > cl_prob + 0.15:
            boost = 1.0 + pattern_importance * 0.3
            new = ScoreWeights(
                lp_inflow=_clamp(current.lp_inflow * boost),
                lp_holder=_clamp(current.lp_holder * boost),
                lp_price_stability=_clamp(current.lp_price_stability * boost),
                lp_short_pressure=_clamp(current.lp_short_pressure * boost),
                cl_short_interest=_clamp(current.cl_short_interest / boost),
                cl_funding_rate=_clamp(current.cl_funding_rate / boost),
                cl_inflow=_clamp(current.cl_inflow / boost),
                cl_holder=_clamp(current.cl_holder / boost),
            )
            return new, f"ml_boosted_lp lp_prob={lp_prob:.2f}"

        if pattern_importance > 0.3 and cl_prob > lp_prob + 0.15:
            boost = 1.0 + pattern_importance * 0.3
            new = ScoreWeights(
                lp_inflow=_clamp(current.lp_inflow / boost),
                lp_holder=_clamp(current.lp_holder / boost),
                lp_price_stability=_clamp(current.lp_price_stability / boost),
                lp_short_pressure=_clamp(current.lp_short_pressure / boost),
                cl_short_interest=_clamp(current.cl_short_interest * boost),
                cl_funding_rate=_clamp(current.cl_funding_rate * boost),
                cl_inflow=_clamp(current.cl_inflow * boost),
                cl_holder=_clamp(current.cl_holder * boost),
            )
            return new, f"ml_boosted_classic cl_prob={cl_prob:.2f}"

        return current, f"ml_no_clear_winner lp={lp_prob:.2f} cl={cl_prob:.2f}"
