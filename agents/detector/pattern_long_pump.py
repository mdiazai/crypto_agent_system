"""
Patrón A — Long Pump

Señales:
  1. Inflow masivo hacia exchange (1-4h)   → 0-40 pts
  2. Holder concentration > 60% en top-10  → 0-25 pts
  3. Precio estable (acumulación silenciosa)→ 0-20 pts
  4. Bajo short pressure (funding positivo) → 0-15 pts
"""
from agents.monitor.schemas import TokenSnapshot
from shared.config import settings
from .schemas import PatternBreakdown, ScoreWeights


def score(snapshot: TokenSnapshot, weights: ScoreWeights) -> PatternBreakdown:
    inflow_s = _inflow_signal(snapshot.inflow_4h_usd) * weights.lp_inflow
    holder_s = _holder_signal(snapshot.holder_top10_pct) * weights.lp_holder
    price_s = _price_stability_signal(snapshot.price_change_24h_pct) * weights.lp_price_stability
    short_s = _short_pressure_signal(snapshot.funding_rate) * weights.lp_short_pressure

    normalized = min(100.0, inflow_s + holder_s + price_s + short_s)

    return PatternBreakdown(
        score=round(normalized, 2),
        inflow_signal=round(inflow_s, 2),
        holder_signal=round(holder_s, 2),
        price_stability_signal=round(price_s, 2),
        funding_rate_signal=round(short_s, 2),
    )


def _inflow_signal(inflow_usd: float | None) -> float:
    """Máx 40 pts. Escala logarítmica respecto al umbral configurado."""
    if inflow_usd is None or inflow_usd <= 0:
        return 0.0
    threshold = settings.inflow_threshold_usd
    ratio = inflow_usd / threshold
    if ratio >= 5.0:
        return 40.0
    if ratio >= 1.0:
        # 20-40 pts lineales entre 1x y 5x threshold
        return 20.0 + (ratio - 1.0) / 4.0 * 20.0
    # 0-20 pts por debajo del threshold
    return ratio * 20.0


def _holder_signal(holder_pct: float | None) -> float:
    """Máx 25 pts. Concentración > 60% activa la señal."""
    if holder_pct is None:
        return 0.0
    threshold = settings.holder_concentration_threshold  # default 60
    if holder_pct >= 85:
        return 25.0
    if holder_pct >= 75:
        return 20.0
    if holder_pct >= threshold:
        # 12.5-20 pts lineales entre threshold y 75%
        return 12.5 + (holder_pct - threshold) / (75 - threshold) * 7.5
    if holder_pct >= threshold * 0.8:
        return (holder_pct - threshold * 0.8) / (threshold * 0.2) * 12.5
    return 0.0


def _price_stability_signal(change_24h: float | None) -> float:
    """Máx 20 pts. Precio estable = acumulación silenciosa."""
    if change_24h is None:
        return 10.0  # neutral sin datos
    abs_change = abs(change_24h)
    if abs_change <= 1.0:
        return 20.0
    if abs_change <= 3.0:
        return 17.0
    if abs_change <= 7.0:
        return 12.0
    if abs_change <= 15.0:
        return 5.0
    return 0.0  # ya está moviendo fuerte


def _short_pressure_signal(funding_rate: float | None) -> float:
    """Máx 15 pts. Funding positivo = longs dominan = menos resistencia al pump."""
    if funding_rate is None:
        return 7.5  # neutral sin datos
    if funding_rate >= 0.01:
        return 15.0
    if funding_rate >= 0.005:
        return 12.0
    if funding_rate >= 0.0:
        return 8.0
    if funding_rate >= -0.005:
        return 4.0
    return 0.0  # funding muy negativo = mucho shorting
