"""Blackout date management and orphan availability cleanup."""

from __future__ import annotations

import logging

from ...core.exceptions import ConflictException, NotFoundException, RepositoryException
from ...models.availability import BlackoutDate
from ...schemas.availability_window import BlackoutDateCreate
from ..base import BaseService
from .mixin_base import AvailabilityMixinBase

logger = logging.getLogger(__name__)


class AvailabilityBlackoutMixin(AvailabilityMixinBase):
    """Blackout date management and orphan availability cleanup."""

    @BaseService.measure_operation("get_blackout_dates")
    def get_blackout_dates(self, instructor_id: str) -> list[BlackoutDate]:
        """Get instructor's future blackout dates."""
        try:
            return list(self.repository.get_future_blackout_dates(instructor_id))
        except RepositoryException as error:
            logger.error("Error getting blackout dates: %s", error)
            return []

    @BaseService.measure_operation("add_blackout_date")
    def add_blackout_date(
        self, instructor_id: str, blackout_data: BlackoutDateCreate
    ) -> BlackoutDate:
        """Add a blackout date for an instructor."""
        existing_blackouts = self.repository.get_future_blackout_dates(instructor_id)
        if any(blackout.date == blackout_data.date for blackout in existing_blackouts):
            raise ConflictException("Blackout date already exists")

        with self.transaction():
            try:
                return self.repository.create_blackout_date(
                    instructor_id, blackout_data.date, blackout_data.reason
                )
            except RepositoryException as error:
                if "already exists" in str(error):
                    raise ConflictException("Blackout date already exists")
                raise

    @BaseService.measure_operation("delete_blackout_date")
    def delete_blackout_date(self, instructor_id: str, blackout_id: str) -> bool:
        """Delete a blackout date."""
        with self.transaction():
            try:
                success = self.repository.delete_blackout_date(blackout_id, instructor_id)
                if not success:
                    raise NotFoundException("Blackout date not found")
                return True
            except RepositoryException as error:
                logger.error("Error deleting blackout date: %s", error)
                raise

    @BaseService.measure_operation("delete_orphan_availability_for_instructor")
    def delete_orphan_availability_for_instructor(
        self,
        instructor_id: str,
        *,
        keep_days_with_bookings: bool = True,
    ) -> int:
        """
        Delete orphaned AvailabilityDay rows for an instructor.

        Bitmap-era invariant: availability is not cascaded on instructor delete, so we
        proactively purge orphaned days that have no bookings while preserving any day
        that has (or had) a booking on that date.
        """
        protected_dates = None
        if keep_days_with_bookings:
            protected_dates = self.booking_repository.get_distinct_booking_dates(instructor_id)

        deleted = self._bitmap_repo().delete_days_for_instructor(
            instructor_id, exclude_dates=protected_dates
        )
        if deleted:
            logger.info(
                "availability_cleanup: instructor_id=%s purged_days=%s keep_days_with_bookings=%s",
                instructor_id,
                deleted,
                keep_days_with_bookings,
            )
        return int(deleted)
