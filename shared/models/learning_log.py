from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Float, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


class LearningLog(Base):
    __tablename__ = "learning_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    tokens_evaluated: Mapped[int] = mapped_column(Integer, nullable=False)
    accuracy_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_entry_quality: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weights_adjusted: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<LearningLog id={self.id} accuracy={self.accuracy_rate} at={self.created_at}>"
