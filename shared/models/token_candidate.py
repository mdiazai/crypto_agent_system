import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Float, DateTime, Boolean, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TokenStatus(str, enum.Enum):
    active = "active"
    removed = "removed"


class PatternType(str, enum.Enum):
    long_pump = "long_pump"
    classic = "classic"
    unknown = "unknown"


class TokenCandidate(Base):
    __tablename__ = "token_candidates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[TokenStatus] = mapped_column(
        SAEnum(TokenStatus, name="token_status"),
        default=TokenStatus.active,
        nullable=False,
        index=True,
    )
    detection_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pattern_type: Mapped[PatternType] = mapped_column(
        SAEnum(PatternType, name="pattern_type"),
        default=PatternType.unknown,
        nullable=False,
    )
    holder_concentration_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    inflow_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    alert_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<TokenCandidate {self.symbol} score={self.detection_score} status={self.status}>"
