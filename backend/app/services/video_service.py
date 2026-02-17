"""VideoService: business logic for video lessons.

Handles on-demand room creation, join window validation, and auth token
generation for 100ms video calls tied to bookings.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Optional, Union

from sqlalchemy.orm import Session

from ..core.exceptions import NotFoundException, ServiceException, ValidationException
from ..integrations.hundredms_client import FakeHundredMsClient, HundredMsClient, HundredMsError
from ..models.booking import BookingStatus, LocationType
from ..repositories.factory import RepositoryFactory
from .base import BaseService, CacheInvalidationProtocol

logger = logging.getLogger(__name__)


class VideoService(BaseService):
    """Service layer for video lesson operations."""

    def __init__(
        self,
        db: Session,
        hundredms_client: Union[HundredMsClient, FakeHundredMsClient],
        cache: Optional[CacheInvalidationProtocol] = None,
    ) -> None:
        super().__init__(db, cache)
        self.hundredms_client = hundredms_client
        self.booking_repository = RepositoryFactory.create_booking_repository(db)

    @BaseService.measure_operation("join_lesson")
    def join_lesson(self, booking_id: str, user_id: str) -> dict[str, Any]:
        """Join a video lesson.

        Creates the 100ms room on-demand (first participant) and returns
        an auth token for the frontend SDK.
        """
        # 1. Look up booking — participant-filtered at DB level
        booking = self.booking_repository.get_booking_for_participant(booking_id, user_id)
        if booking is None:
            raise NotFoundException("Booking not found")

        # 2. Validate booking state
        if booking.status != BookingStatus.CONFIRMED:
            raise ValidationException("Booking is not confirmed")

        if booking.location_type != LocationType.ONLINE:
            raise ValidationException("This booking is not an online lesson")

        # 3. Validate timing
        now = datetime.now(timezone.utc)
        booking_start = booking.booking_start_utc
        join_opens_at = booking_start - timedelta(minutes=5)
        grace_minutes = min(booking.duration_minutes * 0.25, 15)
        join_closes_at = booking_start + timedelta(minutes=grace_minutes)

        if now < join_opens_at:
            raise ValidationException("Lesson join window has not opened yet")
        if now > join_closes_at:
            raise ValidationException("Lesson join window has closed")

        # 4. Determine role
        role = "host" if user_id == booking.instructor_id else "guest"

        # 5. Create or get room
        video_session = self.booking_repository.get_video_session_by_booking_id(booking_id)

        if video_session is None or video_session.room_id is None:
            try:
                room_name = f"lesson-{booking_id}"
                room = self.hundredms_client.create_room(name=room_name)
                room_id: str = room["id"]
                video_session = self.booking_repository.ensure_video_session(
                    booking_id, room_id=room_id, room_name=room_name
                )
            except HundredMsError as e:
                raise ServiceException(
                    f"100ms room creation failed: {e.message}",
                    details={"status_code": e.status_code},
                )

        # 6. Generate auth token
        try:
            token = self.hundredms_client.generate_auth_token(
                room_id=video_session.room_id,
                user_id=user_id,
                role=role,
            )
        except HundredMsError as e:
            raise ServiceException(
                f"100ms auth token generation failed: {e.message}",
                details={"status_code": e.status_code},
            )

        return {
            "auth_token": token,
            "room_id": video_session.room_id,
            "role": role,
            "booking_id": booking_id,
        }

    @BaseService.measure_operation("get_video_session_status")
    def get_video_session_status(self, booking_id: str, user_id: str) -> Optional[dict[str, Any]]:
        """Get video session status for a booking.

        Returns None if no video session exists yet.
        """
        booking = self.booking_repository.get_booking_for_participant(booking_id, user_id)
        if booking is None:
            raise NotFoundException("Booking not found")

        video_session = self.booking_repository.get_video_session_by_booking_id(booking_id)
        if video_session is None:
            return None

        return {
            "room_id": video_session.room_id,
            "session_started_at": video_session.session_started_at,
            "session_ended_at": video_session.session_ended_at,
            "instructor_joined_at": video_session.instructor_joined_at,
            "student_joined_at": video_session.student_joined_at,
        }
