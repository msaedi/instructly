"""Availability service facade and backward-compatible exports."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Optional, cast

from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.timezone_utils import get_user_now_by_id, get_user_today_by_id
from ..repositories.availability_day_repository import AvailabilityDayRepository
from ..repositories.factory import RepositoryFactory
from ..utils.bitset import windows_from_bits
from .availability.audit_events import AvailabilityAuditEventsMixin
from .availability.bitmap_io import AvailabilityBitmapIOMixin
from .availability.bitmap_write import AvailabilityBitmapWriteMixin
from .availability.blackout import AvailabilityBlackoutMixin
from .availability.cache import AvailabilityCacheMixin
from .availability.public_availability import AvailabilityPublicMixin
from .availability.reads import AvailabilityReadMixin
from .availability.types import (
    ALLOW_PAST,
    AUDIT_ENABLED,
    PERF_DEBUG,
    AvailabilityWindowInput,
    DayBitmaps,
    PreparedWeek,
    ProcessedSlot,
    SaveWeekBitmapsResult,
    SaveWeekBitsResult,
    ScheduleSlotInput,
    SlotSnapshot,
    TimeSlotResponse,
    WeekAvailabilityResult,
    build_availability_idempotency_key,
)
from .availability.validation import AvailabilityValidationMixin
from .availability.week_save import AvailabilityWeekSaveMixin
from .base import BaseService
from .config_service import ConfigService
from .search.cache_invalidation import invalidate_on_availability_change

if TYPE_CHECKING:
    from ..repositories.audit_repository import AuditRepository
    from ..repositories.availability_repository import AvailabilityRepository
    from ..repositories.bulk_operation_repository import BulkOperationRepository
    from ..repositories.conflict_checker_repository import ConflictCheckerRepository
    from .cache_service import CacheServiceSyncAdapter

__all__ = [
    "ALLOW_PAST",
    "AUDIT_ENABLED",
    "PERF_DEBUG",
    "AvailabilityService",
    "AvailabilityWindowInput",
    "DayBitmaps",
    "PreparedWeek",
    "ProcessedSlot",
    "SaveWeekBitsResult",
    "SaveWeekBitmapsResult",
    "ScheduleSlotInput",
    "SlotSnapshot",
    "TimeSlotResponse",
    "WeekAvailabilityResult",
    "date",
    "datetime",
    "build_availability_idempotency_key",
    "get_user_now_by_id",
    "get_user_today_by_id",
    "invalidate_on_availability_change",
    "settings",
    "time",
    "timedelta",
    "timezone",
    "windows_from_bits",
]


class AvailabilityService(
    AvailabilityBitmapIOMixin,
    AvailabilityAuditEventsMixin,
    AvailabilityValidationMixin,
    AvailabilityBlackoutMixin,
    AvailabilityCacheMixin,
    AvailabilityReadMixin,
    AvailabilityPublicMixin,
    AvailabilityBitmapWriteMixin,
    AvailabilityWeekSaveMixin,
    BaseService,
):
    """
    Service layer for availability operations.

    Uses bitmap-based availability storage (availability_days table).
    """

    audit_repository: "AuditRepository"

    def __init__(
        self,
        db: Session,
        cache_service: Optional["CacheServiceSyncAdapter"] = None,
        repository: Optional["AvailabilityRepository"] = None,
        bulk_repository: Optional["BulkOperationRepository"] = None,
        conflict_repository: Optional["ConflictCheckerRepository"] = None,
        config_service: Optional[ConfigService] = None,
    ):
        """Initialize availability service with optional cache and repositories."""
        super().__init__(db, cache=cache_service)
        self.cache_service = cache_service
        self.config_service = config_service or ConfigService(db)

        self.repository = repository or RepositoryFactory.create_availability_repository(db)
        self.bulk_repository = (
            bulk_repository or RepositoryFactory.create_bulk_operation_repository(db)
        )
        self.conflict_repository = (
            conflict_repository or RepositoryFactory.create_conflict_checker_repository(db)
        )
        self._bitmap_repository = AvailabilityDayRepository(db)
        self.instructor_repository = RepositoryFactory.create_instructor_profile_repository(db)
        self.event_outbox_repository = RepositoryFactory.create_event_outbox_repository(db)
        self.booking_repository = RepositoryFactory.create_booking_repository(db)
        self.audit_repository = RepositoryFactory.create_audit_repository(db)

    def _bitmap_repo(self) -> AvailabilityDayRepository:
        repo = getattr(self, "_bitmap_repository", None)
        if repo is None:
            repo = AvailabilityDayRepository(self.db)
            self._bitmap_repository = repo
        return cast(AvailabilityDayRepository, repo)
