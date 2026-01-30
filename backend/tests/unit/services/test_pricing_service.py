from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.constants.pricing_defaults import PRICING_DEFAULTS
from app.core.exceptions import BusinessRuleException, NotFoundException, ValidationException
from app.models.booking import BookingStatus
from app.models.service_catalog import InstructorService
from app.repositories.factory import RepositoryFactory
from app.services.config_service import DEFAULT_PRICING_CONFIG
from app.services.pricing_service import PricingService


def _make_payload(**overrides):
    data = {
        "instructor_id": "instructor_1",
        "instructor_service_id": "service_1",
        "booking_date": "2024-01-10",
        "start_time": "09:00",
        "selected_duration": 60,
        "location_type": "online",
        "meeting_location": None,
        "applied_credit_cents": 0,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _make_service(**overrides):
    data = {
        "hourly_rate": Decimal("80.00"),
        "instructor_profile_id": "profile_1",
        "service_catalog_id": "catalog_1",
        "offers_online": True,
        "offers_travel": False,
        "offers_at_location": False,
    }
    data.update(overrides)
    return InstructorService(**data)


@pytest.fixture
def db():
    session = Mock()
    session.commit = Mock()
    session.rollback = Mock()
    return session


@pytest.fixture
def booking_repo():
    return Mock()


@pytest.fixture
def conflict_repo():
    return Mock()


@pytest.fixture
def instructor_profile_repo():
    return Mock()


@pytest.fixture
def pricing_config():
    return deepcopy(DEFAULT_PRICING_CONFIG)


@pytest.fixture
def pricing_service(db, booking_repo, conflict_repo, instructor_profile_repo, pricing_config, monkeypatch):
    monkeypatch.setattr(
        RepositoryFactory, "create_booking_repository", Mock(return_value=booking_repo)
    )
    monkeypatch.setattr(
        RepositoryFactory, "create_conflict_checker_repository", Mock(return_value=conflict_repo)
    )
    monkeypatch.setattr(
        RepositoryFactory, "create_instructor_profile_repository", Mock(return_value=instructor_profile_repo)
    )
    service = PricingService(db)
    service.config_service = Mock()
    service.config_service.get_pricing_config.return_value = (pricing_config, None)
    return service


class TestPricingService:
    class TestComputeBookingPricing:
        def test_compute_booking_pricing_rejects_negative_applied_credit(self, pricing_service):
            with pytest.raises(ValidationException) as exc:
                pricing_service.compute_booking_pricing("booking_1", applied_credit_cents=-1)

            assert exc.value.code == "NEGATIVE_CREDIT"
            assert "non-negative" in exc.value.message

    class TestComputeQuotePricing:
        def test_compute_quote_pricing_rejects_negative_applied_credit(self, pricing_service):
            payload = _make_payload(applied_credit_cents=-10)

            with pytest.raises(ValidationException) as exc:
                pricing_service.compute_quote_pricing(payload, student_id="student_1")

            assert exc.value.code == "NEGATIVE_CREDIT"

        def test_compute_quote_pricing_raises_when_service_missing(
            self, pricing_service, conflict_repo
        ):
            conflict_repo.get_active_service.return_value = None
            payload = _make_payload(instructor_service_id="missing")

            with pytest.raises(NotFoundException) as exc:
                pricing_service.compute_quote_pricing(payload, student_id="student_1")

            assert exc.value.code == "INSTRUCTOR_SERVICE_NOT_FOUND"

        def test_compute_quote_pricing_raises_when_profile_missing(
            self, pricing_service, conflict_repo, instructor_profile_repo
        ):
            conflict_repo.get_active_service.return_value = _make_service()
            instructor_profile_repo.get_by_user_id.return_value = None
            payload = _make_payload()

            with pytest.raises(NotFoundException) as exc:
                pricing_service.compute_quote_pricing(payload, student_id="student_1")

            assert exc.value.code == "INSTRUCTOR_PROFILE_NOT_FOUND"

        def test_compute_quote_pricing_raises_on_instructor_mismatch(
            self, pricing_service, conflict_repo, instructor_profile_repo
        ):
            profile = SimpleNamespace(user_id="instructor_other")
            conflict_repo.get_active_service.return_value = _make_service()
            instructor_profile_repo.get_by_user_id.return_value = profile
            payload = _make_payload(instructor_id="instructor_1")

            with pytest.raises(ValidationException) as exc:
                pricing_service.compute_quote_pricing(payload, student_id="student_1")

            assert exc.value.code == "SERVICE_INSTRUCTOR_MISMATCH"

        def test_compute_quote_pricing_rejects_invalid_booking_date(
            self, pricing_service, conflict_repo, instructor_profile_repo
        ):
            profile = SimpleNamespace(user_id="instructor_1")
            conflict_repo.get_active_service.return_value = _make_service()
            instructor_profile_repo.get_by_user_id.return_value = profile
            payload = _make_payload(booking_date="2024-99-01")

            with pytest.raises(ValidationException) as exc:
                pricing_service.compute_quote_pricing(payload, student_id="student_1")

            assert exc.value.code == "INVALID_BOOKING_DATE"

        def test_compute_quote_pricing_rejects_invalid_start_time(
            self, pricing_service, conflict_repo, instructor_profile_repo
        ):
            profile = SimpleNamespace(user_id="instructor_1")
            conflict_repo.get_active_service.return_value = _make_service()
            instructor_profile_repo.get_by_user_id.return_value = profile
            payload = _make_payload(start_time="25:99")

            with pytest.raises(ValidationException) as exc:
                pricing_service.compute_quote_pricing(payload, student_id="student_1")

            assert exc.value.code == "INVALID_START_TIME"

        def test_compute_quote_pricing_reraises_domain_exception(
            self, pricing_service, conflict_repo, instructor_profile_repo
        ):
            profile = SimpleNamespace(user_id="instructor_1")
            conflict_repo.get_active_service.return_value = _make_service()
            instructor_profile_repo.get_by_user_id.return_value = profile
            payload = _make_payload()

            pricing_service._compute_pricing_from_inputs = Mock(
                side_effect=BusinessRuleException("floor", code="PRICE_BELOW_FLOOR")
            )

            with pytest.raises(BusinessRuleException):
                pricing_service.compute_quote_pricing(payload, student_id="student_1")

    class TestLoadInputs:
        def test_load_inputs_raises_when_booking_missing(self, pricing_service, booking_repo):
            booking_repo.get_with_pricing_context.return_value = None

            with pytest.raises(NotFoundException) as exc:
                pricing_service._load_inputs("missing")

            assert exc.value.code == "BOOKING_NOT_FOUND"

    class TestComputeBasePrice:
        def test_compute_base_price_cents_rejects_invalid_hourly_rate(self, pricing_service):
            booking = SimpleNamespace(hourly_rate="bad", duration_minutes=60)

            with pytest.raises(ValidationException) as exc:
                pricing_service._compute_base_price_cents(booking)

            assert exc.value.code == "INVALID_HOURLY_RATE"

        def test_compute_base_price_cents_rejects_invalid_duration(self, pricing_service):
            booking = SimpleNamespace(hourly_rate=Decimal("50"), duration_minutes="oops")

            with pytest.raises(ValidationException) as exc:
                pricing_service._compute_base_price_cents(booking)

            assert exc.value.code == "INVALID_DURATION"

    class TestModalityResolution:
        def test_resolve_modality_uses_service_offers_for_in_person(self):
            service = _make_service(offers_online=False, offers_travel=True)
            booking = SimpleNamespace(
                location_type="unknown",
                meeting_location=None,
                instructor_service=service,
            )

            assert PricingService._resolve_modality(booking) == "in_person"

    class TestPrivateBookingResolution:
        def test_is_private_booking_defaults_true_on_bad_group_size(self):
            booking = SimpleNamespace(group_size="invalid")

            assert PricingService._is_private_booking(booking) is True

        def test_is_private_booking_uses_is_group_flag(self):
            booking = SimpleNamespace(is_group=True)

            assert PricingService._is_private_booking(booking) is False

    class TestPriceFloor:
        def test_compute_price_floor_returns_none_without_floor_config(self):
            config = {"price_floor_cents": {}}

            assert PricingService._compute_price_floor_cents("in_person", 60, config) is None

        def test_compute_price_floor_returns_zero_for_non_positive_duration(self):
            config = {"price_floor_cents": {"private_in_person": 8000}}

            assert PricingService._compute_price_floor_cents("in_person", 0, config) == 0

    class TestInstructorTierResolution:
        def test_resolve_instructor_tier_pct_founding_invalid_rate_falls_back(
            self, pricing_service, booking_repo
        ):
            booking = SimpleNamespace(instructor_id="inst_1", status=BookingStatus.CONFIRMED)
            profile = SimpleNamespace(is_founding_instructor=True)
            pricing_config = {"founding_instructor_rate_pct": "bad"}

            result = pricing_service._resolve_instructor_tier_pct(
                booking=booking,
                instructor_profile=profile,
                pricing_config=pricing_config,
            )

            expected = Decimal(str(DEFAULT_PRICING_CONFIG["founding_instructor_rate_pct"])).quantize(
                Decimal("0.0001")
            )
            assert result == expected

        def test_resolve_instructor_tier_pct_uses_default_tiers_when_config_missing(
            self, pricing_service, booking_repo
        ):
            booking_repo.get_instructor_last_completed_at.return_value = datetime.now(timezone.utc)
            booking_repo.count_instructor_completed_last_30d.return_value = 0
            booking = SimpleNamespace(instructor_id="inst_1", status=BookingStatus.CONFIRMED)

            result = pricing_service._resolve_instructor_tier_pct(
                booking=booking,
                instructor_profile=None,
                pricing_config={"instructor_tiers": []},
            )

            assert result == Decimal("0.1500")

        def test_resolve_instructor_tier_pct_returns_zero_when_no_tiers(
            self, pricing_service, booking_repo, monkeypatch
        ):
            booking_repo.get_instructor_last_completed_at.return_value = datetime.now(timezone.utc)
            booking_repo.count_instructor_completed_last_30d.return_value = 0
            booking = SimpleNamespace(instructor_id="inst_1", status=BookingStatus.CONFIRMED)

            monkeypatch.setitem(DEFAULT_PRICING_CONFIG, "instructor_tiers", [])
            monkeypatch.setitem(PRICING_DEFAULTS, "instructor_tiers", [])

            result = pricing_service._resolve_instructor_tier_pct(
                booking=booking,
                instructor_profile=None,
                pricing_config={"instructor_tiers": []},
            )

            assert result == Decimal("0")

        def test_resolve_instructor_tier_pct_breaks_when_below_min_count(
            self, pricing_service, booking_repo
        ):
            booking_repo.get_instructor_last_completed_at.return_value = datetime.now(timezone.utc)
            booking_repo.count_instructor_completed_last_30d.return_value = 0
            booking = SimpleNamespace(instructor_id="inst_1", status=BookingStatus.CONFIRMED)
            pricing_config = {
                "instructor_tiers": [
                    {"min": 5, "max": 10, "pct": 0.12},
                    {"min": 11, "max": None, "pct": 0.10},
                ]
            }

            result = pricing_service._resolve_instructor_tier_pct(
                booking=booking,
                instructor_profile=None,
                pricing_config=pricing_config,
            )

            assert result == Decimal("0.1200")

        def test_resolve_instructor_tier_pct_handles_current_pct_not_in_tiers(
            self, pricing_service, booking_repo
        ):
            booking_repo.get_instructor_last_completed_at.return_value = datetime.now(timezone.utc)
            booking_repo.count_instructor_completed_last_30d.return_value = 5
            booking = SimpleNamespace(instructor_id="inst_1", status=BookingStatus.CONFIRMED)
            profile = SimpleNamespace(current_tier_pct=11)

            result = pricing_service._resolve_instructor_tier_pct(
                booking=booking,
                instructor_profile=profile,
                pricing_config=deepcopy(DEFAULT_PRICING_CONFIG),
            )

            assert result == Decimal("0.1200")

        def test_resolve_instructor_tier_pct_handles_required_pct_not_in_tiers(
            self, pricing_service, booking_repo
        ):
            class FlakyPct:
                def __init__(self, values):
                    self._values = list(values)
                    self._index = 0

                def __str__(self):
                    if self._index < len(self._values):
                        value = self._values[self._index]
                        self._index += 1
                        return value
                    return self._values[-1]

            booking_repo.get_instructor_last_completed_at.return_value = datetime.now(timezone.utc)
            booking_repo.count_instructor_completed_last_30d.return_value = 1
            booking = SimpleNamespace(instructor_id="inst_1", status=BookingStatus.CONFIRMED)
            profile = SimpleNamespace(current_tier_pct=12)
            pricing_config = {
                "instructor_tiers": [
                    {"min": 1, "max": None, "pct": FlakyPct(["0.12", "0.14"])},
                    {"min": 5, "max": None, "pct": 0.15},
                ],
                "tier_stepdown_max": 1,
            }

            result = pricing_service._resolve_instructor_tier_pct(
                booking=booking,
                instructor_profile=profile,
                pricing_config=pricing_config,
            )

            assert result == Decimal("0.1500")

    class TestUpdateInstructorTier:
        def test_update_instructor_tier_converts_pct_values(self, pricing_service):
            profile = SimpleNamespace(is_founding_instructor=False)

            updated = pricing_service.update_instructor_tier(profile, new_tier_pct=0.15)

            assert updated is True
            assert profile.current_tier_pct == Decimal("15")
            assert profile.last_tier_eval_at is not None

    class TestDefaultTierPct:
        def test_default_instructor_tier_pct_uses_default_config(self):
            result = PricingService._default_instructor_tier_pct({})

            assert result == Decimal("0.1500")

        def test_default_instructor_tier_pct_falls_back_to_pricing_defaults(self, monkeypatch):
            monkeypatch.setitem(DEFAULT_PRICING_CONFIG, "instructor_tiers", [])
            monkeypatch.setitem(PRICING_DEFAULTS, "instructor_tiers", [])

            result = PricingService._default_instructor_tier_pct({})

            assert result == Decimal("0")
