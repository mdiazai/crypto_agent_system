import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Float, Integer, BigInteger, DateTime, Boolean, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class NarrativeCandidateStatus(str, enum.Enum):
    candidate = "candidate"
    alerted = "alerted"
    entered = "entered"
    archived = "archived"


class NarrativeCandidate(Base):
    __tablename__ = "narrative_candidates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False, default="spot")

    narrative_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    onchain_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    technical_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    combined_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    narrative_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    galaxy_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    alt_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    social_volume_24h: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    panic_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    latest_news: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    smart_money_netflow: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    holder_concentration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    rsi_1d: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    volume_24h_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    status: Mapped[NarrativeCandidateStatus] = mapped_column(
        SAEnum(NarrativeCandidateStatus, name="narrative_candidate_status"),
        default=NarrativeCandidateStatus.candidate,
        nullable=False,
        index=True,
    )
    alert_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_checked: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<NarrativeCandidate {self.symbol} score={self.combined_score} status={self.status}>"
