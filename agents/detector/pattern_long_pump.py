"""
Patrón A — Long Pump

Señales:
  1. Inflow masivo hacia exchange (4h proxy)     → 0-40 pts
  2. Señales suplementarias — Coinglass+Etherscan → 0-18 pts
       2a. Long/Short ratio (Coinglass)           → 0-8 pts
       2b. Open Interest vs volumen               → 0-5 pts
       2c. Concentración de holders (Etherscan)   → 0-5 pts
  3. Precio estable (acumulación silenciosa)      → 0-20 pts
  4. Bajo short pressure / funding CCXT           → 0-15 pts

Máximo teórico: 93 pts (umbral de alerta: 62)
"""
from agents.monitor.schemas import TokenSnapshot
from shared.config import settings
from .schemas import PatternBreakdown, ScoreWeights


def score(snapshot: TokenSnapshot, weights: ScoreWeights) -> PatternBreakdown:
    inflow_s = _inflow_signal(snapshot.inflow_4h_usd) * weights.lp_inflow
    suppl_s  = _supplemental_signal(snapshot)          # sin weight — señal fija
    price_s  = _price_stability_signal(snapshot.price_change_24h_pct) * weights.lp_price_stability
    short_s  = _short_pressure_signal(snapshot.funding_rate) * weights.lp_short_pressure

    normalized = min(100.0, inflow_s + suppl_s + price_s + short_s)

    return PatternBreakdown(
        score=round(normalized, 2),
        inflow_signal=round(inflow_s, 2),
        holder_signal=round(suppl_s, 2),     # reutiliza campo holder_signal del schema
        price_stability_signal=round(price_s, 2),
        funding_rate_signal=round(short_s, 2),
    )


# ── Señal 1: Inflow ───────────────────────────────────────────────────────────

def _inflow_signal(inflow_usd: float | None) -> float:
    """Máx 40 pts. Escala logarítmica respecto al umbral configurado."""
    if inflow_usd is None or inflow_usd <= 0:
        return 0.0
    threshold = settings.inflow_threshold_usd
    ratio = inflow_usd / threshold
    if ratio >= 5.0:
        return 40.0
    if ratio >= 1.0:
        return 20.0 + (ratio - 1.0) / 4.0 * 20.0
    return ratio * 20.0


# ── Señal 2: Suplementaria (reemplaza holder de Glassnode) ───────────────────

def _supplemental_signal(snapshot: TokenSnapshot) -> float:
    """
    Máx 18 pts. Combina 3 sub-señales de Coinglass + Etherscan:
      - Long/Short ratio  → 0-8 pts
      - OI / volumen      → 0-5 pts
      - Holder count      → 0-5 pts
    """
    total = 0.0

    # 2a. Long/Short ratio de Coinglass (8 pts)
    # Más longs = menos resistencia al pump = señal positiva
    ls = snapshot.long_short_ratio
    if ls is not None:
        if ls >= 1.5:
            total += 8.0
        elif ls >= 1.2:
            total += 6.0
        elif ls >= 1.0:
            total += 4.0
        elif ls >= 0.8:
            total += 1.0

    # 2b. Open Interest / Volumen (5 pts)
    # OI alto relativo al volumen = grandes posiciones abiertas = movimiento potencial
    oi  = snapshot.open_interest_usd
    vol = snapshot.volume_24h_usd
    if oi is not None and vol is not None and vol > 0:
        oi_ratio = oi / vol
        if oi_ratio >= 0.5:
            total += 5.0
        elif oi_ratio >= 0.2:
            total += 3.0
        elif oi_ratio >= 0.1:
            total += 1.0

    # 2c. Holder concentration aproximada via Etherscan (5 pts)
    # Menos holders únicos = token más concentrado = pump más coordinable
    holders = snapshot.total_holders
    if holders is not None:
        if holders <= 1_000:
            total += 5.0
        elif holders <= 5_000:
            total += 3.0
        elif holders <= 15_000:
            total += 1.0

    return min(18.0, total)


# ── Señal 3: Estabilidad de precio ───────────────────────────────────────────

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
    return 0.0


# ── Señal 4: Short pressure / funding (CCXT) ─────────────────────────────────

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
    return 0.0
