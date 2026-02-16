"""
Integration tests for booking_service.py targeting uncovered code paths.

Coverage focus:
- cancel_booking() full flow (lines 1657-1779)
- complete_booking() flow (lines 3476-3590)
- mark_no_show() and no-show handling (lines 3889-4199)
- retry_authorization() (lines 1438-1574)
- validate_booking_prerequisites() (lines 4598-4676)
- _check_conflicts_and_rules() (lines 4676-4769)

Strategy: Real DB, real repositories, mocked external services (Stripe, notifications)
"""

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BookingConflictException,
    BusinessRuleException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.booking_lock import BookingLock
from app.models.booking_no_show import BookingNoShow
from app.models.booking_payment import BookingPayment
from app.models.booking_reschedule import BookingReschedule
from app.models.booking_transfer import BookingTransfer
from app.models.payment import PaymentMethod
from app.models.service_catalog import InstructorService as Service, ServiceCatalog
from app.models.user import User
from app.schemas.booking import BookingCreate
from app.services.booking_service import BookingService
from app.utils.time_utils import time_to_minutes
from tests._utils.bitmap_avail import seed_day
from tests.factories.booking_builders import create_booking_pg_safe
from tests.utils.time import now_trimmed, start_just_over_24h, start_within_24h


def create_test_booking(
    db: Session,
    student: User,
    instructor: User,
    service: Service,
    booking_date: date,
    start_time: time = time(10, 0),
    end_time: time = time(11, 0),
    status: BookingStatus = BookingStatus.CONFIRMED,
    payment_status: str = PaymentStatus.AUTHORIZED.value,
    offset_index: int = 0,
    **extra_fields,
) -> Booking:
    """Helper to create test bookings with required fields."""
    catalog = db.query(ServiceCatalog).filter(
        ServiceCatalog.id == service.service_catalog_id
    ).first()
    service_name = catalog.name if catalog else "Test Service"

    duration_minutes = time_to_minutes(end_time) - time_to_minutes(start_time)
    if duration_minutes <= 0:
        duration_minutes = 60

    return create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=service.id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        duration_minutes=duration_minutes,
        hourly_rate=service.hourly_rate,
        total_price=float(service.hourly_rate) * (duration_minutes / 60),
        service_name=service_name,
        status=status,
        payment_status=payment_status,
        location_type="neutral_location",
        offset_index=offset_index,
        cancel_duplicate=True,
        **extra_fields,
    )


def _ensure_default_payment_method(db: Session, user: User) -> str:
    from app.repositories.payment_repository import PaymentRepository

    payment_repo = PaymentRepository(db)
    method = payment_repo.save_payment_method(
        user_id=user.id,
        stripe_payment_method_id=f"pm_{generate_ulid()}",
        last4="4242",
        brand="visa",
        is_default=True,
    )
    db.commit()
    return method.stripe_payment_method_id


def _ensure_stripe_customer(db: Session, user: User) -> str:
    from app.repositories.payment_repository import PaymentRepository

    payment_repo = PaymentRepository(db)
    existing = payment_repo.get_customer_by_user_id(user.id)
    if existing and existing.stripe_customer_id:
        return existing.stripe_customer_id
    customer = payment_repo.create_customer_record(
        user_id=user.id, stripe_customer_id=f"cus_{generate_ulid()}"
    )
    db.commit()
    return customer.stripe_customer_id


def _ensure_connected_account(db: Session, instructor: User) -> str:
    from app.repositories.payment_repository import PaymentRepository

    profile = instructor.instructor_profile
    payment_repo = PaymentRepository(db)
    account = payment_repo.get_connected_account_by_instructor_id(profile.id)
    if account:
        return account.stripe_account_id
    account = payment_repo.create_connected_account_record(
        profile.id,
        f"acct_{generate_ulid()}",
        onboarding_completed=True,
    )
    db.commit()
    return account.stripe_account_id


def _get_transfer(db: Session, booking_id: str) -> BookingTransfer | None:
    return (
        db.query(BookingTransfer).filter(BookingTransfer.booking_id == booking_id).one_or_none()
    )


def _reload_payment_detail(db: Session, booking: Booking) -> None:
    """Reload the payment_detail relationship after db.refresh (lazy='noload' won't auto-load)."""
    booking.payment_detail = (
        db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).one_or_none()
    )


def _get_no_show(db: Session, booking_id: str) -> BookingNoShow | None:
    return db.query(BookingNoShow).filter(BookingNoShow.booking_id == booking_id).one_or_none()


def _upsert_no_show(db: Session, booking_id: str, **fields) -> BookingNoShow:
    no_show = _get_no_show(db, booking_id)
    if no_show is None:
        no_show = BookingNoShow(booking_id=booking_id)
        db.add(no_show)
    for key, value in fields.items():
        setattr(no_show, key, value)
    return no_show


def _get_lock(db: Session, booking_id: str) -> BookingLock | None:
    return db.query(BookingLock).filter(BookingLock.booking_id == booking_id).one_or_none()


def _upsert_lock(db: Session, booking_id: str, **fields) -> BookingLock:
    lock = _get_lock(db, booking_id)
    if lock is None:
        lock = BookingLock(booking_id=booking_id)
        db.add(lock)
    for key, value in fields.items():
        setattr(lock, key, value)
    return lock


def _get_reschedule(db: Session, booking_id: str) -> BookingReschedule | None:
    return (
        db.query(BookingReschedule).filter(BookingReschedule.booking_id == booking_id).one_or_none()
    )


def _upsert_reschedule(db: Session, booking_id: str, **fields) -> BookingReschedule:
    reschedule = _get_reschedule(db, booking_id)
    if reschedule is None:
        reschedule = BookingReschedule(booking_id=booking_id)
        db.add(reschedule)
    for key, value in fields.items():
        setattr(reschedule, key, value)
    return reschedule


@pytest.fixture(autouse=True)
def _no_price_floors(disable_price_floors):
    """Disable price floors for these tests."""
    yield


@pytest.fixture
def booking_service_integration(db: Session, mock_notification_service):
    """
    Create BookingService with:
    - Real database session
    - Real repositories (created automatically)
    - Mocked notification service
    - Mocked event publisher
    """
    svc = BookingService(
        db,
        mock_notification_service,
        event_publisher=Mock(),
    )
    return svc


@pytest.fixture
def instructor_service(db: Session, test_instructor_with_availability: User) -> Service:
    """Get first active service for test instructor."""
    profile = test_instructor_with_availability.instructor_profile
    if profile is None:
        from app.models.instructor import InstructorProfile

        profile = db.query(InstructorProfile).filter(
            InstructorProfile.user_id == test_instructor_with_availability.id
        ).first()
    return db.query(Service).filter(
        Service.instructor_profile_id == profile.id,
        Service.is_active == True
    ).first()


class TestCancelBookingIntegration:
    """Integration tests for cancel_booking covering lines 1634-1779."""

    def test_cancel_booking_confirmed_by_student(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test student cancelling a confirmed booking >24h before lesson."""
        future_date = date.today() + timedelta(days=5)
        seed_day(db, test_instructor_with_availability.id, future_date, [("10:00", "12:00")])

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(10, 0), time(11, 0),
        )
        db.commit()

        result = booking_service_integration.cancel_booking(
            booking.id, test_student, reason="Changed my plans"
        )

        assert result.status == BookingStatus.CANCELLED
        assert result.cancelled_at is not None
        assert result.cancellation_reason == "Changed my plans"


class TestBookingServiceHelpersIntegration:
    """Integration tests for booking service helper methods."""

    def test_booking_window_to_minutes_missing_times(self):
        """Missing times fall back to (0, 0)."""
        booking = SimpleNamespace(start_time=None, end_time=None)

        assert BookingService._booking_window_to_minutes(booking) == (0, 0)

    def test_booking_window_to_minutes_rolls_over_midnight(self):
        """End time before start time rolls to 24:00."""
        booking = SimpleNamespace(start_time=time(23, 0), end_time=time(1, 0))

        start, end = BookingService._booking_window_to_minutes(booking)
        assert start == 23 * 60
        assert end == 24 * 60

    def test_resolve_actor_payload_from_dict(self, booking_service_integration: BookingService):
        """Dict actors preserve explicit id/role."""
        payload = booking_service_integration._resolve_actor_payload(
            {"id": "actor_1", "role": "admin"}, default_role="system"
        )

        assert payload["id"] == "actor_1"
        assert payload["role"] == "admin"

    def test_resolve_actor_payload_from_roles(self, booking_service_integration: BookingService):
        """Role list is used when actor has no direct role field."""
        actor = SimpleNamespace(id="actor_2", roles=[SimpleNamespace(name="student")])

        payload = booking_service_integration._resolve_actor_payload(actor, default_role="system")

        assert payload["id"] == "actor_2"
        assert payload["role"] == "student"

    def test_cancel_booking_by_instructor(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test instructor cancelling a booking."""
        future_date = date.today() + timedelta(days=3)
        seed_day(db, test_instructor_with_availability.id, future_date, [("14:00", "16:00")])

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(14, 0), time(15, 0),
            offset_index=1,  # Avoid overlap
        )
        db.commit()

        result = booking_service_integration.cancel_booking(
            booking.id, test_instructor_with_availability, reason="Emergency"
        )

        assert result.status == BookingStatus.CANCELLED
        assert result.cancelled_at is not None

    def test_cancel_booking_not_found(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
    ):
        """Test cancellation of non-existent booking raises NotFoundException."""
        fake_id = generate_ulid()

        with pytest.raises(NotFoundException, match="Booking not found"):
            booking_service_integration.cancel_booking(fake_id, test_student)

    def test_cancel_already_cancelled_booking(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test cancelling an already cancelled booking is a no-op or raises."""
        future_date = date.today() + timedelta(days=4)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(10, 0), time(11, 0),
            status=BookingStatus.CANCELLED,
            offset_index=2,
        )
        db.commit()

        # The service may either raise or return the already-cancelled booking
        # Either behavior is acceptable
        result = booking_service_integration.cancel_booking(booking.id, test_student)
        assert result.status == BookingStatus.CANCELLED


class TestCompleteBookingIntegration:
    """Integration tests for complete_booking covering lines 3476-3590."""

    def test_complete_booking_success(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test successful booking completion by instructor."""
        past_date = date.today() - timedelta(days=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(10, 0), time(11, 0),
            offset_index=3,
        )
        db.commit()

        result = booking_service_integration.complete_booking(
            booking.id, test_instructor_with_availability
        )

        assert result.status == BookingStatus.COMPLETED
        assert result.completed_at is not None

    def test_complete_booking_not_instructor(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test that non-instructor cannot complete booking."""
        past_date = date.today() - timedelta(days=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(10, 0), time(11, 0),
            offset_index=4,
        )
        db.commit()

        with pytest.raises(ValidationException, match="Only instructors"):
            booking_service_integration.complete_booking(booking.id, test_student)

    def test_complete_booking_wrong_instructor(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        test_instructor_2: User,
        instructor_service: Service,
    ):
        """Test that different instructor cannot complete booking."""
        past_date = date.today() - timedelta(days=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(10, 0), time(11, 0),
            offset_index=5,
        )
        db.commit()

        with pytest.raises(ValidationException, match="your own bookings"):
            booking_service_integration.complete_booking(booking.id, test_instructor_2)

    def test_complete_booking_not_confirmed(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test completing a non-confirmed booking fails."""
        past_date = date.today() - timedelta(days=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(10, 0), time(11, 0),
            status=BookingStatus.CANCELLED,
            offset_index=6,
        )
        db.commit()

        with pytest.raises(BusinessRuleException, match="confirmed bookings"):
            booking_service_integration.complete_booking(
                booking.id, test_instructor_with_availability
            )


class TestMarkNoShowIntegration:
    """Integration tests for mark_no_show covering lines 4391-4460."""

    def test_mark_no_show_success(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test instructor marking a no-show."""
        past_date = date.today() - timedelta(days=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(10, 0), time(11, 0),
            offset_index=7,
        )
        db.commit()

        result = booking_service_integration.mark_no_show(
            booking.id, test_instructor_with_availability
        )

        # mark_no_show sets status to NO_SHOW (may or may not set no_show_reported_at)
        assert result.status == BookingStatus.NO_SHOW

    def test_mark_no_show_non_instructor_fails(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test that non-instructor cannot mark no-show."""
        past_date = date.today() - timedelta(days=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(10, 0), time(11, 0),
            offset_index=8,
        )
        db.commit()

        with pytest.raises(ValidationException, match="Only instructors"):
            booking_service_integration.mark_no_show(booking.id, test_student)


class TestReportNoShowIntegration:
    """Integration tests for report_no_show covering lines 3765-3867."""

    def test_report_no_show_by_student(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test student reporting instructor no-show."""
        now = now_trimmed()
        start_dt = now - timedelta(hours=2)
        end_dt = start_dt + timedelta(hours=1)
        if end_dt.date() != start_dt.date():
            start_dt = datetime.combine(
                (now - timedelta(days=1)).date(),
                time(10, 0),
                tzinfo=timezone.utc,
            )
            end_dt = start_dt + timedelta(hours=1)
        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            start_dt.date(), start_dt.time(), end_dt.time(),
            offset_index=9,
            lesson_timezone="UTC",
            instructor_tz_at_booking="UTC",
            student_tz_at_booking="UTC",
        )
        db.commit()

        # Students can report instructor no-shows
        result = booking_service_integration.report_no_show(
            booking_id=booking.id,
            reporter=test_student,  # Student reports instructor no-show
            no_show_type="instructor",  # Instructor was the no-show
            reason="Instructor did not arrive",
        )

        # Result may be a dict or Booking object
        if isinstance(result, dict):
            assert result.get("status") == "success" or "booking_id" in result
        else:
            no_show = _get_no_show(db, booking.id)
            assert no_show is not None
            assert no_show.no_show_reported_at is not None
            assert no_show.no_show_type == "instructor"

    def test_report_no_show_booking_not_found(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_instructor_with_availability: User,
    ):
        """Test reporting no-show for non-existent booking."""
        fake_id = generate_ulid()

        with pytest.raises(NotFoundException, match="Booking not found"):
            booking_service_integration.report_no_show(
                booking_id=fake_id,
                reporter=test_instructor_with_availability,
                no_show_type="student",  # Valid values: "student" or "instructor"
                reason="Student did not arrive",
            )


class TestDisputeNoShowIntegration:
    """Integration tests for dispute_no_show covering lines 3867-3951."""

    def test_dispute_no_show_success(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test student disputing a no-show report."""
        past_date = date.today() - timedelta(days=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(10, 0), time(11, 0),
            offset_index=10,
        )
        _upsert_no_show(
            db,
            booking.id,
            no_show_reported_at=datetime.now(timezone.utc),
            no_show_type="student",  # Valid values: "student" or "instructor"
        )
        db.commit()

        result = booking_service_integration.dispute_no_show(
            booking_id=booking.id,
            disputer=test_student,
            reason="I was there on time",
        )

        # Result can be a dict or a Booking object depending on implementation
        if isinstance(result, dict):
            assert result.get("disputed") == True or result.get("no_show_disputed") == True
        else:
            no_show = _get_no_show(db, booking.id)
            assert no_show is not None
            assert no_show.no_show_disputed is True
            assert no_show.no_show_dispute_reason == "I was there on time"

    def test_dispute_no_show_no_report_exists(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test disputing when no no-show report exists."""
        past_date = date.today() - timedelta(days=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(10, 0), time(11, 0),
            offset_index=11,
        )
        db.commit()

        with pytest.raises(BusinessRuleException, match="No no-show report exists"):
            booking_service_integration.dispute_no_show(
                booking_id=booking.id,
                disputer=test_student,
                reason="I was there",
            )


class TestResolveNoShowIntegration:
    """Integration tests for resolve_no_show covering lines 3951-4205."""

    def test_resolve_no_show_instructor_refund(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
        admin_user: User,
    ):
        """Confirm instructor no-show triggers refund settlement."""
        from unittest.mock import MagicMock, patch

        past_date = date.today() - timedelta(days=1)
        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(10, 0), time(11, 0),
            payment_status=PaymentStatus.SETTLED.value,
            payment_intent_id="pi_no_show_refund",
            offset_index=12,
        )
        _upsert_no_show(
            db,
            booking.id,
            no_show_reported_at=datetime.now(timezone.utc) - timedelta(hours=1),
            no_show_type="instructor",
        )
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.refund_payment.return_value = {
            "refund_id": "re_no_show_refund",
            "amount_refunded": 5000,
        }

        with patch("app.services.stripe_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.resolve_no_show(
                booking_id=booking.id,
                resolution="confirmed_no_dispute",
                resolved_by=admin_user,
                admin_notes="refund instructor no-show",
            )

        db.refresh(booking)
        _reload_payment_detail(db, booking)
        transfer = _get_transfer(db, booking.id)
        assert result.get("success") is True
        assert booking.status == BookingStatus.NO_SHOW
        assert booking.payment_detail.payment_status == PaymentStatus.SETTLED.value
        assert booking.payment_detail.settlement_outcome == "instructor_no_show_full_refund"
        assert transfer is not None
        assert transfer.refund_id == "re_no_show_refund"

    def test_resolve_no_show_student_payout(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
        admin_user: User,
    ):
        """Confirm student no-show captures and settles payout."""
        from unittest.mock import MagicMock, patch

        past_date = date.today() - timedelta(days=1)
        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(12, 0), time(13, 0),
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_no_show_capture",
            offset_index=13,
        )
        _upsert_no_show(
            db,
            booking.id,
            no_show_reported_at=datetime.now(timezone.utc) - timedelta(hours=1),
            no_show_type="student",
        )
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.capture_payment_intent.return_value = {
            "transfer_id": "tr_no_show",
            "amount_received": 10000,
            "transfer_amount": 8000,
        }

        with patch("app.services.stripe_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.resolve_no_show(
                booking_id=booking.id,
                resolution="confirmed_no_dispute",
                resolved_by=admin_user,
                admin_notes="capture student no-show",
            )

        db.refresh(booking)
        _reload_payment_detail(db, booking)
        transfer = _get_transfer(db, booking.id)
        assert result.get("success") is True
        assert booking.status == BookingStatus.NO_SHOW
        assert booking.payment_detail.payment_status == PaymentStatus.SETTLED.value
        assert booking.payment_detail.settlement_outcome == "student_no_show_full_payout"
        assert transfer is not None
        assert transfer.stripe_transfer_id == "tr_no_show"


class TestValidateBookingPrerequisitesIntegration:
    """Integration tests for _validate_booking_prerequisites covering lines 4598-4676."""

    def test_validate_prerequisites_non_student_fails(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test that non-student cannot create booking."""
        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=instructor_service.id,
            booking_date=date.today() + timedelta(days=2),
            start_time=time(10, 0),
            selected_duration=60,
            end_time=time(11, 0),
            meeting_location="Test Location",
            location_lat=40.751,
            location_lng=-73.989,
            location_type="neutral_location",
        )

        with pytest.raises(ValidationException, match="Only students can create bookings"):
            booking_service_integration._validate_booking_prerequisites(
                test_instructor_with_availability, booking_data
            )

    def test_validate_prerequisites_account_restricted_fails(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Restricted accounts cannot create bookings."""
        test_student.account_restricted = True
        db.commit()

        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=instructor_service.id,
            booking_date=date.today() + timedelta(days=2),
            start_time=time(10, 0),
            selected_duration=60,
            end_time=time(11, 0),
            meeting_location="Test Location",
            location_lat=40.751,
            location_lng=-73.989,
            location_type="neutral_location",
        )

        with pytest.raises(BusinessRuleException, match="restricted"):
            booking_service_integration._validate_booking_prerequisites(
                test_student, booking_data
            )

    def test_validate_prerequisites_service_not_found(
        self,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
    ):
        """Missing service ID raises NotFoundException."""
        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=generate_ulid(),
            booking_date=date.today() + timedelta(days=2),
            start_time=time(10, 0),
            selected_duration=60,
            end_time=time(11, 0),
            meeting_location="Test Location",
            location_lat=40.751,
            location_lng=-73.989,
            location_type="neutral_location",
        )

        with pytest.raises(NotFoundException, match="Service not found"):
            booking_service_integration._validate_booking_prerequisites(
                test_student, booking_data
            )

    def test_validate_prerequisites_instructor_profile_missing(
        self,
        booking_service_integration: BookingService,
        test_student: User,
        instructor_service: Service,
    ):
        """Missing instructor profile raises NotFoundException."""
        booking_data = BookingCreate(
            instructor_id=generate_ulid(),
            instructor_service_id=instructor_service.id,
            booking_date=date.today() + timedelta(days=2),
            start_time=time(10, 0),
            selected_duration=60,
            end_time=time(11, 0),
            meeting_location="Test Location",
            location_lat=40.751,
            location_lng=-73.989,
            location_type="neutral_location",
        )

        with pytest.raises(NotFoundException, match="Instructor profile not found"):
            booking_service_integration._validate_booking_prerequisites(
                test_student, booking_data
            )

    def test_validate_prerequisites_service_mismatch(
        self,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_2: User,
        instructor_service: Service,
    ):
        """Service must belong to the specified instructor."""
        booking_data = BookingCreate(
            instructor_id=test_instructor_2.id,
            instructor_service_id=instructor_service.id,
            booking_date=date.today() + timedelta(days=2),
            start_time=time(10, 0),
            selected_duration=60,
            end_time=time(11, 0),
            meeting_location="Test Location",
            location_lat=40.751,
            location_lng=-73.989,
            location_type="neutral_location",
        )

        with pytest.raises(ValidationException, match="Service does not belong"):
            booking_service_integration._validate_booking_prerequisites(
                test_student, booking_data
            )

    def test_validate_prerequisites_instructor_inactive(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Inactive instructor accounts cannot receive bookings."""
        test_instructor_with_availability.account_status = "suspended"
        db.commit()

        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=instructor_service.id,
            booking_date=date.today() + timedelta(days=2),
            start_time=time(10, 0),
            selected_duration=60,
            end_time=time(11, 0),
            meeting_location="Test Location",
            location_lat=40.751,
            location_lng=-73.989,
            location_type="neutral_location",
        )

        with pytest.raises(BusinessRuleException, match="temporarily suspended"):
            booking_service_integration._validate_booking_prerequisites(
                test_student, booking_data
            )


class TestCheckConflictsAndRulesIntegration:
    """Integration tests for _check_conflicts_and_rules covering lines 4676-4769."""

    def test_student_time_conflict_detected(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test that student double-booking is detected."""
        future_date = date.today() + timedelta(days=3)
        seed_day(db, test_instructor_with_availability.id, future_date, [("10:00", "13:00")])

        profile = test_instructor_with_availability.instructor_profile

        create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(10, 0), time(11, 0),
            offset_index=12,
        )
        db.commit()

        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=instructor_service.id,
            booking_date=future_date,
            start_time=time(10, 30),
            selected_duration=60,
            end_time=time(11, 30),
            meeting_location="Test Location",
            location_lat=40.751,
            location_lng=-73.989,
            location_type="neutral_location",
        )

        with pytest.raises(BookingConflictException):
            booking_service_integration._check_conflicts_and_rules(
                booking_data, instructor_service, profile, test_student
            )


class TestRetryAuthorizationIntegration:
    """Integration tests for retry_authorization covering lines 1438-1574."""

    def test_retry_auth_booking_not_found(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
    ):
        """Test retry auth with non-existent booking."""
        fake_id = generate_ulid()

        with pytest.raises(NotFoundException, match="Booking not found"):
            booking_service_integration.retry_authorization(
                booking_id=fake_id, user=test_student
            )

    def test_retry_auth_wrong_payment_status(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test retry auth fails when payment is already authorized."""
        future_date = date.today() + timedelta(days=2)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(10, 0), time(11, 0),
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=13,
        )
        db.commit()

        with pytest.raises(BusinessRuleException, match="Cannot retry payment"):
            booking_service_integration.retry_authorization(
                booking_id=booking.id, user=test_student
            )

    def test_retry_auth_success_with_existing_intent(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Retry succeeds when confirming an existing PaymentIntent."""
        future_date = date.today() + timedelta(days=2)
        default_method_id = _ensure_default_payment_method(db, test_student)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(10, 0), time(11, 0),
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            payment_intent_id="pi_existing_auth",
            offset_index=32,
        )
        db.commit()

        mock_stripe = Mock()
        mock_stripe.build_charge_context.return_value = SimpleNamespace(
            student_pay_cents=5000,
            application_fee_cents=500,
            applied_credit_cents=0,
        )
        mock_stripe.confirm_payment_intent.return_value = SimpleNamespace(
            status="requires_capture"
        )

        with patch("app.services.stripe_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.retry_authorization(
                booking_id=booking.id, user=test_student
            )

        db.refresh(booking)
        _reload_payment_detail(db, booking)
        assert result["success"] is True
        assert booking.payment_detail.payment_status == PaymentStatus.AUTHORIZED.value
        assert booking.payment_detail.payment_method_id == default_method_id

    def test_retry_auth_credits_only(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Retry succeeds with credits only and skips Stripe confirmation."""
        future_date = date.today() + timedelta(days=3)
        _ensure_default_payment_method(db, test_student)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(9, 0), time(10, 0),
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            offset_index=33,
        )
        booking.payment_detail.auth_failure_count = 2
        booking.payment_detail.auth_last_error = "prior_failure"
        db.commit()

        mock_stripe = Mock()
        mock_stripe.build_charge_context.return_value = SimpleNamespace(
            student_pay_cents=0,
            applied_credit_cents=5000,
            application_fee_cents=0,
        )

        with patch("app.services.stripe_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.retry_authorization(
                booking_id=booking.id, user=test_student
            )

        db.refresh(booking)
        _reload_payment_detail(db, booking)
        assert result["success"] is True
        assert booking.payment_detail.payment_status == PaymentStatus.AUTHORIZED.value
        assert booking.payment_detail.auth_failure_count == 0
        assert booking.payment_detail.auth_last_error is None

    def test_retry_auth_stripe_error_increments_failure_count(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Stripe error during retry increments failure count and stores error."""
        future_date = date.today() + timedelta(days=2)
        _ensure_default_payment_method(db, test_student)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(13, 0), time(14, 0),
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            offset_index=34,
        )
        booking.payment_detail.auth_failure_count = 1
        db.commit()

        mock_stripe = Mock()
        mock_stripe.build_charge_context.return_value = SimpleNamespace(
            student_pay_cents=5000,
            application_fee_cents=500,
            applied_credit_cents=0,
        )
        mock_stripe.create_or_retry_booking_payment_intent.side_effect = Exception("Card declined")

        with patch("app.services.stripe_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.retry_authorization(
                booking_id=booking.id, user=test_student
            )

        db.refresh(booking)
        _reload_payment_detail(db, booking)
        assert result["success"] is False
        assert booking.payment_detail.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
        assert booking.payment_detail.auth_failure_count == 2
        assert booking.payment_detail.auth_last_error == "Card declined"

    def test_retry_auth_non_student_forbidden(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Only the booking student can retry authorization."""
        future_date = date.today() + timedelta(days=2)
        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(11, 0), time(12, 0),
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            offset_index=35,
        )
        db.commit()

        with pytest.raises(ForbiddenException, match="Only the student"):
            booking_service_integration.retry_authorization(
                booking_id=booking.id, user=test_instructor_with_availability
            )

    def test_retry_auth_cancelled_booking(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Cancelled bookings cannot be retried."""
        future_date = date.today() + timedelta(days=2)
        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(11, 0), time(12, 0),
            status=BookingStatus.CANCELLED,
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            offset_index=36,
        )
        db.commit()

        with pytest.raises(BusinessRuleException, match="cancelled"):
            booking_service_integration.retry_authorization(
                booking_id=booking.id, user=test_student
            )

    def test_retry_auth_missing_payment_method(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Missing payment methods should raise validation errors."""
        future_date = date.today() + timedelta(days=2)
        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(11, 0), time(12, 0),
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            payment_method_id=None,
            offset_index=37,
        )
        db.query(PaymentMethod).filter(PaymentMethod.user_id == test_student.id).delete()
        db.commit()

        with pytest.raises(ValidationException, match="No payment method"):
            booking_service_integration.retry_authorization(
                booking_id=booking.id, user=test_student
            )

    def test_retry_auth_success_with_new_intent(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Retry creates a new PaymentIntent when none exists."""
        future_date = date.today() + timedelta(days=2)
        _ensure_default_payment_method(db, test_student)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(12, 0), time(13, 0),
            payment_status=PaymentStatus.SCHEDULED.value,
            payment_intent_id=None,
            offset_index=38,
        )
        db.commit()

        mock_stripe = Mock()
        mock_stripe.build_charge_context.return_value = SimpleNamespace(
            student_pay_cents=5000,
            application_fee_cents=500,
            applied_credit_cents=0,
        )
        mock_stripe.create_or_retry_booking_payment_intent.return_value = SimpleNamespace(
            id="pi_new_auth",
            status="requires_capture",
        )

        with patch("app.services.stripe_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.retry_authorization(
                booking_id=booking.id, user=test_student
            )

        db.refresh(booking)
        _reload_payment_detail(db, booking)
        assert result["success"] is True
        assert booking.payment_detail.payment_status == PaymentStatus.AUTHORIZED.value
        assert booking.payment_detail.payment_intent_id == "pi_new_auth"


class TestGetBookingsForUserIntegration:
    """Integration tests for get_bookings_for_user covering lines 3284-3331."""

    def test_get_bookings_for_student(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test retrieving bookings for a student."""
        future_date = date.today() + timedelta(days=4)

        create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(10, 0), time(11, 0),
            offset_index=14,
        )
        db.commit()

        result = booking_service_integration.get_bookings_for_user(test_student)

        assert len(result) >= 1
        assert all(b.student_id == test_student.id for b in result)

    def test_get_bookings_for_instructor(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test retrieving bookings for an instructor."""
        future_date = date.today() + timedelta(days=5)

        create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(14, 0), time(15, 0),
            offset_index=15,
        )
        db.commit()

        result = booking_service_integration.get_bookings_for_user(
            test_instructor_with_availability
        )

        assert len(result) >= 1
        assert all(b.instructor_id == test_instructor_with_availability.id for b in result)


class TestGetBookingForUserIntegration:
    """Integration tests for get_booking_for_user covering lines 3396-3415."""

    def test_get_booking_student_authorized(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test student can view their own booking."""
        future_date = date.today() + timedelta(days=3)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(10, 0), time(11, 0),
            offset_index=16,
        )
        db.commit()

        result = booking_service_integration.get_booking_for_user(
            booking.id, test_student
        )

        assert result is not None
        assert result.id == booking.id

    def test_get_booking_unauthorized_user(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        test_instructor_2: User,
        instructor_service: Service,
    ):
        """Test unauthorized user cannot view booking."""
        future_date = date.today() + timedelta(days=3)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(10, 0), time(11, 0),
            offset_index=17,
        )
        db.commit()

        result = booking_service_integration.get_booking_for_user(
            booking.id, test_instructor_2
        )

        assert result is None


class TestFindBookingOpportunitiesIntegration:
    """Integration tests for find_booking_opportunities."""

    def test_find_booking_opportunities_respects_conflicts(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Opportunities exclude existing booking windows."""
        target_date = date.today() + timedelta(days=4)
        seed_day(db, test_instructor_with_availability.id, target_date, [("09:00", "12:00")])

        create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            target_date,
            time(10, 0),
            time(11, 0),
            offset_index=52,
        )
        db.commit()

        opportunities = booking_service_integration.find_booking_opportunities(
            instructor_id=test_instructor_with_availability.id,
            target_date=target_date,
            target_duration_minutes=60,
        )

        assert opportunities
        for slot in opportunities:
            slot_start = time.fromisoformat(slot["start_time"])
            slot_end = time.fromisoformat(slot["end_time"])
            assert not (slot_start < time(11, 0) and slot_end > time(10, 0))

    def test_find_booking_opportunities_no_availability_returns_empty(
        self,
        booking_service_integration: BookingService,
        test_instructor_with_availability: User,
    ):
        """No availability yields no opportunities."""
        target_date = date.today() + timedelta(days=30)
        opportunities = booking_service_integration.find_booking_opportunities(
            instructor_id=test_instructor_with_availability.id,
            target_date=target_date,
            target_duration_minutes=60,
        )

        assert opportunities == []


class TestCancelBookingWithoutStripeIntegration:
    """Integration tests for cancel_booking_without_stripe covering lines 1782-1836."""

    def test_cancel_without_stripe_clears_payment_intent(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test cancel_booking_without_stripe clears payment_intent_id."""
        future_date = date.today() + timedelta(days=4)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(10, 0), time(11, 0),
            payment_intent_id="pi_test_12345",
            offset_index=18,
        )
        db.commit()

        booking_service_integration.cancel_booking_without_stripe(
            booking.id, test_student, "Test reason", clear_payment_intent=True
        )

        db.refresh(booking)
        _reload_payment_detail(db, booking)
        assert booking.status == BookingStatus.CANCELLED
        assert booking.payment_detail.payment_intent_id is None


class TestActivateLockForRescheduleIntegration:
    """Integration tests for activate_lock_for_reschedule covering lines 1866-2031."""

    def test_activate_lock_booking_not_found(
        self,
        db: Session,
        booking_service_integration: BookingService,
    ):
        """Test lock activation with non-existent booking."""
        fake_id = generate_ulid()

        with pytest.raises(NotFoundException, match="Booking not found"):
            booking_service_integration.activate_lock_for_reschedule(fake_id)

    def test_activate_lock_already_locked(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test lock activation when already locked."""
        future_date = date.today() + timedelta(days=2)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(10, 0), time(11, 0),
            payment_status=PaymentStatus.LOCKED.value,  # Correct enum value
            offset_index=19,
        )
        db.commit()

        result = booking_service_integration.activate_lock_for_reschedule(booking.id)

        assert result.get("already_locked") == True

    def test_activate_lock_invalid_payment_status_raises(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Reject lock activation when payment status is not eligible."""
        future_date = date.today() + timedelta(days=3)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(11, 0), time(12, 0),
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            offset_index=57,
        )
        db.commit()

        with pytest.raises(BusinessRuleException, match="Cannot lock booking"):
            booking_service_integration.activate_lock_for_reschedule(booking.id)

    def test_activate_lock_capture_failure_raises(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Capture failure aborts lock activation."""
        from unittest.mock import MagicMock, patch

        future_date = date.today() + timedelta(days=4)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(10, 0), time(11, 0),
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_lock_capture_fail",
            offset_index=58,
        )
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.capture_payment_intent.side_effect = Exception("capture failed")

        with patch("app.services.stripe_service.StripeService", return_value=mock_stripe):
            with pytest.raises(BusinessRuleException, match="Unable to lock payment"):
                booking_service_integration.activate_lock_for_reschedule(booking.id)

    def test_activate_lock_reverse_failure_marks_manual_review(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Transfer reversal failure marks booking for manual review."""
        from unittest.mock import MagicMock, patch

        future_date = date.today() + timedelta(days=4)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(12, 0), time(13, 0),
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_lock_reverse_fail",
            offset_index=59,
        )
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.capture_payment_intent.return_value = {
            "transfer_id": "tr_lock_reverse_fail",
            "transfer_amount": 8000,
            "amount_received": 10000,
        }
        mock_stripe.reverse_transfer.side_effect = Exception("reverse failed")

        with patch("app.services.stripe_service.StripeService", return_value=mock_stripe):
            with pytest.raises(BusinessRuleException, match="Unable to lock payment"):
                booking_service_integration.activate_lock_for_reschedule(booking.id)

        db.refresh(booking)
        transfer = _get_transfer(db, booking.id)
        assert booking.payment_detail.payment_status == PaymentStatus.MANUAL_REVIEW.value
        assert transfer is not None
        assert transfer.transfer_reversal_failed is True
        assert transfer.transfer_reversal_error == "reverse failed"

    def test_activate_lock_success_sets_locked(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Successful lock activation persists locked state."""
        from unittest.mock import MagicMock, patch

        future_date = date.today() + timedelta(days=4)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(9, 0), time(10, 0),
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_lock_success",
            offset_index=60,
        )
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.capture_payment_intent.return_value = {
            "transfer_id": "tr_lock_success",
            "transfer_amount": 8000,
            "amount_received": 10000,
        }
        mock_stripe.reverse_transfer.return_value = {"reversal": {"id": "trr_lock_success"}}

        with patch("app.services.stripe_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.activate_lock_for_reschedule(booking.id)

        db.refresh(booking)
        lock = _get_lock(db, booking.id)
        assert result.get("locked") is True
        assert booking.payment_detail.payment_status == PaymentStatus.LOCKED.value
        assert lock is not None
        assert lock.locked_amount_cents == 10000

    def test_activate_lock_missing_payment_intent_raises(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Authorized booking without payment_intent_id cannot be locked."""
        future_date = date.today() + timedelta(days=3)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(15, 0), time(16, 0),
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id=None,
            offset_index=63,
        )
        db.commit()

        with pytest.raises(BusinessRuleException, match="No authorized payment available"):
            booking_service_integration.activate_lock_for_reschedule(booking.id)


class TestResolveLockForBookingIntegration:
    """Integration tests for resolve_lock_for_booking covering lines 2031-2165."""

    def test_resolve_lock_booking_not_found(
        self,
        db: Session,
        booking_service_integration: BookingService,
    ):
        """Test resolve lock with non-existent booking."""
        fake_id = generate_ulid()

        with pytest.raises(NotFoundException, match="Locked booking not found"):
            booking_service_integration.resolve_lock_for_booking(
                fake_id, "new_lesson_completed"
            )

    def test_resolve_lock_not_locked(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test resolve lock when booking is not locked."""
        future_date = date.today() + timedelta(days=2)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(10, 0), time(11, 0),
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=20,
        )
        db.commit()

        result = booking_service_integration.resolve_lock_for_booking(
            booking.id, "new_lesson_completed"
        )

        assert result is not None

    def test_resolve_lock_already_settled_skips(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Settled bookings are skipped in lock resolution."""
        past_date = date.today() - timedelta(days=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(10, 0), time(11, 0),
            payment_status=PaymentStatus.SETTLED.value,
            offset_index=69,
        )
        db.commit()

        result = booking_service_integration.resolve_lock_for_booking(
            booking.id, "new_lesson_completed"
        )

        assert result.get("skipped") is True
        assert result.get("reason") == "already_settled"


class TestCreateBookingWithPaymentSetupIntegration:
    """Integration tests for create_booking_with_payment_setup covering lines 668-804."""

    def test_create_booking_with_payment_invalid_duration(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test that invalid duration is rejected."""
        future_date = date.today() + timedelta(days=3)
        seed_day(db, test_instructor_with_availability.id, future_date, [("10:00", "14:00")])

        # Use a duration value that's valid for the schema but not in service's duration_options
        # Most services have specific durations like [30, 60, 90, 120] - use 45 or 180
        invalid_duration = 45  # Valid per schema but likely not in duration_options
        if invalid_duration in instructor_service.duration_options:
            invalid_duration = 180  # Try another value

        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=instructor_service.id,
            booking_date=future_date,
            start_time=time(10, 0),
            selected_duration=invalid_duration,
            end_time=time(10, 45) if invalid_duration == 45 else time(13, 0),
            meeting_location="Test Location",
            location_lat=40.751,
            location_lng=-73.989,
            location_type="neutral_location",
        )

        with pytest.raises(BusinessRuleException, match="Invalid duration"):
            booking_service_integration.create_booking_with_payment_setup(
                test_student, booking_data, selected_duration=invalid_duration
            )

    def test_create_booking_with_payment_success(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test successful booking creation with payment setup."""
        from unittest.mock import MagicMock, patch

        future_date = date.today() + timedelta(days=4)
        seed_day(db, test_instructor_with_availability.id, future_date, [("10:00", "14:00")])

        # Get valid duration from service
        valid_duration = instructor_service.duration_options[0] if instructor_service.duration_options else 60

        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=instructor_service.id,
            booking_date=future_date,
            start_time=time(11, 0),
            selected_duration=valid_duration,
            end_time=time(12, 0),
            meeting_location="Test Location",
            location_lat=40.751,
            location_lng=-73.989,
            location_type="neutral_location",
        )

        # Mock StripeService to avoid actual Stripe calls
        mock_stripe = MagicMock()
        mock_stripe.create_setup_intent.return_value = {"client_secret": "test_secret"}

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.create_booking_with_payment_setup(
                test_student, booking_data, selected_duration=valid_duration
            )

        assert result is not None
        assert result.status == BookingStatus.PENDING
        _reload_payment_detail(db, result)
        assert result.payment_detail.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value


class TestCreateBookingWithRescheduleIntegration:
    """Integration tests for create_booking_with_payment_setup with reschedule linkage."""

    def test_create_booking_with_reschedule_linkage(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test booking creation maintains reschedule chain linkage."""
        from unittest.mock import MagicMock, patch

        # Create the original booking that we'll reschedule from
        original_date = date.today() + timedelta(days=2)
        seed_day(db, test_instructor_with_availability.id, original_date, [("09:00", "17:00")])

        original_booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            original_date, time(9, 0), time(10, 0),
            offset_index=21,
        )
        db.commit()

        # Create new booking with reschedule linkage
        new_date = date.today() + timedelta(days=5)
        seed_day(db, test_instructor_with_availability.id, new_date, [("10:00", "14:00")])

        valid_duration = instructor_service.duration_options[0] if instructor_service.duration_options else 60

        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=instructor_service.id,
            booking_date=new_date,
            start_time=time(10, 0),
            selected_duration=valid_duration,
            end_time=time(11, 0),
            meeting_location="Test Location",
            location_lat=40.751,
            location_lng=-73.989,
            location_type="neutral_location",
        )

        mock_stripe = MagicMock()
        mock_stripe.create_setup_intent.return_value = {"client_secret": "test_secret"}

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.create_booking_with_payment_setup(
                test_student,
                booking_data,
                selected_duration=valid_duration,
                rescheduled_from_booking_id=original_booking.id,
            )

        assert result is not None
        assert result.rescheduled_from_booking_id == original_booking.id

        # Verify original booking was updated
        db.refresh(original_booking)
        original_reschedule = _get_reschedule(db, original_booking.id)
        assert original_reschedule is not None
        assert original_reschedule.rescheduled_to_booking_id == result.id


class TestConfirmBookingPaymentIntegration:
    """Integration tests for confirm_booking_payment."""

    def test_confirm_booking_payment_schedules_auth(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Lessons >24h schedule authorization and confirm booking."""
        start_utc = start_just_over_24h()
        end_utc = start_utc + timedelta(hours=1)

        booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            start_utc.date(),
            start_utc.time(),
            end_utc.time(),
            status=BookingStatus.PENDING,
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            offset_index=49,
        )
        booking.booking_start_utc = start_utc
        booking.booking_end_utc = end_utc
        db.commit()

        result = booking_service_integration.confirm_booking_payment(
            booking_id=booking.id,
            student=test_student,
            payment_method_id="pm_scheduled_auth",
            save_payment_method=False,
        )

        db.refresh(booking)
        _reload_payment_detail(db, booking)
        assert result.status == BookingStatus.CONFIRMED
        assert booking.payment_detail.payment_status == PaymentStatus.SCHEDULED.value
        assert booking.payment_detail.auth_scheduled_for is not None
        assert booking.payment_detail.payment_method_id == "pm_scheduled_auth"

    def test_confirm_booking_payment_gaming_reschedule_immediate_auth(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Gaming reschedule triggers immediate authorization."""
        from unittest.mock import MagicMock, patch

        now = now_trimmed()
        original_start_utc = start_within_24h(base=now, hours=6)
        original_end_utc = original_start_utc + timedelta(hours=1)
        start_utc = start_just_over_24h(base=now)
        end_utc = start_utc + timedelta(hours=1)

        original_booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            original_start_utc.date(),
            original_start_utc.time(),
            original_end_utc.time(),
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=50,
        )
        original_booking.booking_start_utc = original_start_utc
        original_booking.booking_end_utc = original_end_utc

        booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            start_utc.date(),
            start_utc.time(),
            end_utc.time(),
            status=BookingStatus.PENDING,
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            offset_index=51,
        )
        booking.booking_start_utc = start_utc
        booking.booking_end_utc = end_utc
        booking.rescheduled_from_booking_id = original_booking.id
        _upsert_reschedule(db, booking.id, original_lesson_datetime=original_start_utc)
        booking.created_at = now
        db.commit()

        _ensure_stripe_customer(db, test_student)
        _ensure_connected_account(db, test_instructor_with_availability)

        mock_stripe = MagicMock()
        mock_stripe.build_charge_context.return_value = SimpleNamespace(
            student_pay_cents=10000,
            application_fee_cents=1000,
            applied_credit_cents=0,
        )
        mock_stripe.create_or_retry_booking_payment_intent.return_value = SimpleNamespace(
            id="pi_auth_immediate",
            status="requires_capture",
        )

        with patch("app.tasks.payment_tasks.StripeService", return_value=mock_stripe):
            result = booking_service_integration.confirm_booking_payment(
                booking_id=booking.id,
                student=test_student,
                payment_method_id="pm_immediate_auth",
                save_payment_method=False,
            )

        db.refresh(booking)
        _reload_payment_detail(db, booking)
        assert result.status == BookingStatus.CONFIRMED
        assert booking.payment_detail.payment_status == PaymentStatus.AUTHORIZED.value
        assert booking.payment_detail.payment_intent_id == "pi_auth_immediate"


class TestRescheduledBookingWithExistingPaymentIntegration:
    """Integration tests for create_rescheduled_booking_with_existing_payment."""

    def test_create_rescheduled_booking_reuses_payment_intent(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Reschedule reuses payment intent and transfers reserved credits."""
        from app.repositories.payment_repository import PaymentRepository

        original_date = date.today() + timedelta(days=3)
        new_date = date.today() + timedelta(days=6)

        seed_day(db, test_instructor_with_availability.id, original_date, [("09:00", "12:00")])
        seed_day(db, test_instructor_with_availability.id, new_date, [("10:00", "13:00")])

        original_booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            original_date,
            time(9, 0),
            time(10, 0),
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_reschedule_existing",
            offset_index=40,
        )
        original_booking.payment_detail.payment_method_id = "pm_reschedule_existing"
        _upsert_reschedule(db, original_booking.id, late_reschedule_used=True)
        db.commit()

        payment_repo = PaymentRepository(db)
        payment_repo.create_payment_record(
            booking_id=original_booking.id,
            payment_intent_id="pi_reschedule_existing",
            amount=10000,
            application_fee=1000,
            status="requires_capture",
            instructor_payout_cents=8000,
        )
        payment_repo.create_platform_credit(
            user_id=test_student.id,
            amount_cents=2000,
            reason="test_credit",
            source_type="test_credit",
        )
        payment_repo.apply_credits_for_booking(
            user_id=test_student.id,
            booking_id=original_booking.id,
            amount_cents=2000,
        )
        db.commit()

        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=instructor_service.id,
            booking_date=new_date,
            start_time=time(10, 0),
            selected_duration=60,
            meeting_location="Test Location",
            location_lat=40.751,
            location_lng=-73.989,
            location_type="neutral_location",
        )

        result = booking_service_integration.create_rescheduled_booking_with_existing_payment(
            student=test_student,
            booking_data=booking_data,
            selected_duration=60,
            original_booking_id=original_booking.id,
            payment_intent_id="pi_reschedule_existing",
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_method_id="pm_reschedule_existing",
        )

        db.refresh(original_booking)
        _reload_payment_detail(db, result)
        _reload_payment_detail(db, original_booking)
        payment_record = payment_repo.get_payment_by_intent_id("pi_reschedule_existing")
        result_reschedule = _get_reschedule(db, result.id)
        original_reschedule = _get_reschedule(db, original_booking.id)

        assert result.rescheduled_from_booking_id == original_booking.id
        assert result_reschedule is not None
        assert result_reschedule.late_reschedule_used is True
        assert result.payment_detail.payment_intent_id == "pi_reschedule_existing"
        assert result.payment_detail.payment_method_id == "pm_reschedule_existing"
        assert original_reschedule is not None
        assert original_reschedule.rescheduled_to_booking_id == result.id
        assert payment_record is not None
        assert payment_record.booking_id == result.id
        assert result.payment_detail.credits_reserved_cents == 2000
        assert original_booking.payment_detail.credits_reserved_cents == 0

    def test_create_rescheduled_booking_missing_original_raises(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Missing original booking raises NotFoundException."""
        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=instructor_service.id,
            booking_date=date.today() + timedelta(days=4),
            start_time=time(10, 0),
            selected_duration=60,
            meeting_location="Test Location",
            location_lat=40.751,
            location_lng=-73.989,
            location_type="neutral_location",
        )

        with pytest.raises(NotFoundException, match="Original booking not found"):
            booking_service_integration.create_rescheduled_booking_with_existing_payment(
                student=test_student,
                booking_data=booking_data,
                selected_duration=60,
                original_booking_id=generate_ulid(),
                payment_intent_id="pi_missing_original",
                payment_status=PaymentStatus.AUTHORIZED.value,
                payment_method_id="pm_missing_original",
            )

    def test_create_rescheduled_booking_invalid_duration_raises(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Invalid duration is rejected for reschedule."""
        original_date = date.today() + timedelta(days=3)
        seed_day(db, test_instructor_with_availability.id, original_date, [("09:00", "12:00")])

        original_booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            original_date,
            time(9, 0),
            time(10, 0),
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_reschedule_invalid_duration",
            offset_index=67,
        )
        db.commit()

        invalid_duration = 45
        if invalid_duration in instructor_service.duration_options:
            invalid_duration = 180

        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=instructor_service.id,
            booking_date=original_date + timedelta(days=3),
            start_time=time(10, 0),
            selected_duration=invalid_duration,
            meeting_location="Test Location",
            location_lat=40.751,
            location_lng=-73.989,
            location_type="neutral_location",
        )

        with pytest.raises(BusinessRuleException, match="Invalid duration"):
            booking_service_integration.create_rescheduled_booking_with_existing_payment(
                student=test_student,
                booking_data=booking_data,
                selected_duration=invalid_duration,
                original_booking_id=original_booking.id,
                payment_intent_id="pi_reschedule_invalid_duration",
                payment_status=PaymentStatus.AUTHORIZED.value,
                payment_method_id="pm_reschedule_invalid_duration",
            )


class TestRescheduledBookingWithLockedFundsIntegration:
    """Integration tests for create_rescheduled_booking_with_locked_funds."""

    def test_create_rescheduled_booking_sets_locked_flags(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """LOCK reschedule creates a booking with locked funds metadata."""
        original_date = date.today() + timedelta(days=4)
        new_date = date.today() + timedelta(days=7)

        seed_day(db, test_instructor_with_availability.id, original_date, [("09:00", "12:00")])
        seed_day(db, test_instructor_with_availability.id, new_date, [("10:00", "13:00")])

        original_booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            original_date,
            time(9, 0),
            time(10, 0),
            payment_status=PaymentStatus.LOCKED.value,
            offset_index=41,
        )
        db.commit()

        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=instructor_service.id,
            booking_date=new_date,
            start_time=time(10, 0),
            selected_duration=60,
            meeting_location="Test Location",
            location_lat=40.751,
            location_lng=-73.989,
            location_type="neutral_location",
        )

        result = booking_service_integration.create_rescheduled_booking_with_locked_funds(
            student=test_student,
            booking_data=booking_data,
            selected_duration=60,
            original_booking_id=original_booking.id,
        )

        db.refresh(original_booking)
        _reload_payment_detail(db, result)
        original_reschedule = _get_reschedule(db, original_booking.id)
        result_reschedule = _get_reschedule(db, result.id)
        assert result.rescheduled_from_booking_id == original_booking.id
        assert original_reschedule is not None
        assert original_reschedule.rescheduled_to_booking_id == result.id
        assert result.has_locked_funds is True
        assert result.payment_detail.payment_status == PaymentStatus.LOCKED.value
        assert result_reschedule is not None
        assert result_reschedule.late_reschedule_used is True

    def test_create_rescheduled_booking_locked_missing_original_raises(
        self,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Missing original booking raises NotFoundException for LOCK reschedule."""
        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=instructor_service.id,
            booking_date=date.today() + timedelta(days=6),
            start_time=time(10, 0),
            selected_duration=60,
            meeting_location="Test Location",
            location_lat=40.751,
            location_lng=-73.989,
            location_type="neutral_location",
        )

        with pytest.raises(NotFoundException, match="Original booking not found"):
            booking_service_integration.create_rescheduled_booking_with_locked_funds(
                student=test_student,
                booking_data=booking_data,
                selected_duration=60,
                original_booking_id=generate_ulid(),
            )

    def test_create_rescheduled_booking_locked_invalid_duration_raises(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Invalid duration is rejected for LOCK reschedule."""
        original_date = date.today() + timedelta(days=4)
        seed_day(db, test_instructor_with_availability.id, original_date, [("09:00", "12:00")])

        original_booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            original_date,
            time(9, 0),
            time(10, 0),
            payment_status=PaymentStatus.LOCKED.value,
            offset_index=68,
        )
        db.commit()

        invalid_duration = 45
        if invalid_duration in instructor_service.duration_options:
            invalid_duration = 180

        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=instructor_service.id,
            booking_date=original_date + timedelta(days=4),
            start_time=time(10, 0),
            selected_duration=invalid_duration,
            meeting_location="Test Location",
            location_lat=40.751,
            location_lng=-73.989,
            location_type="neutral_location",
        )

        with pytest.raises(BusinessRuleException, match="Invalid duration"):
            booking_service_integration.create_rescheduled_booking_with_locked_funds(
                student=test_student,
                booking_data=booking_data,
                selected_duration=invalid_duration,
                original_booking_id=original_booking.id,
            )

    def test_create_rescheduled_booking_locked_instructor_mismatch_raises(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        test_instructor_2: User,
        instructor_service: Service,
    ):
        """LOCK reschedule rejects instructor changes."""
        original_date = date.today() + timedelta(days=3)
        seed_day(db, test_instructor_with_availability.id, original_date, [("09:00", "12:00")])

        original_booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            original_date,
            time(9, 0),
            time(10, 0),
            payment_status=PaymentStatus.LOCKED.value,
            offset_index=70,
        )
        db.commit()

        booking_data = BookingCreate(
            instructor_id=test_instructor_2.id,
            instructor_service_id=instructor_service.id,
            booking_date=original_date + timedelta(days=4),
            start_time=time(10, 0),
            selected_duration=60,
            meeting_location="Test Location",
            location_lat=40.751,
            location_lng=-73.989,
            location_type="neutral_location",
        )

        with pytest.raises(BusinessRuleException, match="Cannot change instructor"):
            booking_service_integration.create_rescheduled_booking_with_locked_funds(
                student=test_student,
                booking_data=booking_data,
                selected_duration=60,
                original_booking_id=original_booking.id,
            )


class TestPaymentProcessingScenariosIntegration:
    """Integration tests for _execute_stripe_cancellation_operations covering lines 2448-2685."""

    def test_over_24h_regular_cancel_scenario(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test payment release for cancellation >24h before lesson."""
        from unittest.mock import MagicMock, patch

        future_date = date.today() + timedelta(days=5)
        seed_day(db, test_instructor_with_availability.id, future_date, [("10:00", "14:00")])

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(12, 0), time(13, 0),
            payment_intent_id="pi_test_over24h",
            offset_index=22,
        )
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.cancel_payment_intent.return_value = {"status": "canceled"}

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.cancel_booking(
                booking.id, test_student, reason="Plans changed"
            )

        assert result.status == BookingStatus.CANCELLED

    def test_instructor_cancel_scenario(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test instructor cancellation triggers full refund."""
        from unittest.mock import MagicMock, patch

        future_date = date.today() + timedelta(days=3)
        seed_day(db, test_instructor_with_availability.id, future_date, [("14:00", "18:00")])

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(14, 0), time(15, 0),
            payment_intent_id="pi_test_instructor_cancel",
            offset_index=23,
        )
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.refund_payment.return_value = {"refund_id": "re_test", "amount_refunded": 6000}
        mock_stripe.cancel_payment_intent.return_value = {"status": "canceled"}

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.cancel_booking(
                booking.id, test_instructor_with_availability, reason="Emergency"
            )

        assert result.status == BookingStatus.CANCELLED

    def test_between_12_24h_cancel_creates_credit(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test student cancellation between 12-24h triggers credit flow."""
        from unittest.mock import MagicMock, patch

        now = datetime.now(timezone.utc)
        start_utc = now + timedelta(hours=18)
        end_utc = start_utc + timedelta(hours=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            start_utc.date(), start_utc.time(), end_utc.time(),
            payment_intent_id="pi_between_12_24",
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=35,
        )
        booking.booking_start_utc = start_utc
        booking.booking_end_utc = end_utc
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.capture_payment_intent.return_value = {
            "transfer_id": "tr_capture_12_24",
            "amount_received": 10000,
            "transfer_amount": 8000,
        }
        mock_stripe.reverse_transfer.return_value = {"reversal": {"id": "trr_12_24"}}

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.cancel_booking(
                booking.id, test_student, reason="Late cancel"
            )

        db.refresh(booking)
        transfer = _get_transfer(db, booking.id)
        assert result.status == BookingStatus.CANCELLED
        assert booking.payment_detail.payment_status == PaymentStatus.SETTLED.value
        assert booking.payment_detail.settlement_outcome == "student_cancel_12_24_full_credit"
        assert transfer is not None
        assert transfer.transfer_reversal_id == "trr_12_24"

    def test_under_12h_cancel_creates_payout_and_credit(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test student cancellation under 12h triggers split payout and credit."""
        from unittest.mock import MagicMock, patch

        now = datetime.now(timezone.utc)
        start_utc = now + timedelta(hours=6)
        end_utc = start_utc + timedelta(hours=1)
        if end_utc.date() != start_utc.date():
            start_utc = start_utc - timedelta(hours=1)
            end_utc = start_utc + timedelta(hours=1)

        _ensure_connected_account(db, test_instructor_with_availability)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            start_utc.date(), start_utc.time(), end_utc.time(),
            payment_intent_id="pi_under_12",
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=36,
        )
        booking.booking_start_utc = start_utc
        booking.booking_end_utc = end_utc
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.capture_payment_intent.return_value = {
            "transfer_id": "tr_capture_under_12",
            "transfer_amount": 8000,
            "amount_received": 10000,
        }
        mock_stripe.reverse_transfer.return_value = {"reversal": {"id": "trr_under_12"}}
        mock_stripe.create_manual_transfer.return_value = {"transfer_id": "tr_payout_under_12"}

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.cancel_booking(
                booking.id, test_student, reason="Emergency"
            )

        db.refresh(booking)
        transfer = _get_transfer(db, booking.id)
        assert result.status == BookingStatus.CANCELLED
        assert booking.payment_detail.payment_status == PaymentStatus.SETTLED.value
        assert booking.payment_detail.settlement_outcome == "student_cancel_lt12_split_50_50"
        assert transfer is not None
        assert transfer.payout_transfer_id == "tr_payout_under_12"

    def test_over_24h_gaming_cancel_reverse_failure_marks_manual_review(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Gaming reschedule cancellation with reversal failure marks manual review."""
        from unittest.mock import MagicMock, patch

        now = datetime.now(timezone.utc)
        original_start_utc = now + timedelta(hours=6)
        original_end_utc = original_start_utc + timedelta(hours=1)
        start_utc = now + timedelta(hours=36)
        end_utc = start_utc + timedelta(hours=1)

        original_booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            original_start_utc.date(),
            original_start_utc.time(),
            original_end_utc.time(),
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=48,
        )
        original_booking.booking_start_utc = original_start_utc
        original_booking.booking_end_utc = original_end_utc

        booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            start_utc.date(),
            start_utc.time(),
            end_utc.time(),
            payment_intent_id="pi_gaming_cancel",
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=42,
        )
        booking.booking_start_utc = start_utc
        booking.booking_end_utc = end_utc
        booking.rescheduled_from_booking_id = original_booking.id
        _upsert_reschedule(db, booking.id, original_lesson_datetime=original_start_utc)
        booking.created_at = now
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.capture_payment_intent.return_value = {
            "transfer_id": "tr_gaming",
            "amount_received": 10000,
            "transfer_amount": 8000,
        }
        mock_stripe.reverse_transfer.side_effect = Exception("reversal failed")

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.cancel_booking(
                booking.id, test_student, reason="Gaming reschedule cancel"
            )

        db.refresh(booking)
        transfer = _get_transfer(db, booking.id)
        assert result.status == BookingStatus.CANCELLED
        assert booking.payment_detail.payment_status == PaymentStatus.MANUAL_REVIEW.value
        assert transfer is not None
        assert transfer.transfer_reversal_failed is True

    def test_cancel_pending_payment_sets_settled(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Pending-payment cancellation settles without Stripe calls."""
        future_date = date.today() + timedelta(days=2)
        booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            future_date,
            time(9, 0),
            time(10, 0),
            status=BookingStatus.PENDING,
            payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            offset_index=43,
        )
        db.commit()

        result = booking_service_integration.cancel_booking(
            booking.id, test_student, reason="Payment not added"
        )

        db.refresh(booking)
        assert result.status == BookingStatus.CANCELLED
        assert booking.payment_detail.payment_status == PaymentStatus.SETTLED.value
        assert booking.payment_detail.settlement_outcome == "student_cancel_gt24_no_charge"

    def test_cancel_under_12h_no_payment_intent_marks_manual_review(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """<12h cancellation without payment intent triggers manual review."""
        now = datetime.now(timezone.utc)
        start_utc = now + timedelta(hours=6)
        end_utc = start_utc + timedelta(hours=1)

        booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            start_utc.date(),
            start_utc.time(),
            end_utc.time(),
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=44,
        )
        booking.booking_start_utc = start_utc
        booking.booking_end_utc = end_utc
        booking.payment_detail.payment_intent_id = None
        db.commit()

        result = booking_service_integration.cancel_booking(
            booking.id, test_student, reason="Last-minute cancel"
        )

        db.refresh(booking)
        assert result.status == BookingStatus.CANCELLED
        assert booking.payment_detail.payment_status == PaymentStatus.MANUAL_REVIEW.value
        assert booking.payment_detail.auth_last_error == "missing_payment_intent"

    def test_instructor_cancel_refund_success_on_captured_payment(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Instructor cancellation refunds when payment already captured."""
        from unittest.mock import MagicMock, patch

        future_date = date.today() + timedelta(days=3)
        seed_day(db, test_instructor_with_availability.id, future_date, [("10:00", "14:00")])

        booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            future_date,
            time(10, 0),
            time(11, 0),
            payment_intent_id="pi_refund_success",
            payment_status=PaymentStatus.SETTLED.value,
            offset_index=45,
        )
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.refund_payment.return_value = {
            "refund_id": "re_refund_success",
            "amount_refunded": 4500,
        }

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.cancel_booking(
                booking.id, test_instructor_with_availability, reason="Instructor cancel"
            )

        db.refresh(booking)
        transfer = _get_transfer(db, booking.id)
        assert result.status == BookingStatus.CANCELLED
        assert transfer is not None
        assert transfer.refund_id == "re_refund_success"
        assert booking.payment_detail.payment_status == PaymentStatus.SETTLED.value
        assert booking.payment_detail.settlement_outcome == "instructor_cancel_full_refund"

    def test_over_24h_gaming_cancel_success_sets_credit(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Gaming reschedule cancellation issues credit on success."""
        from unittest.mock import MagicMock, patch

        now = datetime.now(timezone.utc)
        original_start_utc = now + timedelta(hours=8)
        original_end_utc = original_start_utc + timedelta(hours=1)
        start_utc = now + timedelta(hours=36)
        end_utc = start_utc + timedelta(hours=1)

        original_booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            original_start_utc.date(),
            original_start_utc.time(),
            original_end_utc.time(),
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=53,
        )
        original_booking.booking_start_utc = original_start_utc
        original_booking.booking_end_utc = original_end_utc

        booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            start_utc.date(),
            start_utc.time(),
            end_utc.time(),
            payment_intent_id="pi_gaming_success",
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=54,
        )
        booking.booking_start_utc = start_utc
        booking.booking_end_utc = end_utc
        booking.rescheduled_from_booking_id = original_booking.id
        _upsert_reschedule(db, booking.id, original_lesson_datetime=original_start_utc)
        booking.created_at = now
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.capture_payment_intent.return_value = {
            "transfer_id": "tr_gaming_success",
            "amount_received": 10000,
            "transfer_amount": 8000,
        }
        mock_stripe.reverse_transfer.return_value = {"reversal": {"id": "trr_gaming_success"}}

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.cancel_booking(
                booking.id, test_student, reason="Gaming reschedule cancel"
            )

        db.refresh(booking)
        transfer = _get_transfer(db, booking.id)
        assert result.status == BookingStatus.CANCELLED
        assert booking.payment_detail.payment_status == PaymentStatus.SETTLED.value
        assert booking.payment_detail.settlement_outcome == "student_cancel_12_24_full_credit"
        assert transfer is not None
        assert transfer.transfer_reversal_id == "trr_gaming_success"

    def test_over_24h_regular_cancel_with_cancel_error_marks_manual_review(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Cancel PI failure triggers manual review for >24h cancellation."""
        from unittest.mock import MagicMock, patch

        future_date = date.today() + timedelta(days=5)
        booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            future_date,
            time(12, 0),
            time(13, 0),
            payment_intent_id="pi_cancel_fail",
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=55,
        )
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.cancel_payment_intent.side_effect = Exception("cancel failed")

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.cancel_booking(
                booking.id, test_student, reason="Cancel failure"
            )

        db.refresh(booking)
        assert result.status == BookingStatus.CANCELLED
        assert booking.payment_detail.payment_status == PaymentStatus.MANUAL_REVIEW.value
        assert booking.payment_detail.auth_last_error == "cancel failed"

    def test_instructor_cancel_refund_failed_marks_manual_review(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Refund failure on instructor cancellation triggers manual review."""
        from unittest.mock import MagicMock, patch

        future_date = date.today() + timedelta(days=4)
        booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            future_date,
            time(10, 0),
            time(11, 0),
            payment_intent_id="pi_refund_fail",
            payment_status=PaymentStatus.SETTLED.value,
            offset_index=56,
        )
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.refund_payment.side_effect = Exception("refund failed")

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.cancel_booking(
                booking.id, test_instructor_with_availability, reason="Refund fail"
            )

        db.refresh(booking)
        transfer = _get_transfer(db, booking.id)
        assert result.status == BookingStatus.CANCELLED
        assert booking.payment_detail.payment_status == PaymentStatus.MANUAL_REVIEW.value
        assert transfer is not None
        assert transfer.refund_failed_at is not None
        assert transfer.refund_error == "refund failed"

    def test_between_12_24h_cancel_reverse_failure_marks_manual_review(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Late cancel reversal failure triggers manual review."""
        from unittest.mock import MagicMock, patch

        now = datetime.now(timezone.utc)
        start_utc = now + timedelta(hours=18)
        end_utc = start_utc + timedelta(hours=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            start_utc.date(), start_utc.time(), end_utc.time(),
            payment_intent_id="pi_late_reverse_fail",
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=61,
        )
        booking.booking_start_utc = start_utc
        booking.booking_end_utc = end_utc
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.capture_payment_intent.return_value = {
            "transfer_id": "tr_late_reverse_fail",
            "transfer_amount": 8000,
            "amount_received": 10000,
        }
        mock_stripe.reverse_transfer.side_effect = Exception("reverse failed")

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.cancel_booking(
                booking.id, test_student, reason="Late cancel"
            )

        db.refresh(booking)
        transfer = _get_transfer(db, booking.id)
        assert result.status == BookingStatus.CANCELLED
        assert booking.payment_detail.payment_status == PaymentStatus.MANUAL_REVIEW.value
        assert transfer is not None
        assert transfer.transfer_reversal_failed is True

    def test_under_12h_cancel_payout_failure_marks_manual_review(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Missing instructor account yields payout failure and manual review."""
        from unittest.mock import MagicMock, patch

        now = datetime.now(timezone.utc)
        start_utc = now + timedelta(hours=6)
        end_utc = start_utc + timedelta(hours=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            start_utc.date(), start_utc.time(), end_utc.time(),
            payment_intent_id="pi_under12_payout_fail",
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=62,
        )
        booking.booking_start_utc = start_utc
        booking.booking_end_utc = end_utc
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.capture_payment_intent.return_value = {
            "transfer_id": "tr_under12",
            "transfer_amount": 8000,
            "amount_received": 10000,
        }
        mock_stripe.reverse_transfer.return_value = {"reversal": {"id": "trr_under12"}}

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.cancel_booking(
                booking.id, test_student, reason="Last-minute cancel"
            )

        db.refresh(booking)
        transfer = _get_transfer(db, booking.id)
        assert result.status == BookingStatus.CANCELLED
        assert booking.payment_detail.payment_status == PaymentStatus.MANUAL_REVIEW.value
        assert transfer is not None
        assert transfer.payout_transfer_failed_at is not None
        assert transfer.payout_transfer_error == "missing_instructor_account"

    def test_over_24h_gaming_capture_failure_marks_capture_failed(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Gaming reschedule capture failure records auth error."""
        from unittest.mock import MagicMock, patch

        now = datetime.now(timezone.utc)
        original_start_utc = now + timedelta(hours=6)
        original_end_utc = original_start_utc + timedelta(hours=1)
        start_utc = now + timedelta(hours=36)
        end_utc = start_utc + timedelta(hours=1)

        original_booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            original_start_utc.date(),
            original_start_utc.time(),
            original_end_utc.time(),
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=64,
        )
        original_booking.booking_start_utc = original_start_utc
        original_booking.booking_end_utc = original_end_utc

        booking = create_test_booking(
            db,
            test_student,
            test_instructor_with_availability,
            instructor_service,
            start_utc.date(),
            start_utc.time(),
            end_utc.time(),
            payment_intent_id="pi_gaming_capture_fail",
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=65,
        )
        booking.booking_start_utc = start_utc
        booking.booking_end_utc = end_utc
        booking.rescheduled_from_booking_id = original_booking.id
        _upsert_reschedule(db, booking.id, original_lesson_datetime=original_start_utc)
        booking.created_at = now
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.capture_payment_intent.side_effect = Exception("capture failed")

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.cancel_booking(
                booking.id, test_student, reason="Gaming reschedule cancel"
            )

        db.refresh(booking)
        assert result.status == BookingStatus.CANCELLED
        assert booking.payment_detail.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
        assert booking.payment_detail.capture_failed_at is not None
        assert booking.payment_detail.auth_last_error == "capture failed"

    def test_under_12h_cancel_reverse_failure_manual_review(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Reverse transfer failure on last-minute cancel triggers manual review."""
        from unittest.mock import MagicMock, patch

        now = datetime.now(timezone.utc)
        start_utc = now + timedelta(hours=6)
        end_utc = start_utc + timedelta(hours=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            start_utc.date(), start_utc.time(), end_utc.time(),
            payment_intent_id="pi_under12_reverse_fail",
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=66,
        )
        booking.booking_start_utc = start_utc
        booking.booking_end_utc = end_utc
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.capture_payment_intent.return_value = {
            "transfer_id": "tr_under12_reverse_fail",
            "transfer_amount": 8000,
            "amount_received": 10000,
        }
        mock_stripe.reverse_transfer.side_effect = Exception("reverse failed")

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.cancel_booking(
                booking.id, test_student, reason="Last-minute cancel"
            )

        db.refresh(booking)
        transfer = _get_transfer(db, booking.id)
        assert result.status == BookingStatus.CANCELLED
        assert booking.payment_detail.payment_status == PaymentStatus.MANUAL_REVIEW.value
        assert transfer is not None
        assert transfer.transfer_reversal_failed is True


class TestResolveLockResolutionsIntegration:
    """Integration tests for resolve_lock_for_booking resolution paths covering lines 2185-2297."""

    def test_resolve_lock_new_lesson_completed(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test lock resolution when new lesson is completed."""
        from unittest.mock import MagicMock, patch

        past_date = date.today() - timedelta(days=2)

        # Create locked booking
        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(10, 0), time(11, 0),
            payment_status=PaymentStatus.LOCKED.value,
            offset_index=24,
        )
        _upsert_lock(db, booking.id, locked_amount_cents=6000)
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.create_manual_transfer.return_value = {"transfer_id": "tr_test"}

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.resolve_lock_for_booking(
                booking.id, "new_lesson_completed"
            )

        # Resolution should succeed
        assert result is not None
        if isinstance(result, dict):
            assert result.get("success") == True or "resolution" in result

    def test_resolve_lock_new_lesson_completed_with_account(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Successful payout when instructor Stripe account is available."""
        from unittest.mock import MagicMock, patch

        from app.repositories.payment_repository import PaymentRepository

        past_date = date.today() - timedelta(days=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(10, 0), time(11, 0),
            payment_status=PaymentStatus.LOCKED.value,
            payment_intent_id="pi_lock_paid",
            offset_index=71,
        )
        _upsert_lock(db, booking.id, locked_amount_cents=6000)
        db.commit()

        _ensure_connected_account(db, test_instructor_with_availability)

        payment_repo = PaymentRepository(db)
        payment_repo.create_payment_record(
            booking_id=booking.id,
            payment_intent_id="pi_lock_paid",
            amount=6000,
            application_fee=500,
            status="requires_capture",
            instructor_payout_cents=5000,
        )
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.create_manual_transfer.return_value = {"transfer_id": "tr_lock_paid"}

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.resolve_lock_for_booking(
                booking.id, "new_lesson_completed"
            )

        db.refresh(booking)
        transfer = _get_transfer(db, booking.id)
        assert result.get("success") is True
        assert booking.payment_detail.payment_status == PaymentStatus.SETTLED.value
        assert transfer is not None
        assert transfer.payout_transfer_id == "tr_lock_paid"

    def test_resolve_lock_new_lesson_cancelled_ge12(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test lock resolution when new lesson is cancelled >=12h before."""
        from unittest.mock import MagicMock, patch

        past_date = date.today() - timedelta(days=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(10, 0), time(11, 0),
            payment_status=PaymentStatus.LOCKED.value,
            offset_index=25,
        )
        _upsert_lock(db, booking.id, locked_amount_cents=6000)
        db.commit()

        mock_stripe = MagicMock()

        from app.models.payment import PlatformCredit
        from app.repositories.payment_repository import PaymentRepository

        db.query(PlatformCredit).filter(
            PlatformCredit.source_booking_id == booking.id
        ).delete()
        db.commit()

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.resolve_lock_for_booking(
                booking.id, "new_lesson_cancelled_ge12"
            )

        payment_repo = PaymentRepository(db)
        credits = payment_repo.get_credits_issued_for_source(booking.id)

        assert result is not None
        if isinstance(result, dict):
            assert result.get("success") == True or "resolution" in result
        assert credits

    def test_resolve_lock_new_lesson_cancelled_lt12(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test lock resolution when new lesson is cancelled <12h before (50/50 split)."""
        from unittest.mock import MagicMock, patch

        past_date = date.today() - timedelta(days=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(10, 0), time(11, 0),
            payment_status=PaymentStatus.LOCKED.value,
            offset_index=26,
        )
        _upsert_lock(db, booking.id, locked_amount_cents=6000)
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.create_manual_transfer.return_value = {"transfer_id": "tr_test_lt12"}

        from app.models.payment import PlatformCredit
        from app.repositories.payment_repository import PaymentRepository

        db.query(PlatformCredit).filter(
            PlatformCredit.source_booking_id == booking.id
        ).delete()
        db.commit()

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.resolve_lock_for_booking(
                booking.id, "new_lesson_cancelled_lt12"
            )

        payment_repo = PaymentRepository(db)
        credits = payment_repo.get_credits_issued_for_source(booking.id)

        assert result is not None
        assert credits

    def test_resolve_lock_instructor_cancelled(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test lock resolution when instructor cancels (full refund)."""
        from unittest.mock import MagicMock, patch

        past_date = date.today() - timedelta(days=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(10, 0), time(11, 0),
            payment_status=PaymentStatus.LOCKED.value,
            payment_intent_id="pi_test_locked",
            offset_index=27,
        )
        _upsert_lock(db, booking.id, locked_amount_cents=6000)
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.refund_payment.return_value = {"refund_id": "re_test", "amount_refunded": 6000}

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.resolve_lock_for_booking(
                booking.id, "instructor_cancelled"
            )

        assert result is not None

    def test_resolve_lock_instructor_cancelled_missing_payment_intent(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Missing payment intent triggers manual review on instructor cancel."""
        past_date = date.today() - timedelta(days=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(10, 0), time(11, 0),
            payment_status=PaymentStatus.LOCKED.value,
            payment_intent_id=None,
            offset_index=72,
        )
        _upsert_lock(db, booking.id, locked_amount_cents=6000)
        db.commit()

        result = booking_service_integration.resolve_lock_for_booking(
            booking.id, "instructor_cancelled"
        )

        db.refresh(booking)
        assert result.get("success") is True
        assert booking.payment_detail.payment_status == PaymentStatus.MANUAL_REVIEW.value


class TestBuildCancellationContextIntegration:
    """Integration tests for _build_cancellation_context covering lines 2299-2380."""

    def test_build_context_for_confirmed_booking(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test cancellation context is built correctly."""
        future_date = date.today() + timedelta(days=3)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(10, 0), time(11, 0),
            payment_intent_id="pi_context_test",
            offset_index=28,
        )
        db.commit()

        ctx = booking_service_integration._build_cancellation_context(booking, test_student)

        assert ctx is not None
        assert "hours_until" in ctx  # The actual key name
        assert ctx["booking_id"] == booking.id
        assert ctx["cancelled_by_role"] == "student"
        assert "scenario" in ctx


class TestValidateRescheduleAllowedIntegration:
    """Integration tests for validate_reschedule_allowed covering line 5449."""

    def test_validate_reschedule_allowed_for_confirmed_booking(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test reschedule validation passes for confirmed future booking."""
        future_date = date.today() + timedelta(days=5)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(10, 0), time(11, 0),
            status=BookingStatus.CONFIRMED,
            offset_index=29,
        )
        db.commit()

        # Should not raise - confirmed bookings can be rescheduled
        booking_service_integration.validate_reschedule_allowed(booking)

    def test_validate_reschedule_blocked_for_locked_booking(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test reschedule validation fails for locked booking."""
        future_date = date.today() + timedelta(days=3)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(10, 0), time(11, 0),
            payment_status=PaymentStatus.LOCKED.value,
            offset_index=30,
        )
        db.commit()

        with pytest.raises(BusinessRuleException, match="locked funds"):
            booking_service_integration.validate_reschedule_allowed(booking)

    def test_validate_reschedule_blocked_for_late_reschedule_used(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test reschedule validation fails when late reschedule already used."""
        future_date = date.today() + timedelta(days=3)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(10, 0), time(11, 0),
            offset_index=31,
        )
        _upsert_reschedule(db, booking.id, late_reschedule_used=True)
        db.commit()

        with pytest.raises(BusinessRuleException, match="late reschedule"):
            booking_service_integration.validate_reschedule_allowed(booking)


class TestReschedulePaymentMethodIntegration:
    """Integration tests for validate_reschedule_payment_method."""

    def test_validate_reschedule_payment_method_missing(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
    ):
        """No default payment method returns False/None."""
        db.query(PaymentMethod).filter(PaymentMethod.user_id == test_student.id).delete()
        db.commit()

        has_method, method_id = booking_service_integration.validate_reschedule_payment_method(
            test_student.id
        )

        assert has_method is False
        assert method_id is None

    def test_validate_reschedule_payment_method_returns_default(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
    ):
        """Default payment method returns True with ID."""
        method_id = _ensure_default_payment_method(db, test_student)

        has_method, returned_id = booking_service_integration.validate_reschedule_payment_method(
            test_student.id
        )

        assert has_method is True
        assert returned_id == method_id


class TestAbortPendingBookingIntegration:
    """Integration tests for abort_pending_booking."""

    def test_abort_pending_booking_missing(self, booking_service_integration: BookingService):
        """Missing bookings return False."""
        assert booking_service_integration.abort_pending_booking(generate_ulid()) is False

    def test_abort_pending_booking_non_pending(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Non-pending bookings should not be deleted."""
        future_date = date.today() + timedelta(days=4)
        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(9, 0), time(10, 0),
            status=BookingStatus.CONFIRMED,
            offset_index=32,
        )
        db.commit()

        assert booking_service_integration.abort_pending_booking(booking.id) is False
        assert db.query(Booking).filter(Booking.id == booking.id).first() is not None

    def test_abort_pending_booking_success(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Pending bookings are deleted."""
        future_date = date.today() + timedelta(days=4)
        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(9, 0), time(10, 0),
            status=BookingStatus.PENDING,
            offset_index=33,
        )
        db.commit()

        assert booking_service_integration.abort_pending_booking(booking.id) is True
        assert db.query(Booking).filter(Booking.id == booking.id).first() is None


class TestFinalizeCompletionIntegration:
    """Integration tests for _finalize_completion covering payment capture paths."""

    def test_complete_booking_with_payment_capture(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test booking completion triggers payment capture."""
        from unittest.mock import MagicMock, patch

        past_date = date.today() - timedelta(days=1)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(10, 0), time(11, 0),
            payment_intent_id="pi_complete_test",
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=30,
        )
        db.commit()

        mock_stripe = MagicMock()
        mock_stripe.capture_payment_intent.return_value = {
            "transfer_id": "tr_test",
            "amount_received": 6000,
            "transfer_amount": 5000,
        }

        with patch("app.services.booking_service.StripeService", return_value=mock_stripe):
            result = booking_service_integration.complete_booking(
                booking.id, test_instructor_with_availability
            )

        assert result.status == BookingStatus.COMPLETED


class TestGetBookingStartUtcIntegration:
    """Integration tests for _get_booking_start_utc helper."""

    def test_get_booking_start_utc_returns_datetime(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Test _get_booking_start_utc returns proper UTC datetime."""
        future_date = date.today() + timedelta(days=2)

        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(10, 0), time(11, 0),
            offset_index=31,
        )
        db.commit()

        result = booking_service_integration._get_booking_start_utc(booking)

        assert result is not None
        assert isinstance(result, datetime)
        # Should be timezone-aware
        assert result.tzinfo is not None or result.tzinfo == timezone.utc


class TestInstructorCompletionIntegration:
    """Integration tests for instructor completion and disputes."""

    def test_instructor_mark_complete_success(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Instructor can mark a past lesson as completed."""
        past_date = date.today() - timedelta(days=1)
        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(9, 0), time(10, 0),
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=37,
        )
        booking.booking_start_utc = datetime.now(timezone.utc) - timedelta(hours=2)
        booking.booking_end_utc = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()

        result = booking_service_integration.instructor_mark_complete(
            booking_id=booking.id,
            instructor=test_instructor_with_availability,
            notes="Completed lesson",
        )

        assert result.status == BookingStatus.COMPLETED
        assert result.completed_at is not None

    def test_instructor_mark_complete_before_lesson_ends(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Cannot mark completion before lesson end."""
        future_date = date.today() + timedelta(days=1)
        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            future_date, time(9, 0), time(10, 0),
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=38,
        )
        booking.booking_start_utc = datetime.now(timezone.utc) + timedelta(hours=2)
        booking.booking_end_utc = datetime.now(timezone.utc) + timedelta(hours=3)
        db.commit()

        with pytest.raises(BusinessRuleException, match="before it ends"):
            booking_service_integration.instructor_mark_complete(
                booking_id=booking.id,
                instructor=test_instructor_with_availability,
            )

    def test_instructor_dispute_completion_sets_manual_review(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Instructor dispute sets payment status to manual review."""
        past_date = date.today() - timedelta(days=1)
        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(11, 0), time(12, 0),
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=39,
        )
        db.commit()

        result = booking_service_integration.instructor_dispute_completion(
            booking_id=booking.id,
            instructor=test_instructor_with_availability,
            reason="Disputed completion",
        )

        assert result.payment_detail.payment_status == PaymentStatus.MANUAL_REVIEW.value

    def test_instructor_mark_complete_not_found(
        self,
        booking_service_integration: BookingService,
        test_instructor_with_availability: User,
    ):
        """Missing booking raises NotFoundException."""
        with pytest.raises(NotFoundException, match="Booking not found"):
            booking_service_integration.instructor_mark_complete(
                booking_id=generate_ulid(),
                instructor=test_instructor_with_availability,
            )

    def test_instructor_mark_complete_wrong_instructor(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        test_instructor_2: User,
        instructor_service: Service,
    ):
        """Only the assigned instructor can mark complete."""
        past_date = date.today() - timedelta(days=1)
        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(8, 0), time(9, 0),
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=46,
        )
        booking.booking_start_utc = datetime.now(timezone.utc) - timedelta(hours=3)
        booking.booking_end_utc = datetime.now(timezone.utc) - timedelta(hours=2)
        db.commit()

        with pytest.raises(NotFoundException):
            booking_service_integration.instructor_mark_complete(
                booking_id=booking.id,
                instructor=test_instructor_2,
            )

    def test_instructor_mark_complete_rejects_non_confirmed(
        self,
        db: Session,
        booking_service_integration: BookingService,
        test_student: User,
        test_instructor_with_availability: User,
        instructor_service: Service,
    ):
        """Non-confirmed bookings cannot be marked complete."""
        past_date = date.today() - timedelta(days=2)
        booking = create_test_booking(
            db, test_student, test_instructor_with_availability, instructor_service,
            past_date, time(8, 0), time(9, 0),
            status=BookingStatus.CANCELLED,
            payment_status=PaymentStatus.AUTHORIZED.value,
            offset_index=47,
        )
        booking.booking_start_utc = datetime.now(timezone.utc) - timedelta(hours=4)
        booking.booking_end_utc = datetime.now(timezone.utc) - timedelta(hours=3)
        db.commit()

        with pytest.raises(BusinessRuleException, match="Cannot mark booking as complete"):
            booking_service_integration.instructor_mark_complete(
                booking_id=booking.id,
                instructor=test_instructor_with_availability,
            )
