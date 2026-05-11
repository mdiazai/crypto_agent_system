from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


# ── Tokens ────────────────────────────────────────────────────────────────────

class TokenCandidateResponse(BaseModel):
    id: int
    symbol: str
    exchange: str
    status: str
    detection_score: Optional[float]
    pattern_type: str
    holder_concentration_pct: Optional[float]
    inflow_usd: Optional[float]
    alert_sent: bool
    added_at: datetime
    last_checked: Optional[datetime]
    notes: Optional[str]


# ── Trades ────────────────────────────────────────────────────────────────────

class TradeResponse(BaseModel):
    id: int
    token_symbol: str
    exchange: str
    direction: str
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    capital_used_usd: float
    entry_time: datetime
    exit_time: Optional[datetime]
    pnl_usd: Optional[float]
    pnl_pct: Optional[float]
    pattern_detected: Optional[str]
    entry_quality: Optional[str]
    score_at_entry: Optional[float]
    is_paper: bool


class TradeSummaryResponse(BaseModel):
    total_trades: int
    open_trades: int
    closed_trades: int
    win_rate: float
    total_pnl_usd: float
    avg_pnl_pct: float
    best_trade_pct: Optional[float]
    worst_trade_pct: Optional[float]
    is_paper: bool


class ManualTradeRequest(BaseModel):
    symbol: str
    direction: str = Field(..., pattern="^(buy|sell)$")
    capital_usd: float = Field(..., gt=0)
    exchange: str = Field(..., pattern="^(mexc|bitget)$")


# ── Config ────────────────────────────────────────────────────────────────────

class ConfigResponse(BaseModel):
    paper_trading: bool
    capital_total_usd: float
    mexc_allocation_pct: float
    bitget_allocation_pct: float
    alert_threshold: float
    llm_validation_threshold: float
    monitor_interval_seconds: int
    discovery_schedule_hour: int
    stop_loss_pct: float
    take_profit_1_pct: float
    take_profit_2_pct: float
    take_profit_3_pct: float
    max_daily_loss_pct: float
    max_consecutive_losses: int
    inflow_threshold_usd: float
    holder_concentration_threshold: float


class ConfigUpdateRequest(BaseModel):
    capital_total_usd: Optional[float] = Field(None, gt=0)
    mexc_allocation_pct: Optional[float] = Field(None, ge=0, le=100)
    bitget_allocation_pct: Optional[float] = Field(None, ge=0, le=100)
    alert_threshold: Optional[float] = Field(None, ge=0, le=100)
    stop_loss_pct: Optional[float] = Field(None, gt=0, le=50)
    max_daily_loss_pct: Optional[float] = Field(None, gt=0, le=100)
    inflow_threshold_usd: Optional[float] = Field(None, gt=0)
    holder_concentration_threshold: Optional[float] = Field(None, ge=0, le=100)


# ── Generic ───────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str
    detail: Optional[Any] = None

class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=200)
