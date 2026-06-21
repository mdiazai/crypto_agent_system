from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class TokenData(BaseModel):
    symbol: str
    base: str
    quote: str = "USDT"
    exchange: str
    coingecko_id: Optional[str] = None
    market_cap_usd: Optional[float] = None
    volume_24h_usd: Optional[float] = None
    volume_to_mcap_ratio: Optional[float] = None
    launch_date: Optional[datetime] = None
    token_age_days: Optional[int] = None
    current_price: Optional[float] = None
    price_change_24h_pct: Optional[float] = None
    eth_contract: Optional[str] = None
    chain: Optional[str] = None


class DiscoveryResult(BaseModel):
    run_at: datetime = Field(default_factory=datetime.utcnow)
    tokens_scanned: int = 0
    candidates_found: int = 0
    candidates_removed: int = 0
    candidate_symbols: list[str] = Field(default_factory=list)
