"""Satellite table accessors for booking-related one-to-one records."""

from datetime import datetime
from typing import Any, Optional, cast

from sqlalchemy.exc import IntegrityError, OperationalError

# PostgreSQL SQLSTATE for a non-blocking lock acquisition that could not be granted.
_LOCK_NOT_AVAILABLE_PGCODE = "55P03"

from ...core.exceptions import RepositoryException
from ...models.booking import Booking, BookingStatus
from ...models.booking_dispute import BookingDispute
from ...models.booking_lock import BookingLock
from ...models.booking_no_show import BookingNoShow
from ...models.booking_payment import BookingPayment
from ...models.booking_reschedule import BookingReschedule
from ...models.booking_transfer import BookingTransfer
from ...models.booking_video_session import BookingVideoSession
from .mixin_base import BookingRepositoryMixinBase


class BookingSatelliteMixin(BookingRepositoryMixinBase):
    """Satellite table accessors — dispute, transfer, no-show, lock, payment, and video."""

    @staticmethod
    def _rollback_savepoint(savepoint: Any | None) -> None:
        """Rollback an active savepoint when one was successfully created."""
        if savepoint is None:
            return
        if not getattr(savepoint, "is_active", True):
            return
        savepoint.rollback()

    def get_dispute_by_booking_id(self, booking_id: str) -> Optional[BookingDispute]:
        """Return dispute satellite row for a booking, if present."""
        try:
            dispute = cast(
                Optional[BookingDispute],
                self.db.query(BookingDispute)
                .filter(BookingDispute.booking_id == booking_id)
                .one_or_none(),
            )
            return dispute
        except Exception as e:
            self.logger.error("Error getting dispute for booking %s: %s", booking_id, str(e))
            raise RepositoryException(f"Failed to get booking dispute: {str(e)}")

    def ensure_dispute(self, booking_id: str) -> BookingDispute:
        """Get or create dispute satellite row for a booking."""
        dispute = self.get_dispute_by_booking_id(booking_id)
        if dispute is not None:
            return dispute
        nested: Any | None = None
        try:
            nested = self.db.begin_nested()
            dispute = BookingDispute(booking_id=booking_id)
            self.db.add(dispute)
            self.db.flush()
            return dispute
        except IntegrityError:
            if nested is None:
                raise
            self._rollback_savepoint(nested)
            dispute = self.get_dispute_by_booking_id(booking_id)
            if dispute is not None:
                return dispute
            raise RepositoryException(
                f"Failed to ensure booking dispute after retry for booking {booking_id}"
            )
        except Exception:
            self._rollback_savepoint(nested)
            raise

    def get_transfer_by_booking_id(self, booking_id: str) -> Optional[BookingTransfer]:
        """Return transfer satellite row for a booking, if present."""
        try:
            transfer = cast(
                Optional[BookingTransfer],
                self.db.query(BookingTransfer)
                .filter(BookingTransfer.booking_id == booking_id)
                .one_or_none(),
            )
            return transfer
        except Exception as e:
            self.logger.error("Error getting transfer for booking %s: %s", booking_id, str(e))
            raise RepositoryException(f"Failed to get booking transfer: {str(e)}")

    def ensure_transfer(self, booking_id: str) -> BookingTransfer:
        """Get or create transfer satellite row for a booking."""
        transfer = self.get_transfer_by_booking_id(booking_id)
        if transfer is not None:
            return transfer
        nested: Any | None = None
        try:
            nested = self.db.begin_nested()
            transfer = BookingTransfer(booking_id=booking_id)
            self.db.add(transfer)
            self.db.flush()
            return transfer
        except IntegrityError:
            if nested is None:
                raise
            self._rollback_savepoint(nested)
            transfer = self.get_transfer_by_booking_id(booking_id)
            if transfer is not None:
                return transfer
            raise RepositoryException(
                f"Failed to ensure booking transfer after retry for booking {booking_id}"
            )
        except Exception:
            self._rollback_savepoint(nested)
            raise

    def get_no_show_by_booking_id(self, booking_id: str) -> Optional[BookingNoShow]:
        """Return no-show satellite row for a booking, if present."""
        try:
            no_show = cast(
                Optional[BookingNoShow],
                self.db.query(BookingNoShow)
                .filter(BookingNoShow.booking_id == booking_id)
                .one_or_none(),
            )
            return no_show
        except Exception as e:
            self.logger.error("Error getting no-show for booking %s: %s", booking_id, str(e))
            raise RepositoryException(f"Failed to get booking no-show: {str(e)}")

    def ensure_no_show(self, booking_id: str) -> BookingNoShow:
        """Get or create no-show satellite row for a booking."""
        no_show = self.get_no_show_by_booking_id(booking_id)
        if no_show is not None:
            return no_show
        nested: Any | None = None
        try:
            nested = self.db.begin_nested()
            no_show = BookingNoShow(booking_id=booking_id)
            self.db.add(no_show)
            self.db.flush()
            return no_show
        except IntegrityError:
            if nested is None:
                raise
            self._rollback_savepoint(nested)
            no_show = self.get_no_show_by_booking_id(booking_id)
            if no_show is not None:
                return no_show
            raise RepositoryException(
                f"Failed to ensure booking no-show after retry for booking {booking_id}"
            )
        except Exception:
            self._rollback_savepoint(nested)
            raise

    def get_lock_by_booking_id(self, booking_id: str) -> Optional[BookingLock]:
        """Return lock satellite row for a booking, if present."""
        try:
            lock = cast(
                Optional[BookingLock],
                self.db.query(BookingLock)
                .filter(BookingLock.booking_id == booking_id)
                .one_or_none(),
            )
            return lock
        except Exception as e:
            self.logger.error("Error getting lock for booking %s: %s", booking_id, str(e))
            raise RepositoryException(f"Failed to get booking lock: {str(e)}")

    def ensure_lock(self, booking_id: str) -> BookingLock:
        """Get or create lock satellite row for a booking."""
        lock = self.get_lock_by_booking_id(booking_id)
        if lock is not None:
            return lock
        nested: Any | None = None
        try:
            nested = self.db.begin_nested()
            lock = BookingLock(booking_id=booking_id)
            self.db.add(lock)
            self.db.flush()
            return lock
        except IntegrityError:
            if nested is None:
                raise
            self._rollback_savepoint(nested)
            lock = self.get_lock_by_booking_id(booking_id)
            if lock is not None:
                return lock
            raise RepositoryException(
                f"Failed to ensure booking lock after retry for booking {booking_id}"
            )
        except Exception:
            self._rollback_savepoint(nested)
            raise

    def get_reschedule_by_booking_id(self, booking_id: str) -> Optional[BookingReschedule]:
        """Return reschedule satellite row for a booking, if present."""
        try:
            reschedule = cast(
                Optional[BookingReschedule],
                self.db.query(BookingReschedule)
                .filter(BookingReschedule.booking_id == booking_id)
                .one_or_none(),
            )
            return reschedule
        except Exception as e:
            self.logger.error("Error getting reschedule for booking %s: %s", booking_id, str(e))
            raise RepositoryException(f"Failed to get booking reschedule: {str(e)}")

    def ensure_reschedule(self, booking_id: str) -> BookingReschedule:
        """Get or create reschedule satellite row for a booking."""
        reschedule = self.get_reschedule_by_booking_id(booking_id)
        if reschedule is not None:
            return reschedule
        nested: Any | None = None
        try:
            nested = self.db.begin_nested()
            reschedule = BookingReschedule(booking_id=booking_id)
            self.db.add(reschedule)
            self.db.flush()
            return reschedule
        except IntegrityError:
            if nested is None:
                raise
            self._rollback_savepoint(nested)
            reschedule = self.get_reschedule_by_booking_id(booking_id)
            if reschedule is not None:
                return reschedule
            raise RepositoryException(
                f"Failed to ensure booking reschedule after retry for booking {booking_id}"
            )
        except Exception:
            self._rollback_savepoint(nested)
            raise

    def get_payment_by_booking_id(self, booking_id: str) -> Optional[BookingPayment]:
        """Return payment satellite row for a booking, if present."""
        try:
            payment = cast(
                Optional[BookingPayment],
                self.db.query(BookingPayment)
                .filter(BookingPayment.booking_id == booking_id)
                .one_or_none(),
            )
            return payment
        except Exception as e:
            self.logger.error("Error getting payment for booking %s: %s", booking_id, str(e))
            raise RepositoryException(f"Failed to get booking payment: {str(e)}")

    def atomic_confirm_if_pending(self, booking_id: str, confirmed_at: datetime) -> int:
        """Atomically confirm a booking only if it is currently PENDING.

        Uses ``FOR UPDATE NOWAIT`` so concurrent webhook workers return fast
        (0 rows affected) instead of blocking on a lock held by a peer. This
        prevents thread-pool exhaustion when Stripe bursts duplicate deliveries.
        """
        try:
            booking = (
                self.db.query(Booking)
                .filter(
                    Booking.id == booking_id,
                    Booking.status == BookingStatus.PENDING.value,
                )
                .with_for_update(nowait=True)
                .one_or_none()
            )
        except OperationalError as exc:
            pgcode = getattr(getattr(exc, "orig", None), "pgcode", None)
            if pgcode == _LOCK_NOT_AVAILABLE_PGCODE:
                return 0
            raise
        if booking is None:
            return 0
        booking.mark_confirmed(confirmed_at=confirmed_at)
        return 1

    def ensure_payment(self, booking_id: str) -> BookingPayment:
        """Get or create payment satellite row for a booking."""
        payment = self.get_payment_by_booking_id(booking_id)
        if payment is not None:
            return payment
        nested: Any | None = None
        try:
            nested = self.db.begin_nested()
            payment = BookingPayment(booking_id=booking_id)
            self.db.add(payment)
            self.db.flush()
            return payment
        except IntegrityError:
            if nested is None:
                raise
            self._rollback_savepoint(nested)
            payment = self.get_payment_by_booking_id(booking_id)
            if payment is not None:
                return payment
            raise RepositoryException(
                f"Failed to ensure booking payment after retry for booking {booking_id}"
            )
        except Exception:
            self._rollback_savepoint(nested)
            raise

    def get_video_session_by_booking_id(self, booking_id: str) -> Optional[BookingVideoSession]:
        """Return video session satellite row for a booking, if present."""
        try:
            video_session = cast(
                Optional[BookingVideoSession],
                self.db.query(BookingVideoSession)
                .filter(BookingVideoSession.booking_id == booking_id)
                .one_or_none(),
            )
            return video_session
        except Exception as e:
            self.logger.error("Error getting video session for booking %s: %s", booking_id, str(e))
            raise RepositoryException(f"Failed to get booking video session: {str(e)}")

    def ensure_video_session(
        self, booking_id: str, room_id: str, room_name: str | None = None
    ) -> BookingVideoSession:
        """Get or create video session satellite row for a booking."""
        video_session = self.get_video_session_by_booking_id(booking_id)
        if video_session is not None:
            return video_session
        nested: Any | None = None
        try:
            nested = self.db.begin_nested()
            video_session = BookingVideoSession(
                booking_id=booking_id, room_id=room_id, room_name=room_name
            )
            self.db.add(video_session)
            self.db.flush()
            return video_session
        except IntegrityError:
            if nested is None:
                raise
            self._rollback_savepoint(nested)
            video_session = self.get_video_session_by_booking_id(booking_id)
            if video_session is not None:
                return video_session
            raise RepositoryException(
                f"Failed to ensure booking video session after retry for booking {booking_id}"
            )
        except Exception:
            self._rollback_savepoint(nested)
            raise

    def release_lock_for_external_call(self) -> None:
        """Release row-level lock before outbound API calls."""
        savepoint = self._external_call_lock_savepoint
        self._external_call_lock_savepoint = None
        if savepoint is None:
            return
        self._rollback_savepoint(savepoint)
