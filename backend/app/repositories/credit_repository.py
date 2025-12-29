# backend/app/repositories/credit_repository.py
"""
Credit Repository for InstaInstru Platform

Encapsulates read-heavy credit queries (available/reserved/expired) to support
the credit reservation lifecycle.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import List, Optional, cast

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.core.exceptions import RepositoryException
from app.models.payment import PlatformCredit

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class CreditRepository(BaseRepository[PlatformCredit]):
    """Repository for platform credit queries."""

    def __init__(self, db: Session):
        super().__init__(db, PlatformCredit)
        self.logger = logging.getLogger(__name__)

    def get_available_credits(
        self, *, user_id: str, order_by: str = "expires_at"
    ) -> List[PlatformCredit]:
        """Return available (non-reserved, non-expired) credits for a user."""
        try:
            now = datetime.now(timezone.utc)
            query = self.db.query(PlatformCredit).filter(
                and_(
                    PlatformCredit.user_id == user_id,
                    or_(
                        PlatformCredit.status.is_(None),
                        PlatformCredit.status == "available",
                    ),
                    (PlatformCredit.expires_at.is_(None) | (PlatformCredit.expires_at > now)),
                )
            )
            if order_by == "expires_at":
                query = query.order_by(
                    PlatformCredit.expires_at.asc().nullslast(),
                    PlatformCredit.created_at.asc(),
                    PlatformCredit.id.asc(),
                )
            else:
                query = query.order_by(PlatformCredit.created_at.asc(), PlatformCredit.id.asc())
            return cast(List[PlatformCredit], query.all())
        except Exception as exc:
            self.logger.error("Failed to get available credits: %s", str(exc))
            raise RepositoryException("Failed to get available credits") from exc

    def get_reserved_credits(self, *, user_id: str) -> List[PlatformCredit]:
        """Return reserved credits for a user."""
        try:
            query = (
                self.db.query(PlatformCredit)
                .filter(
                    and_(
                        PlatformCredit.user_id == user_id,
                        PlatformCredit.status == "reserved",
                    )
                )
                .order_by(PlatformCredit.reserved_at.asc().nullslast(), PlatformCredit.id.asc())
            )
            return cast(List[PlatformCredit], query.all())
        except Exception as exc:
            self.logger.error("Failed to get reserved credits: %s", str(exc))
            raise RepositoryException("Failed to get reserved credits") from exc

    def get_reserved_credits_for_booking(self, *, booking_id: str) -> List[PlatformCredit]:
        """Return credits reserved for a specific booking."""
        try:
            query = (
                self.db.query(PlatformCredit)
                .filter(
                    and_(
                        PlatformCredit.reserved_for_booking_id == booking_id,
                        PlatformCredit.status == "reserved",
                    )
                )
                .order_by(PlatformCredit.reserved_at.asc().nullslast(), PlatformCredit.id.asc())
            )
            return cast(List[PlatformCredit], query.all())
        except Exception as exc:
            self.logger.error(
                "Failed to get reserved credits for booking %s: %s",
                booking_id,
                str(exc),
            )
            raise RepositoryException("Failed to get reserved credits for booking") from exc

    def get_credits_for_source_booking(
        self,
        *,
        booking_id: str,
        statuses: Optional[List[str]] = None,
    ) -> List[PlatformCredit]:
        """Return credits generated from the given booking."""
        try:
            query = self.db.query(PlatformCredit).filter(
                PlatformCredit.source_booking_id == booking_id
            )
            if statuses:
                query = query.filter(PlatformCredit.status.in_(statuses))
            return cast(List[PlatformCredit], query.all())
        except Exception as exc:
            self.logger.error(
                "Failed to get credits for source booking %s: %s",
                booking_id,
                str(exc),
            )
            raise RepositoryException("Failed to load source credits") from exc

    def get_total_available_credits(self, *, user_id: str) -> int:
        """Return total available credit balance in cents."""
        try:
            now = datetime.now(timezone.utc)
            result = (
                self.db.query(func.sum(PlatformCredit.amount_cents))
                .filter(
                    and_(
                        PlatformCredit.user_id == user_id,
                        or_(
                            PlatformCredit.status.is_(None),
                            PlatformCredit.status == "available",
                        ),
                        (PlatformCredit.expires_at.is_(None) | (PlatformCredit.expires_at > now)),
                    )
                )
                .scalar()
            )
            return int(result or 0)
        except Exception as exc:
            self.logger.error("Failed to total available credits: %s", str(exc))
            raise RepositoryException("Failed to total available credits") from exc

    def get_total_reserved_credits(self, *, user_id: str) -> int:
        """Return total reserved credit balance in cents."""
        try:
            result = (
                self.db.query(func.sum(PlatformCredit.reserved_amount_cents))
                .filter(
                    and_(
                        PlatformCredit.user_id == user_id,
                        PlatformCredit.status == "reserved",
                    )
                )
                .scalar()
            )
            return int(result or 0)
        except Exception as exc:
            self.logger.error("Failed to total reserved credits: %s", str(exc))
            raise RepositoryException("Failed to total reserved credits") from exc

    def get_expired_available_credits(
        self, *, as_of: Optional[datetime] = None
    ) -> List[PlatformCredit]:
        """Return available credits that have expired as of the given timestamp."""
        try:
            now = as_of or datetime.now(timezone.utc)
            credits = (
                self.db.query(PlatformCredit)
                .filter(
                    and_(
                        PlatformCredit.status == "available",
                        PlatformCredit.expires_at.is_not(None),
                        PlatformCredit.expires_at <= now,
                    )
                )
                .all()
            )
            return cast(List[PlatformCredit], credits)
        except Exception as exc:
            self.logger.error("Failed to load expired credits: %s", str(exc))
            raise RepositoryException("Failed to load expired credits") from exc


__all__ = ["CreditRepository"]
