import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Float, DateTime, Boolean, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class NarrativeTradeDirection(str, enum.Enum):
    buy = "buy"
    sell = "sell"


class NarrativeTradeStatus(str, enum.Enum):
    open = "open"
    closed = "closed"


class NarrativeTrade(Base):
    __tablename__ = "narrative_trades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    direction: Mapped[NarrativeTradeDirection] = mapped_column(
        SAEnum(NarrativeTradeDirection, name="narrative_trade_direction"),
        default=NarrativeTradeDirection.buy,
        nullable=False,
    )

    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    capital_usd: Mapped[float] = mapped_column(Float, nullable=False)

    stop_loss_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target1_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target2_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    entry_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    narrative_at_entry: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    pnl_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    is_paper: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[NarrativeTradeStatus] = mapped_column(
        SAEnum(NarrativeTradeStatus, name="narrative_trade_status"),
        default=NarrativeTradeStatus.open,
        nullable=False,
        index=True,
    )
    open_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    close_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    entry_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    educational_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<NarrativeTrade {self.direction.value} {self.symbol} @ {self.entry_price} pnl={self.pnl_pct}%>"
