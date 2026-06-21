from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, Literal


class TakeProfitLevel(BaseModel):
    gain_pct: float        # % de ganancia para activar este nivel
    sell_pct: float        # % de la cantidad ORIGINAL a vender
    triggered: bool = False
    triggered_at: Optional[datetime] = None
    fill_price: Optional[float] = None


class PositionState(BaseModel):
    trade_id: int
    symbol: str
    exchange: str
    entry_price: float
    total_quantity: float      # cantidad original comprada
    remaining_quantity: float  # cantidad todavía en cartera
    capital_usd: float
    stop_loss_price: float
    take_profit_levels: list[TakeProfitLevel]
    opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_paper: bool
    score_at_entry: float = 0.0
    pattern_detected: str = ""


class OrderResult(BaseModel):
    success: bool
    price: Optional[float] = None
    quantity: Optional[float] = None
    cost_usd: Optional[float] = None
    order_id: Optional[str] = None
    error: Optional[str] = None
    is_paper: bool = False


TradeAction = Literal["buy", "sell_tp1", "sell_tp2", "sell_final", "sell_stop_loss", "sell_max_hold"]


class TradeResult(BaseModel):
    trade_id: int
    symbol: str
    exchange: str
    action: TradeAction
    price: float
    quantity: float
    pnl_usd: Optional[float] = None
    pnl_pct: Optional[float] = None
    reason: str = ""
    is_paper: bool
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DailyStats(BaseModel):
    date: str               # YYYY-MM-DD UTC
    realized_pnl_usd: float = 0.0
    trades_count: int = 0
    winning_trades: int = 0
    consecutive_losses: int = 0
