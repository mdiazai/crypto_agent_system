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
    volume_24h_usd: Optional[float] = None
    alert_sent: bool
    added_at: datetime
    last_checked: Optional[datetime]
    notes: Optional[str]
    score_breakdown: Optional[dict] = None


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


# ── Narrative Swing Module ───────────────────────────────────────────────────

class NarrativeCandidateResponse(BaseModel):
    symbol: str
    exchange: str
    narrative_score: Optional[float]
    onchain_score: Optional[float]
    technical_score: Optional[float]
    combined_score: Optional[float]
    narrative_description: Optional[str]
    galaxy_score: Optional[float]
    alt_rank: Optional[int]
    smart_money_netflow: Optional[float]
    holder_concentration: Optional[float]
    rsi_1d: Optional[float]
    price_usd: Optional[float]
    status: str
    last_checked: datetime


class NarrativeTradeResponse(BaseModel):
    id: int
    symbol: str
    direction: str
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    capital_usd: float
    stop_loss_price: Optional[float]
    target1_price: Optional[float]
    target2_price: Optional[float]
    entry_score: Optional[float]
    pnl_usd: Optional[float]
    pnl_pct: Optional[float]
    is_paper: bool
    status: str
    close_reason: Optional[str]
    entry_time: datetime
    exit_time: Optional[datetime]


class NarrativeGateResponse(BaseModel):
    days_elapsed: int
    days_required: int
    trades_closed: int
    trades_required: int
    win_rate: float
    win_rate_required: float
    profit_factor: float
    profit_factor_required: float
    gate_status: str
