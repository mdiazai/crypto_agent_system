from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DiagnosticsLog(Base):
    __tablename__ = "diagnostics_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    diagnosis: Mapped[str] = mapped_column(Text, nullable=False)
    fix_command: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<DiagnosticsLog severity={self.severity} at={self.run_at}>"
