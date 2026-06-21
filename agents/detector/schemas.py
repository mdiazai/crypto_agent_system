from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, Literal


class ScoreWeights(BaseModel):
    """Pesos ajustables por el Learner. Cada peso amplifica/reduce la señal correspondiente."""
    # Long Pump
    lp_inflow: float = 1.0
    lp_holder: float = 1.0
    lp_price_stability: float = 1.0
    lp_short_pressure: float = 1.0
    # Classic Short Squeeze
    cl_short_interest: float = 1.0
    cl_funding_rate: float = 1.0
    cl_inflow: float = 1.0
    cl_holder: float = 1.0


class PatternBreakdown(BaseModel):
    """Desglose de señales para un patrón específico."""
    score: float = Field(ge=0.0, le=100.0)
    inflow_signal: float = 0.0
    holder_signal: float = 0.0
    price_stability_signal: float = 0.0
    short_interest_signal: float = 0.0
    funding_rate_signal: float = 0.0


class ScoredToken(BaseModel):
    """Resultado del Detector. Lo consumen el Scorer y el Executor."""
    symbol: str
    exchange: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Scores por patrón
    long_pump: PatternBreakdown
    classic_squeeze: PatternBreakdown

    # Score final
    composite_score: float = Field(ge=0.0, le=100.0)
    dominant_pattern: Literal["long_pump", "classic", "unknown"]

    # Datos clave del snapshot (redundados para que el Scorer no necesite el snapshot)
    current_price: float
    inflow_4h_usd: Optional[float] = None
    holder_top10_pct: Optional[float] = None
    holder_source: Optional[str] = None
    volume_24h_usd: Optional[float] = None
    funding_rate: Optional[float] = None

    # Análisis del LLM (solo si score >= LLM_VALIDATION_THRESHOLD)
    llm_analysis: Optional[str] = None
    llm_validated: bool = False

    # Flag para que el Executor sepa si actuar
    above_alert_threshold: bool = False


class WeightUpdate(BaseModel):
    """Publicado por el Learner para actualizar los pesos del ScoreEngine."""
    weights: ScoreWeights
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str = ""
