"""
Patrón B — Classic Short Squeeze

Señales:
  1. Alto short interest (> 20% del float)  → 0-35 pts
  2. Funding rate muy negativo (bearish)     → 0-25 pts
  3. Inflow masivo como activador del squeeze→ 0-25 pts
  4. Holders fuertes (no panic sellers)      → 0-15 pts
"""
from agents.monitor.schemas import TokenSnapshot
from shared.config import settings
from .schemas import PatternBreakdown, ScoreWeights


def score(snapshot: TokenSnapshot, weights: ScoreWeights) -> PatternBreakdown:
    short_s = _short_interest_signal(snapshot.short_interest_pct) * weights.cl_short_interest
    funding_s = _funding_rate_signal(snapshot.funding_rate) * weights.cl_funding_rate
    inflow_s = _inflow_activator_signal(snapshot.inflow_1h_usd) * weights.cl_inflow
    holder_s = _strong_holder_signal(snapshot.holder_top10_pct) * weights.cl_holder

    normalized = min(100.0, short_s + funding_s + inflow_s + holder_s)

    return PatternBreakdown(
        score=round(normalized, 2),
        short_interest_signal=round(short_s, 2),
        funding_rate_signal=round(funding_s, 2),
        inflow_signal=round(inflow_s, 2),
        holder_signal=round(holder_s, 2),
    )


def _short_interest_signal(short_pct: float | None) -> float:
    """Máx 35 pts. > 20% = condiciones para un squeeze."""
    if short_pct is None:
        return 0.0
    threshold = settings.short_interest_threshold  # default 20
    if short_pct >= 50:
        return 35.0
    if short_pct >= 35:
        return 27.0
    if short_pct >= threshold:
        return 15.0 + (short_pct - threshold) / (35 - threshold) * 12.0
    if short_pct >= threshold * 0.7:
        return (short_pct - threshold * 0.7) / (threshold * 0.3) * 15.0
    return 0.0


def _funding_rate_signal(funding_rate: float | None) -> float:
    """Máx 25 pts. Funding muy negativo = shorts pagando = presión acumulada."""
    if funding_rate is None:
        return 0.0
    if funding_rate <= -0.05:
        return 25.0
    if funding_rate <= -0.03:
        return 20.0
    if funding_rate <= -0.01:
        return 14.0
    if funding_rate < 0.0:
        return 7.0
    return 0.0  # funding positivo = no es classic squeeze


def _inflow_activator_signal(inflow_1h_usd: float | None) -> float:
    """
    Máx 25 pts. En un squeeze, el inflow de la ÚLTIMA HORA es el activador clave
    (diferente al Long Pump que mira 4h de acumulación silenciosa).
    """
    if inflow_1h_usd is None or inflow_1h_usd <= 0:
        return 0.0
    threshold = settings.inflow_threshold_usd * 0.25  # umbral 1h = 25% del umbral 4h
    ratio = inflow_1h_usd / threshold
    if ratio >= 5.0:
        return 25.0
    if ratio >= 1.0:
        return 12.5 + (ratio - 1.0) / 4.0 * 12.5
    return ratio * 12.5


def _strong_holder_signal(holder_pct: float | None) -> float:
    """Máx 15 pts. Manos fuertes = no se rendirán ante el squeeze."""
    if holder_pct is None:
        return 0.0
    if holder_pct >= 70:
        return 15.0
    if holder_pct >= 60:
        return 10.0
    if holder_pct >= 50:
        return 5.0
    return 0.0
