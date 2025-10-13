"""Platform configuration models."""

from sqlalchemy import JSON, Column, DateTime, Text
from sqlalchemy.sql import func

from ..database import Base


class PlatformConfig(Base):
    """Key/value configuration stored as JSON for dynamic platform settings."""

    __tablename__ = "platform_config"

    key = Column(Text, primary_key=True)
    value_json = Column(JSON, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - repr is trivial
        return f"<PlatformConfig key={self.key}>"


__all__ = ["PlatformConfig"]
