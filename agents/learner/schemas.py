from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional


# Score numérico para promediar calidad de entrada
QUALITY_SCORE: dict[str, float] = {
    "perfect": 4.0,
    "good": 3.0,
    "early": 2.0,
    "late": 1.0,
    "bad": 0.0,
}


class PatternMetrics(BaseModel):
    pattern: str
    total_trades: int = 0
    win_count: int = 0
    win_rate: float = 0.0
    avg_pnl_pct: float = 0.0
    avg_quality_score: float = 0.0
    quality_distribution: dict[str, int] = Field(default_factory=dict)


class TradeMetrics(BaseModel):
    period_days: int
    total_trades: int = 0
    win_rate: float = 0.0
    avg_pnl_pct: float = 0.0
    avg_quality_score: float = 0.0
    perfect_count: int = 0
    good_count: int = 0
    early_count: int = 0
    late_count: int = 0
    bad_count: int = 0
    long_pump: PatternMetrics = Field(default_factory=lambda: PatternMetrics(pattern="long_pump"))
    classic: PatternMetrics = Field(default_factory=lambda: PatternMetrics(pattern="classic"))


class LearnerRun(BaseModel):
    run_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metrics: TradeMetrics
    previous_weights: dict[str, float]
    new_weights: dict[str, float]
    weight_delta: dict[str, float] = Field(default_factory=dict)
    adjustment_reason: str = ""
    trades_analyzed: int = 0
    min_trades_met: bool = False
