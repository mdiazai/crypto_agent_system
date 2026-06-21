from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Float, DateTime, BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token_symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    pattern_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    telegram_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    def __repr__(self) -> str:
        return f"<Alert {self.token_symbol} score={self.score} at={self.sent_at}>"
