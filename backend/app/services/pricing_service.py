"""Centralized pricing calculations for bookings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessRuleException,
    NotFoundException,
    ValidationException,
)
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.repositories.booking_repository import BookingRepository
from app.repositories.factory import RepositoryFactory
from app.services.base import BaseService
from app.services.config_service import ConfigService


@dataclass(frozen=True)
class PricingInputs:
    """Snapshot of booking context required for pricing calculations."""

    booking: Booking
    instructor_profile: Optional[InstructorProfile]
    pricing_config: Dict[str, Any]


class PricingService(BaseService):
    """Compute pricing line items and payouts for bookings."""

    def __init__(self, db_session: Session) -> None:
        super().__init__(db_session)
        self.booking_repository: BookingRepository = RepositoryFactory.create_booking_repository(
            db_session
        )
        self.config_service = ConfigService(db_session)

    @BaseService.measure_operation("pricing.compute_booking")
    def compute_booking_pricing(
        self,
        booking_id: str,
        applied_credit_cents: int = 0,
        persist: bool = False,
    ) -> Dict[str, Any]:
        if applied_credit_cents < 0:
            raise ValidationException(
                "applied_credit_cents must be non-negative",
                code="NEGATIVE_CREDIT",
                details={"applied_credit_cents": applied_credit_cents},
            )

        inputs = self._load_inputs(booking_id)
        booking = inputs.booking

        # Future steps will persist tier updates/Stripe wiring; preview never persists.
        _ = persist  # pragma: no cover - placeholder until Step 5 implementation

        base_price_cents = self._compute_base_price_cents(booking)
        modality = self._resolve_modality(booking)
        is_private = self._is_private_booking(booking)
        floor_cents = self._compute_price_floor_cents(
            modality, booking.duration_minutes, inputs.pricing_config
        )

        if is_private and floor_cents is not None and base_price_cents < floor_cents:
            required_dollars = self._format_cents(floor_cents)
            current_dollars = self._format_cents(base_price_cents)
            modality_label = "in-person" if modality == "in_person" else "remote"
            raise BusinessRuleException(
                message=(
                    "Minimum price for a "
                    f"{modality_label} {booking.duration_minutes}-minute private session is ${required_dollars} "
                    f"(current ${current_dollars})."
                ),
                code="PRICE_BELOW_FLOOR",
                details={
                    "modality": modality,
                    "duration_minutes": booking.duration_minutes,
                    "base_price_cents": base_price_cents,
                    "required_floor_cents": floor_cents,
                },
            )

        student_fee_pct = Decimal(str(inputs.pricing_config["student_fee_pct"]))
        tier_pct = self._resolve_instructor_tier_pct(
            booking=booking,
            instructor_profile=inputs.instructor_profile,
            pricing_config=inputs.pricing_config,
        )

        student_fee_cents = self._round_to_int(Decimal(base_price_cents) * student_fee_pct)
        instructor_commission_cents = self._round_to_int(Decimal(base_price_cents) * tier_pct)
        target_payout_cents = base_price_cents - instructor_commission_cents

        credit_cents = int(applied_credit_cents)
        subtotal_with_fee = base_price_cents + student_fee_cents

        student_pay_cents = max(0, subtotal_with_fee - credit_cents)
        application_fee_raw = student_fee_cents + instructor_commission_cents - credit_cents
        application_fee_cents = max(0, application_fee_raw)

        top_up_transfer_cents = 0
        if application_fee_cents == 0 and student_pay_cents < target_payout_cents:
            top_up_transfer_cents = target_payout_cents - student_pay_cents

        line_items = self._build_line_items(
            student_fee_cents=student_fee_cents,
            credit_cents=credit_cents,
            student_fee_pct=student_fee_pct,
        )

        return {
            "base_price_cents": base_price_cents,
            "student_fee_cents": student_fee_cents,
            "instructor_commission_cents": instructor_commission_cents,
            "target_instructor_payout_cents": target_payout_cents,
            "credit_applied_cents": credit_cents,
            "student_pay_cents": student_pay_cents,
            "application_fee_cents": application_fee_cents,
            "top_up_transfer_cents": top_up_transfer_cents,
            "instructor_tier_pct": float(tier_pct),
            "line_items": line_items,
        }

    def _load_inputs(self, booking_id: str) -> PricingInputs:
        booking = self.booking_repository.get_with_pricing_context(booking_id)

        if not booking:
            raise NotFoundException(
                "Booking not found",
                code="BOOKING_NOT_FOUND",
                details={"booking_id": booking_id},
            )

        pricing_config, _ = self.config_service.get_pricing_config()
        instructor_profile = getattr(booking.instructor, "instructor_profile", None)
        return PricingInputs(
            booking=booking,
            instructor_profile=instructor_profile,
            pricing_config=pricing_config,
        )

    @staticmethod
    def _round_to_int(value: Decimal) -> int:
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def _compute_base_price_cents(self, booking: Booking) -> int:
        try:
            hourly_rate = Decimal(str(booking.hourly_rate))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationException(
                "Booking hourly rate is invalid",
                code="INVALID_HOURLY_RATE",
                details={"hourly_rate": getattr(booking, "hourly_rate", None)},
            ) from exc

        try:
            duration_minutes = int(booking.duration_minutes)
        except (TypeError, ValueError) as exc:
            raise ValidationException(
                "Booking duration is invalid",
                code="INVALID_DURATION",
                details={"duration_minutes": getattr(booking, "duration_minutes", None)},
            ) from exc
        cents_value = hourly_rate * Decimal(duration_minutes) * Decimal(100) / Decimal(60)
        return self._round_to_int(cents_value)

    @staticmethod
    def _resolve_modality(booking: Booking) -> str:
        location = str(getattr(booking, "location_type", "") or "").lower()
        if location in {"student_home", "instructor_location", "neutral", "in_person"}:
            return "in_person"
        if "remote" in location or "online" in location or "virtual" in location:
            return "remote"
        service_location_types = getattr(booking.instructor_service, "location_types", None)
        if service_location_types and any(
            str(loc).lower() in {"online", "remote", "virtual"} for loc in service_location_types
        ):
            return "remote"
        return "in_person"

    @staticmethod
    def _is_private_booking(booking: Booking) -> bool:
        group_size = getattr(booking, "group_size", None)
        if group_size is not None:
            try:
                return int(group_size) <= 1
            except (TypeError, ValueError):
                return True
        is_group = getattr(booking, "is_group", None)
        if is_group is not None:
            return not bool(is_group)
        return True

    @staticmethod
    def _compute_price_floor_cents(
        modality: str, duration_minutes: int, config: Dict[str, Any]
    ) -> Optional[int]:
        floors = config.get("price_floor_cents", {})
        if modality == "in_person":
            base_floor = floors.get("private_in_person")
        else:
            base_floor = floors.get("private_remote")
        if base_floor is None:
            return None
        base_floor_int = int(base_floor)
        if duration_minutes <= 0:
            return 0

        prorated = (Decimal(base_floor_int) * Decimal(duration_minutes) / Decimal(60)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        return int(prorated)

    def _resolve_instructor_tier_pct(
        self,
        *,
        booking: Booking,
        instructor_profile: Optional[InstructorProfile],
        pricing_config: Dict[str, Any],
    ) -> Decimal:
        tiers = sorted(
            pricing_config.get("instructor_tiers", []), key=lambda tier: tier.get("min", 0)
        )
        if not tiers:
            return Decimal("0.15")

        tier_pcts = [Decimal(str(tier["pct"])).quantize(Decimal("0.0001")) for tier in tiers]
        fallback_pct = max(tier_pcts)
        current_pct = fallback_pct
        if instructor_profile and instructor_profile.current_tier_pct is not None:
            current_pct = (
                Decimal(str(instructor_profile.current_tier_pct)) / Decimal(100)
            ).quantize(Decimal("0.0001"))

        inactivity_days = int(pricing_config.get("tier_inactivity_reset_days", 90))
        now = datetime.now(timezone.utc)
        last_completed = self.booking_repository.get_instructor_last_completed_at(
            booking.instructor_id
        )
        if not last_completed or last_completed < now - timedelta(days=inactivity_days):
            return fallback_pct.quantize(Decimal("0.0001"))

        completed_count = self.booking_repository.count_instructor_completed_last_30d(
            booking.instructor_id
        )
        increment = 1 if booking.status in {BookingStatus.CONFIRMED, BookingStatus.PENDING} else 0
        projected_count = max(0, completed_count + increment)

        required_pct = fallback_pct
        for tier in tiers:
            min_count = int(tier.get("min", 0))
            max_count = tier.get("max")
            if projected_count < min_count:
                break
            required_pct = Decimal(str(tier["pct"]))
            if max_count is None or projected_count <= max_count:
                break

        required_pct = required_pct.quantize(Decimal("0.0001"))
        if required_pct < current_pct:
            return required_pct
        if required_pct == current_pct:
            return current_pct

        ordered = sorted(set(tier_pcts))
        try:
            current_index = ordered.index(current_pct)
        except ValueError:
            current_index = min(
                range(len(ordered)), key=lambda idx: abs(ordered[idx] - current_pct)
            )
        try:
            required_index = ordered.index(required_pct)
        except ValueError:
            required_index = min(
                range(len(ordered)), key=lambda idx: abs(ordered[idx] - required_pct)
            )

        stepdown_max = int(pricing_config.get("tier_stepdown_max", 1))
        stepdown_spread = max(0, required_index - current_index)
        stepdown = min(stepdown_spread, max(stepdown_max, 0))
        new_index = min(current_index + stepdown, required_index, len(ordered) - 1)
        return ordered[new_index].quantize(Decimal("0.0001"))

    @staticmethod
    def _build_line_items(
        *,
        student_fee_cents: int,
        credit_cents: int,
        student_fee_pct: Decimal,
    ) -> List[Dict[str, Any]]:
        label_pct = int(
            (student_fee_pct * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        items: List[Dict[str, Any]] = [
            {"label": f"Booking Protection ({label_pct}%)", "amount_cents": student_fee_cents}
        ]
        if credit_cents > 0:
            items.append({"label": "Credit", "amount_cents": -credit_cents})
        return items

    @staticmethod
    def _format_cents(amount_cents: int) -> str:
        dollars = Decimal(amount_cents) / Decimal(100)
        return f"{dollars.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


__all__ = ["PricingService"]
