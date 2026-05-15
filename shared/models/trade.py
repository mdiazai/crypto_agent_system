import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Float, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TradeDirection(str, enum.Enum):
    buy = "buy"
    sell = "sell"


class EntryQuality(str, enum.Enum):
    perfect = "perfect"   # precio subió >20% en primeras 4h
    good = "good"         # precio subió >10% en 12h
    early = "early"       # subió pero después de >6h
    late = "late"         # ya había subido >15% al entrar
    bad = "bad"           # stop-lossed o pérdida


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token_symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[TradeDirection] = mapped_column(
        SAEnum(TradeDirection, name="trade_direction"), nullable=False
    )
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    capital_used_usd: Mapped[float] = mapped_column(Float, nullable=False)
    entry_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pnl_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pattern_detected: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    entry_quality: Mapped[Optional[EntryQuality]] = mapped_column(
        SAEnum(EntryQuality, name="entry_quality"), nullable=True
    )
    score_at_entry: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_paper: Mapped[bool] = mapped_column(default=True, nullable=False)
    anticipation_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<Trade {self.direction.value} {self.token_symbol} @ {self.entry_price} pnl={self.pnl_pct}%>"
