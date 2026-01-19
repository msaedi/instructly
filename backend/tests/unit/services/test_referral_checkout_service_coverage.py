"""
Comprehensive coverage tests for ReferralCheckoutService.

This test file targets the uncovered lines in referral_checkout_service.py
to achieve 90%+ coverage.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from fastapi import status
import pytest

from app.models.booking import Booking
from app.services.referral_checkout_service import (
    OrderState,
    ReferralCheckoutError,
    ReferralCheckoutService,
)


class TestReferralCheckoutError:
    """Test ReferralCheckoutError exception class."""

    def test_error_with_default_status_code(self) -> None:
        """Test error creation with default status code."""
        error = ReferralCheckoutError("test_reason")
        assert error.reason == "test_reason"
        assert error.status_code == status.HTTP_409_CONFLICT
        assert str(error) == "test_reason"

    def test_error_with_custom_status_code(self) -> None:
        """Test error creation with custom status code."""
        error = ReferralCheckoutError("not_found", status.HTTP_404_NOT_FOUND)
        assert error.reason == "not_found"
        assert error.status_code == status.HTTP_404_NOT_FOUND


class TestOrderState:
    """Test OrderState dataclass."""

    def test_order_state_creation(self) -> None:
        """Test OrderState dataclass creation."""
        state = OrderState(
            order_id="order_123",
            user_id="user_456",
            subtotal_cents=5000,
            has_promo=False,
        )
        assert state.order_id == "order_123"
        assert state.user_id == "user_456"
        assert state.subtotal_cents == 5000
        assert state.has_promo is False


class TestReferralCheckoutServiceInit:
    """Test ReferralCheckoutService initialization."""

    def test_service_initialization(self) -> None:
        """Test service initialization with dependencies."""
        mock_db = MagicMock()
        mock_wallet_service = MagicMock()

        with patch(
            "app.services.referral_checkout_service.RepositoryFactory"
        ) as mock_factory:
            mock_payment_repo = MagicMock()
            mock_booking_repo = MagicMock()
            mock_factory.create_payment_repository.return_value = mock_payment_repo
            mock_factory.create_booking_repository.return_value = mock_booking_repo

            service = ReferralCheckoutService(mock_db, mock_wallet_service)

            assert service.db == mock_db
            assert service.wallet_service == mock_wallet_service
            assert service.payment_repository == mock_payment_repo
            assert service.booking_repository == mock_booking_repo


class TestGetOrderState:
    """Test get_order_state method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_wallet_service(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def service(self, mock_db: MagicMock, mock_wallet_service: MagicMock) -> ReferralCheckoutService:
        with patch(
            "app.services.referral_checkout_service.RepositoryFactory"
        ) as mock_factory:
            mock_factory.create_payment_repository.return_value = MagicMock()
            mock_factory.create_booking_repository.return_value = MagicMock()
            return ReferralCheckoutService(mock_db, mock_wallet_service)

    def test_get_order_state_booking_not_found(self, service: ReferralCheckoutService) -> None:
        """Test get_order_state raises error when booking not found."""
        service.payment_repository.get_payment_by_intent_id.return_value = None
        service.payment_repository.get_payment_by_booking_id.return_value = None
        service.booking_repository.get_by_id.return_value = None

        with pytest.raises(ReferralCheckoutError) as exc_info:
            service.get_order_state(order_id="order_123", user_id="user_456")

        assert exc_info.value.reason == "order_not_found"
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    def test_get_order_state_order_not_owned(self, service: ReferralCheckoutService) -> None:
        """Test get_order_state raises error when user doesn't own the booking."""
        mock_booking = MagicMock(spec=Booking)
        mock_booking.student_id = "different_user"
        mock_booking.total_price = Decimal("100.00")

        service.payment_repository.get_payment_by_intent_id.return_value = None
        service.payment_repository.get_payment_by_booking_id.return_value = None
        service.booking_repository.get_by_id.return_value = mock_booking

        with pytest.raises(ReferralCheckoutError) as exc_info:
            service.get_order_state(order_id="order_123", user_id="user_456")

        assert exc_info.value.reason == "order_not_owned"
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    def test_get_order_state_success(self, service: ReferralCheckoutService) -> None:
        """Test successful get_order_state."""
        mock_booking = MagicMock(spec=Booking)
        mock_booking.student_id = "user_456"
        mock_booking.total_price = Decimal("100.00")
        mock_booking.used_credits = None
        mock_booking.generated_credits = None
        mock_booking.promo_code = None

        service.payment_repository.get_payment_by_intent_id.return_value = None
        service.payment_repository.get_payment_by_booking_id.return_value = None
        service.booking_repository.get_by_id.return_value = mock_booking

        state = service.get_order_state(order_id="order_123", user_id="user_456")

        assert state.order_id == "order_123"
        assert state.user_id == "user_456"
        assert state.subtotal_cents == 10000
        assert state.has_promo is False

    def test_get_order_state_with_promo(self, service: ReferralCheckoutService) -> None:
        """Test get_order_state with promo code."""
        mock_booking = MagicMock(spec=Booking)
        mock_booking.student_id = "user_456"
        mock_booking.total_price = Decimal("100.00")
        mock_booking.used_credits = None
        mock_booking.generated_credits = None
        mock_booking.promo_code = "PROMO123"

        service.payment_repository.get_payment_by_intent_id.return_value = None
        service.payment_repository.get_payment_by_booking_id.return_value = None
        service.booking_repository.get_by_id.return_value = mock_booking

        state = service.get_order_state(order_id="order_123", user_id="user_456")

        assert state.has_promo is True


class TestApplyStudentCredit:
    """Test apply_student_credit method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_wallet_service(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def service(self, mock_db: MagicMock, mock_wallet_service: MagicMock) -> ReferralCheckoutService:
        with patch(
            "app.services.referral_checkout_service.RepositoryFactory"
        ) as mock_factory:
            mock_factory.create_payment_repository.return_value = MagicMock()
            mock_factory.create_booking_repository.return_value = MagicMock()
            return ReferralCheckoutService(mock_db, mock_wallet_service)

    def test_apply_student_credit_disabled(self, service: ReferralCheckoutService) -> None:
        """Test apply_student_credit raises error when referrals disabled."""
        with patch(
            "app.services.referral_checkout_service.get_effective_config"
        ) as mock_config:
            mock_config.return_value = {"enabled": False}

            with pytest.raises(ReferralCheckoutError) as exc_info:
                service.apply_student_credit(user_id="user_456", order_id="order_123")

            assert exc_info.value.reason == "disabled"

    def test_apply_student_credit_promo_conflict(
        self, service: ReferralCheckoutService
    ) -> None:
        """Test apply_student_credit raises error on promo conflict."""
        mock_booking = MagicMock(spec=Booking)
        mock_booking.student_id = "user_456"
        mock_booking.total_price = Decimal("100.00")
        mock_booking.used_credits = "some_credits"
        mock_booking.generated_credits = None
        mock_booking.promo_code = None

        service.payment_repository.get_payment_by_intent_id.return_value = None
        service.payment_repository.get_payment_by_booking_id.return_value = None
        service.booking_repository.get_by_id.return_value = mock_booking

        with patch(
            "app.services.referral_checkout_service.get_effective_config"
        ) as mock_config:
            mock_config.return_value = {
                "enabled": True,
                "min_basket_cents": 1000,
                "student_amount_cents": 2000,
            }

            with pytest.raises(ReferralCheckoutError) as exc_info:
                service.apply_student_credit(user_id="user_456", order_id="order_123")

            assert exc_info.value.reason == "promo_conflict"

    def test_apply_student_credit_below_min_basket(
        self, service: ReferralCheckoutService
    ) -> None:
        """Test apply_student_credit raises error when below min basket."""
        mock_booking = MagicMock(spec=Booking)
        mock_booking.student_id = "user_456"
        mock_booking.total_price = Decimal("5.00")  # Only $5 = 500 cents
        mock_booking.used_credits = None
        mock_booking.generated_credits = None
        mock_booking.promo_code = None

        service.payment_repository.get_payment_by_intent_id.return_value = None
        service.payment_repository.get_payment_by_booking_id.return_value = None
        service.booking_repository.get_by_id.return_value = mock_booking

        with patch(
            "app.services.referral_checkout_service.get_effective_config"
        ) as mock_config:
            mock_config.return_value = {
                "enabled": True,
                "min_basket_cents": 1000,  # Min $10
                "student_amount_cents": 2000,
            }

            with pytest.raises(ReferralCheckoutError) as exc_info:
                service.apply_student_credit(user_id="user_456", order_id="order_123")

            assert exc_info.value.reason == "below_min_basket"

    def test_apply_student_credit_no_unlocked_credit(
        self, service: ReferralCheckoutService
    ) -> None:
        """Test apply_student_credit raises error when no unlocked credit."""
        mock_booking = MagicMock(spec=Booking)
        mock_booking.student_id = "user_456"
        mock_booking.total_price = Decimal("100.00")
        mock_booking.used_credits = None
        mock_booking.generated_credits = None
        mock_booking.promo_code = None

        service.payment_repository.get_payment_by_intent_id.return_value = None
        service.payment_repository.get_payment_by_booking_id.return_value = None
        service.booking_repository.get_by_id.return_value = mock_booking
        service.wallet_service.consume_student_credit.return_value = None

        with patch(
            "app.services.referral_checkout_service.get_effective_config"
        ) as mock_config:
            mock_config.return_value = {
                "enabled": True,
                "min_basket_cents": 1000,
                "student_amount_cents": 2000,
            }

            with pytest.raises(ReferralCheckoutError) as exc_info:
                service.apply_student_credit(user_id="user_456", order_id="order_123")

            assert exc_info.value.reason == "no_unlocked_credit"

    def test_apply_student_credit_success(
        self, service: ReferralCheckoutService
    ) -> None:
        """Test successful apply_student_credit."""
        mock_booking = MagicMock(spec=Booking)
        mock_booking.student_id = "user_456"
        mock_booking.total_price = Decimal("100.00")
        mock_booking.used_credits = None
        mock_booking.generated_credits = None
        mock_booking.promo_code = None

        service.payment_repository.get_payment_by_intent_id.return_value = None
        service.payment_repository.get_payment_by_booking_id.return_value = None
        service.booking_repository.get_by_id.return_value = mock_booking

        mock_txn = MagicMock()
        mock_txn.amount_cents = 2000
        service.wallet_service.consume_student_credit.return_value = mock_txn

        with patch(
            "app.services.referral_checkout_service.get_effective_config"
        ) as mock_config:
            mock_config.return_value = {
                "enabled": True,
                "min_basket_cents": 1000,
                "student_amount_cents": 2000,
            }

            result = service.apply_student_credit(user_id="user_456", order_id="order_123")

            assert result == 2000
            service.wallet_service.consume_student_credit.assert_called_once_with(
                user_id="user_456",
                order_id="order_123",
                amount_cents=2000,
            )


class TestResolveBooking:
    """Test _resolve_booking method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_wallet_service(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def service(self, mock_db: MagicMock, mock_wallet_service: MagicMock) -> ReferralCheckoutService:
        with patch(
            "app.services.referral_checkout_service.RepositoryFactory"
        ) as mock_factory:
            mock_factory.create_payment_repository.return_value = MagicMock()
            mock_factory.create_booking_repository.return_value = MagicMock()
            return ReferralCheckoutService(mock_db, mock_wallet_service)

    def test_resolve_booking_by_intent_id(self, service: ReferralCheckoutService) -> None:
        """Test _resolve_booking finds booking via payment intent ID."""
        mock_booking = MagicMock(spec=Booking)
        mock_payment = MagicMock()
        mock_payment.booking = mock_booking

        service.payment_repository.get_payment_by_intent_id.return_value = mock_payment

        result = service._resolve_booking("pi_test_123")

        assert result == mock_booking
        service.payment_repository.get_payment_by_intent_id.assert_called_once_with("pi_test_123")

    def test_resolve_booking_by_booking_id_from_payment(
        self, service: ReferralCheckoutService
    ) -> None:
        """Test _resolve_booking finds booking via payment's booking_id."""
        mock_booking = MagicMock(spec=Booking)
        mock_payment = MagicMock()
        mock_payment.booking = mock_booking

        service.payment_repository.get_payment_by_intent_id.return_value = None
        service.payment_repository.get_payment_by_booking_id.return_value = mock_payment

        result = service._resolve_booking("booking_123")

        assert result == mock_booking

    def test_resolve_booking_directly(self, service: ReferralCheckoutService) -> None:
        """Test _resolve_booking finds booking directly by ID."""
        mock_booking = MagicMock(spec=Booking)

        service.payment_repository.get_payment_by_intent_id.return_value = None
        service.payment_repository.get_payment_by_booking_id.return_value = None
        service.booking_repository.get_by_id.return_value = mock_booking

        result = service._resolve_booking("booking_123")

        assert result == mock_booking
        service.booking_repository.get_by_id.assert_called_once_with("booking_123")

    def test_resolve_booking_not_found(self, service: ReferralCheckoutService) -> None:
        """Test _resolve_booking returns None when booking not found."""
        service.payment_repository.get_payment_by_intent_id.return_value = None
        service.payment_repository.get_payment_by_booking_id.return_value = None
        service.booking_repository.get_by_id.return_value = None

        result = service._resolve_booking("nonexistent")

        assert result is None

    def test_resolve_booking_payment_has_no_booking_attr(
        self, service: ReferralCheckoutService
    ) -> None:
        """Test _resolve_booking handles payment without booking attribute."""
        mock_payment = MagicMock()
        mock_payment.booking = None  # No booking attached

        service.payment_repository.get_payment_by_intent_id.return_value = mock_payment
        service.payment_repository.get_payment_by_booking_id.return_value = None
        service.booking_repository.get_by_id.return_value = None

        result = service._resolve_booking("pi_test_123")

        assert result is None

    def test_resolve_booking_payment_booking_not_booking_instance(
        self, service: ReferralCheckoutService
    ) -> None:
        """Test _resolve_booking handles payment with non-Booking booking attr."""
        mock_payment = MagicMock()
        mock_payment.booking = "not_a_booking_object"  # Wrong type

        mock_booking = MagicMock(spec=Booking)

        service.payment_repository.get_payment_by_intent_id.return_value = mock_payment
        service.payment_repository.get_payment_by_booking_id.return_value = None
        service.booking_repository.get_by_id.return_value = mock_booking

        result = service._resolve_booking("pi_test_123")

        assert result == mock_booking


class TestBookingHasPromo:
    """Test _booking_has_promo static method."""

    def test_booking_has_used_credits(self) -> None:
        """Test returns True when booking has used_credits."""
        mock_booking = MagicMock()
        mock_booking.used_credits = "some_credits"
        mock_booking.generated_credits = None
        mock_booking.promo_code = None

        result = ReferralCheckoutService._booking_has_promo(mock_booking)

        assert result is True

    def test_booking_has_generated_credits(self) -> None:
        """Test returns True when booking has generated_credits."""
        mock_booking = MagicMock()
        mock_booking.used_credits = None
        mock_booking.generated_credits = "some_credits"
        mock_booking.promo_code = None

        result = ReferralCheckoutService._booking_has_promo(mock_booking)

        assert result is True

    def test_booking_has_promo_code(self) -> None:
        """Test returns True when booking has promo_code."""
        mock_booking = MagicMock()
        mock_booking.used_credits = None
        mock_booking.generated_credits = None
        mock_booking.promo_code = "PROMO123"

        result = ReferralCheckoutService._booking_has_promo(mock_booking)

        assert result is True

    def test_booking_has_no_promo(self) -> None:
        """Test returns False when booking has no promo."""
        mock_booking = MagicMock()
        mock_booking.used_credits = None
        mock_booking.generated_credits = None
        mock_booking.promo_code = None

        result = ReferralCheckoutService._booking_has_promo(mock_booking)

        assert result is False


class TestDecimalToCents:
    """Test _decimal_to_cents static method."""

    def test_decimal_to_cents_with_decimal(self) -> None:
        """Test conversion with Decimal input."""
        result = ReferralCheckoutService._decimal_to_cents(Decimal("100.00"))
        assert result == 10000

    def test_decimal_to_cents_with_decimal_fractional(self) -> None:
        """Test conversion with fractional Decimal."""
        result = ReferralCheckoutService._decimal_to_cents(Decimal("100.99"))
        assert result == 10099

    def test_decimal_to_cents_with_decimal_rounding(self) -> None:
        """Test conversion with Decimal that needs rounding."""
        result = ReferralCheckoutService._decimal_to_cents(Decimal("100.995"))
        assert result == 10100  # Rounds to 100.99 or 101.00

    def test_decimal_to_cents_with_int(self) -> None:
        """Test conversion with int input."""
        result = ReferralCheckoutService._decimal_to_cents(100)
        assert result == 10000

    def test_decimal_to_cents_with_float(self) -> None:
        """Test conversion with float input."""
        result = ReferralCheckoutService._decimal_to_cents(100.50)
        assert result == 10050

    def test_decimal_to_cents_with_unsupported_type(self) -> None:
        """Test conversion raises error with unsupported type."""
        with pytest.raises(ValueError, match="Unsupported amount type"):
            ReferralCheckoutService._decimal_to_cents("100.00")  # type: ignore
