from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional


class TokenSnapshot(BaseModel):
    """Snapshot completo de un token en un momento dado. Lo consume el Detector."""

    symbol: str
    exchange: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # ── Precio y mercado ──────────────────────────────────────────────────────
    current_price: float
    price_change_1h_pct: Optional[float] = None
    price_change_24h_pct: Optional[float] = None
    volume_24h_usd: Optional[float] = None
    market_cap_usd: Optional[float] = None
    bid_ask_spread_pct: Optional[float] = None  # spread como % del mid-price

    # ── Datos on-chain: inflow hacia exchanges ────────────────────────────────
    inflow_1h_usd: Optional[float] = None
    inflow_4h_usd: Optional[float] = None
    inflow_24h_usd: Optional[float] = None

    # ── Concentración de holders ──────────────────────────────────────────────
    holder_top10_pct: Optional[float] = None   # % supply en top-10 wallets
    holder_source: Optional[str] = None        # "Etherscan" | "BSCScan" | "Helius"
    total_holders: Optional[int] = None

    # ── Futuros/Derivados (para patrón Classic) ───────────────────────────────
    funding_rate: Optional[float] = None       # % por período CCXT (negativo = bearish)
    open_interest_usd: Optional[float] = None
    short_interest_pct: Optional[float] = None # % del float en short
    long_short_ratio: Optional[float] = None   # Coinglass: longs/shorts (>1 = longs dominan)

    # ── Metadatos de calidad del snapshot ────────────────────────────────────
    onchain_available: bool = False            # True si alguna fuente on-chain devolvió datos
    fetch_errors: list[str] = Field(default_factory=list)


class MonitorCycleResult(BaseModel):
    cycle_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tokens_checked: int = 0
    snapshots_published: int = 0
    fetch_errors: int = 0
    duration_seconds: float = 0.0
