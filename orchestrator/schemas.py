from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, Literal


AgentStatus = Literal["healthy", "degraded", "unhealthy", "unknown"]
OverallStatus = Literal["healthy", "degraded", "unhealthy"]


class AgentHealth(BaseModel):
    name: str
    status: AgentStatus = "unknown"
    last_activity: Optional[datetime] = None
    restart_count: int = 0
    detail: str = ""


class SystemHealth(BaseModel):
    overall: OverallStatus = "healthy"
    paper_trading: bool = True
    circuit_breaker_active: bool = False
    agents: list[AgentHealth] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MarketContext(BaseModel):
    signals_last_30m: int = 0
    avg_score_last_30m: float = 0.0
    is_anomalous: bool = False
    anomaly_reason: str = ""
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ThresholdAdvice(BaseModel):
    action: Literal["raise_threshold", "lower_threshold", "keep_threshold"]
    new_threshold: Optional[float] = None
    reason: str = ""
    confidence: float = 0.0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
