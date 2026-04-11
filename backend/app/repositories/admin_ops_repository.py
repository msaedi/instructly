"""
Admin Operations Repository for MCP Admin Tools.

Provides data access methods for admin operations including:
- Booking summaries and listings
- Payment pipeline status
- Pending payouts
- User lookups and booking history
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..models.booking import Booking
from .admin_ops.booking_queries_mixin import BookingQueriesMixin
from .admin_ops.payment_queries_mixin import PaymentQueriesMixin
from .admin_ops.payout_queries_mixin import PayoutQueriesMixin
from .admin_ops.user_queries_mixin import UserQueriesMixin
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class AdminOpsRepository(
    BookingQueriesMixin,
    UserQueriesMixin,
    PaymentQueriesMixin,
    PayoutQueriesMixin,
    BaseRepository[Booking],
):
    """Repository for admin operations data access."""

    def __init__(self, db: Session) -> None:
        """Initialize with Booking model."""
        super().__init__(db, Booking)
        self.logger = logging.getLogger(__name__)
