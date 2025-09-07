"""
Monitoring and alert history models.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
import ulid

from app.database import Base


class AlertHistory(Base):
    """Track monitoring alerts that have been sent."""

    __tablename__ = "alert_history"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # critical, warning, info
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Notification tracking
    email_sent: Mapped[bool] = mapped_column(default=False)
    github_issue_created: Mapped[bool] = mapped_column(default=False)
    github_issue_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<AlertHistory({self.alert_type}: {self.title})>"
