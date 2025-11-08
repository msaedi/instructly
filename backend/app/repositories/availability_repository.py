# backend/app/repositories/availability_repository.py
"""
AvailabilityRepository - Blackout Date Management

This repository handles blackout date operations only.
Availability data is stored in availability_days table (bitmap format).
See AvailabilityDayRepository for bitmap operations.
"""

from datetime import date
import logging
from typing import List, Optional, cast

from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.exceptions import RepositoryException
from ..core.timezone_utils import get_user_today_by_id
from ..models.availability import BlackoutDate

logger = logging.getLogger(__name__)


class AvailabilityRepository:
    """
    Repository for blackout date management.

    Note: Availability data is stored in availability_days table (bitmap format).
    This repository only handles blackout dates (vacation/unavailable dates).
    """

    def __init__(self, db: Session):
        """Initialize repository."""
        self.db = db
        self.logger = logging.getLogger(__name__)

    # Blackout Date Operations

    def get_future_blackout_dates(self, instructor_id: str) -> List[BlackoutDate]:
        """
        Get all future blackout dates for an instructor.

        Args:
            instructor_id: The instructor ID

        Returns:
            List of blackout dates ordered by date
        """
        try:
            return cast(
                List[BlackoutDate],
                self.db.query(BlackoutDate)
                .filter(
                    and_(
                        BlackoutDate.instructor_id == instructor_id,
                        BlackoutDate.date >= get_user_today_by_id(instructor_id, self.db),
                    )
                )
                .order_by(BlackoutDate.date)
                .all(),
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting blackout dates: {str(e)}")
            raise RepositoryException(f"Failed to get blackout dates: {str(e)}")

    def create_blackout_date(
        self, instructor_id: str, blackout_date: date, reason: Optional[str] = None
    ) -> BlackoutDate:
        """
        Create a new blackout date.

        Args:
            instructor_id: The instructor ID
            blackout_date: The date to blackout
            reason: Optional reason

        Returns:
            Created blackout date

        Raises:
            RepositoryException: If creation fails
        """
        try:
            blackout = BlackoutDate(instructor_id=instructor_id, date=blackout_date, reason=reason)
            self.db.add(blackout)
            self.db.flush()
            return blackout

        except IntegrityError as e:
            self.logger.error(f"Integrity error creating blackout: {str(e)}")
            raise RepositoryException(f"Blackout date already exists: {str(e)}")
        except SQLAlchemyError as e:
            self.logger.error(f"Error creating blackout: {str(e)}")
            raise RepositoryException(f"Failed to create blackout: {str(e)}")

    def flush(self) -> None:
        """Flush pending ORM changes."""
        self.db.flush()

    def delete_blackout_date(self, blackout_id: str, instructor_id: str) -> bool:
        """
        Delete a blackout date.

        Args:
            blackout_id: The blackout ID
            instructor_id: The instructor ID (for security)

        Returns:
            True if deleted, False if not found
        """
        try:
            result = (
                self.db.query(BlackoutDate)
                .filter(
                    and_(
                        BlackoutDate.id == blackout_id, BlackoutDate.instructor_id == instructor_id
                    )
                )
                .delete()
            )

            self.db.flush()
            return bool(result > 0)

        except SQLAlchemyError as e:
            self.logger.error(f"Error deleting blackout: {str(e)}")
            raise RepositoryException(f"Failed to delete blackout: {str(e)}")
