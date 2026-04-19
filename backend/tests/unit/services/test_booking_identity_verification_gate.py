"""H7: booking creation must reject instructors without Stripe Identity verification.

KYC bypass is a liability risk: without this gate an instructor could receive
bookings (and payouts) before Stripe verifies their identity.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.enums import RoleName
from app.core.exceptions import InstructorNotVerifiedError


def _make_creation_service() -> object:
    """Build a `BookingCreationMixin` instance with stub repositories."""
    from app.services.booking.creation_service import BookingCreationMixin

    service = BookingCreationMixin.__new__(BookingCreationMixin)
    service.db = MagicMock()
    service.logger = MagicMock()
    service.conflict_checker_repository = MagicMock()
    return service


def _make_student() -> SimpleNamespace:
    return SimpleNamespace(
        id="student_1",
        roles=[SimpleNamespace(name=RoleName.STUDENT)],
        account_locked=False,
        account_restricted=False,
        credit_balance_frozen=False,
        credit_balance_cents=0,
    )


def _make_booking_data() -> SimpleNamespace:
    return SimpleNamespace(
        instructor_id="instructor_1",
        instructor_service_id="service_1",
    )


def _make_service_record() -> SimpleNamespace:
    return SimpleNamespace(id="service_1", instructor_profile_id="profile_1")


def _make_profile(identity_verified_at: datetime | None) -> SimpleNamespace:
    return SimpleNamespace(
        id="profile_1",
        instructor_id="instructor_1",
        identity_verified_at=identity_verified_at,
        bgc_status="passed",
    )


@pytest.mark.unit
class TestIdentityVerificationGate:
    def test_unverified_instructor_rejects_booking(self):
        creation_service = _make_creation_service()
        creation_service.conflict_checker_repository.get_active_service.return_value = (
            _make_service_record()
        )
        creation_service.conflict_checker_repository.get_instructor_profile.return_value = (
            _make_profile(identity_verified_at=None)
        )

        user_repo = MagicMock()
        user_repo.get_by_id.return_value = SimpleNamespace(account_status="active")

        with patch(
            "app.services.booking.creation_service._booking_service_module"
        ) as mod_mock:
            mod_mock.return_value.must_be_verified_for_public.return_value = False
            mod_mock.return_value.RepositoryFactory.create_base_repository.return_value = (
                user_repo
            )

            with pytest.raises(InstructorNotVerifiedError):
                creation_service._validate_booking_prerequisites(
                    _make_student(), _make_booking_data()
                )

    def test_verified_instructor_passes_validation(self):
        creation_service = _make_creation_service()
        creation_service.conflict_checker_repository.get_active_service.return_value = (
            _make_service_record()
        )
        profile = _make_profile(identity_verified_at=datetime.now(timezone.utc))
        creation_service.conflict_checker_repository.get_instructor_profile.return_value = (
            profile
        )

        user_repo = MagicMock()
        user_repo.get_by_id.return_value = SimpleNamespace(account_status="active")

        with patch(
            "app.services.booking.creation_service._booking_service_module"
        ) as mod_mock:
            mod_mock.return_value.must_be_verified_for_public.return_value = False
            mod_mock.return_value.RepositoryFactory.create_base_repository.return_value = (
                user_repo
            )

            service_rec, profile_rec = creation_service._validate_booking_prerequisites(
                _make_student(), _make_booking_data()
            )

        assert profile_rec is profile
