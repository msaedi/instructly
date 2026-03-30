"""Booking repository façade backed by focused internal mixins."""

from datetime import date, datetime
import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session, joinedload

from ..core.exceptions import RepositoryException
from ..core.timezone_utils import get_user_now_by_id, get_user_today_by_id
from ..models.booking import Booking
from .base_repository import BaseRepository
from .booking.admin_query_mixin import BookingAdminQueryMixin
from .booking.conflict_mixin import BookingConflictMixin
from .booking.conversation_mixin import BookingConversationMixin
from .booking.detail_query_mixin import BookingDetailQueryMixin
from .booking.list_query_mixin import BookingListQueryMixin
from .booking.payment_query_mixin import BookingPaymentQueryMixin
from .booking.satellite_mixin import BookingSatelliteMixin
from .booking.stats_mixin import BookingStatsMixin
from .booking.status_mutation_mixin import BookingStatusMutationMixin
from .cached_repository_mixin import CachedRepositoryMixin

logger = logging.getLogger(__name__)


class BookingRepository(
    BookingSatelliteMixin,
    BookingConflictMixin,
    BookingListQueryMixin,
    BookingDetailQueryMixin,
    BookingStatusMutationMixin,
    BookingPaymentQueryMixin,
    BookingStatsMixin,
    BookingAdminQueryMixin,
    BookingConversationMixin,
    BaseRepository[Booking],
    CachedRepositoryMixin,
):
    """Repository façade for booking data access with caching support."""

    def __init__(self, db: Session, cache_service: Optional[Any] = None):
        """Initialize with Booking model and optional cache service."""
        super().__init__(db, Booking)
        self.logger = logging.getLogger(__name__)
        self.init_cache(cache_service)
        self._external_call_lock_savepoint: Any | None = None

    def create(self, **kwargs: Any) -> Booking:
        """Create a booking, exposing integrity errors for conflict handling."""
        try:
            return super().create(**kwargs)
        except RepositoryException as exc:
            if isinstance(exc.__cause__, IntegrityError):
                raise exc.__cause__
            raise

    def acquire_transaction_advisory_lock(self, lock_key: int) -> None:
        """Acquire a transaction-scoped advisory lock when running on PostgreSQL."""
        get_bind = getattr(self.db, "get_bind", None)
        if not callable(get_bind):
            return

        try:
            bind = get_bind()
        except Exception:
            return

        dialect_name = getattr(getattr(bind, "dialect", None), "name", None)
        if dialect_name != "postgresql":
            return

        self.db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )

    def _get_user_now(self, user_id: str) -> datetime:
        """Proxy timezone-aware current time lookup through the façade module."""
        return get_user_now_by_id(user_id, self.db)

    def _get_user_today(self, user_id: str) -> date:
        """Proxy timezone-aware today lookup through the façade module."""
        return get_user_today_by_id(user_id, self.db)

    def _apply_eager_loading(self, query: Query) -> Query:
        """Override eager loading used by BaseRepository.get_by_id()."""
        return query.options(
            joinedload(Booking.student),
            joinedload(Booking.instructor),
            joinedload(Booking.instructor_service),
            joinedload(Booking.payment_detail),
            joinedload(Booking.reschedule_detail),
            joinedload(Booking.no_show_detail),
            joinedload(Booking.lock_detail),
            joinedload(Booking.dispute),
            joinedload(Booking.transfer),
            joinedload(Booking.video_session),
        )
