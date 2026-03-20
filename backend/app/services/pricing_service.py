"""Centralized pricing calculations for bookings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, TypedDict

from sqlalchemy.orm import Session

from app.constants.pricing_defaults import PRICING_DEFAULTS
from app.core.exceptions import (
    BusinessRuleException,
    NotFoundException,
    ValidationException,
)
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.repositories.booking_repository import BookingRepository
from app.repositories.factory import RepositoryFactory
from app.schemas.instructor import CommissionStatusResponse, TierInfo
from app.schemas.pricing_preview import (
    LineItemData,
    PricingPreviewData,
    PricingPreviewIn,
)

if TYPE_CHECKING:
    from app.repositories.conflict_checker_repository import ConflictCheckerRepository
    from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.services.base import BaseService
from app.services.config_service import DEFAULT_PRICING_CONFIG, ConfigService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PricingInputs:
    """Snapshot of booking context required for pricing calculations."""

    booking: Booking
    instructor_profile: Optional[InstructorProfile]
    pricing_config: Dict[str, Any]


class TierDefinition(TypedDict):
    """Normalized instructor commission tier metadata for display logic."""

    name: str
    display_name: str
    commission_rate: Decimal
    min_lessons: int
    max_lessons: int | None


class TierEvaluationResults(TypedDict):
    evaluated: int
    updated: int
    failed: int
    processed_at: str


class PricingService(BaseService):
    """Compute pricing line items and payouts for bookings."""

    def __init__(self, db_session: Session) -> None:
        super().__init__(db_session)
        self.booking_repository: BookingRepository = RepositoryFactory.create_booking_repository(
            db_session
        )
        self.config_service: ConfigService = ConfigService(db_session)
        self._conflict_checker_repository: ConflictCheckerRepository = (
            RepositoryFactory.create_conflict_checker_repository(db_session)
        )
        self._instructor_profile_repository: InstructorProfileRepository = (
            RepositoryFactory.create_instructor_profile_repository(db_session)
        )

    @BaseService.measure_operation("pricing.compute_booking")
    def compute_booking_pricing(
        self,
        booking_id: str,
        applied_credit_cents: int = 0,
    ) -> PricingPreviewData:
        if applied_credit_cents < 0:
            raise ValidationException(
                "applied_credit_cents must be non-negative",
                code="NEGATIVE_CREDIT",
                details={"applied_credit_cents": applied_credit_cents},
            )

        inputs = self._load_inputs(booking_id)

        return self._compute_pricing_from_inputs(
            inputs=inputs,
            applied_credit_cents=applied_credit_cents,
        )

    @BaseService.measure_operation("pricing.compute_quote")
    def compute_quote_pricing(
        self, payload: PricingPreviewIn, *, student_id: str
    ) -> PricingPreviewData:
        if payload.applied_credit_cents < 0:
            raise ValidationException(
                "applied_credit_cents must be non-negative",
                code="NEGATIVE_CREDIT",
                details={"applied_credit_cents": payload.applied_credit_cents},
            )

        service = self._conflict_checker_repository.get_active_service(
            payload.instructor_service_id
        )
        if service is None:
            raise NotFoundException(
                "Instructor service not found",
                code="INSTRUCTOR_SERVICE_NOT_FOUND",
                details={"instructor_service_id": payload.instructor_service_id},
            )

        instructor_profile = service.instructor_profile
        if instructor_profile is None:
            instructor_profile = self._instructor_profile_repository.get_by_user_id(
                payload.instructor_id
            )

        if instructor_profile is None:
            raise NotFoundException(
                "Instructor profile not found",
                code="INSTRUCTOR_PROFILE_NOT_FOUND",
                details={"instructor_id": payload.instructor_id},
            )

        if str(instructor_profile.user_id) != str(payload.instructor_id):
            raise ValidationException(
                "Service does not belong to instructor",
                code="SERVICE_INSTRUCTOR_MISMATCH",
                details={
                    "instructor_id": payload.instructor_id,
                    "service_instructor_id": instructor_profile.user_id,
                },
            )

        try:
            booking_date_obj = datetime.strptime(payload.booking_date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValidationException(
                "Invalid booking_date format. Expected YYYY-MM-DD",
                code="INVALID_BOOKING_DATE",
                details={"booking_date": payload.booking_date},
            ) from exc

        try:
            start_time_obj = datetime.strptime(payload.start_time, "%H:%M").time()
        except ValueError as exc:
            raise ValidationException(
                "Invalid start_time format. Expected HH:MM",
                code="INVALID_START_TIME",
                details={"start_time": payload.start_time},
            ) from exc

        duration_minutes = int(payload.selected_duration)
        end_time_obj = (
            datetime.combine(  # tz-pattern-ok: duration math only
                date(2000, 1, 1), start_time_obj, tzinfo=timezone.utc
            )
            + timedelta(minutes=duration_minutes)
        ).time()

        hourly_rate = service.hourly_rate_for_location_type(payload.location_type)

        booking = Booking(
            student_id=student_id,
            instructor_id=payload.instructor_id,
            instructor_service_id=payload.instructor_service_id,
            booking_date=booking_date_obj,
            start_time=start_time_obj,
            end_time=end_time_obj,
            service_name=service.name,
            hourly_rate=hourly_rate,
            total_price=Decimal("0.00"),
            duration_minutes=duration_minutes,
            status=BookingStatus.CONFIRMED,
            location_type=payload.location_type,
            meeting_location=payload.meeting_location,
        )

        # Attach related objects for downstream access (pricing floors, tiers)
        booking.instructor_service = service

        pricing_config, _ = self.config_service.get_pricing_config()

        # Build lightweight PricingInputs replica to reuse existing helpers
        inputs = PricingInputs(
            booking=booking,
            instructor_profile=instructor_profile,
            pricing_config=pricing_config,
        )

        return self._compute_pricing_from_inputs(
            inputs=inputs,
            applied_credit_cents=payload.applied_credit_cents,
        )

    @BaseService.measure_operation("pricing.get_instructor_commission_status")
    def get_instructor_commission_status(
        self, *, instructor_user_id: str
    ) -> CommissionStatusResponse:
        """Return the persisted instructor commission tier and progress display data."""

        instructor_profile = self._instructor_profile_repository.get_by_user_id(instructor_user_id)
        if instructor_profile is None:
            raise NotFoundException(
                "Instructor profile not found",
                code="INSTRUCTOR_PROFILE_NOT_FOUND",
                details={"instructor_user_id": instructor_user_id},
            )

        pricing_config, _ = self.config_service.get_pricing_config()
        tier_defs = self._commission_tier_definitions(pricing_config)
        activity_window_days = int(pricing_config.get("tier_activity_window_days", 30))
        completed_lessons_30d = self.booking_repository.count_instructor_completed_in_window(
            instructor_user_id,
            activity_window_days,
        )

        is_founding = bool(getattr(instructor_profile, "is_founding_instructor", False))
        founding_rate = self._founding_rate_pct(pricing_config)

        if is_founding:
            tier_name = "founding"
            commission_rate = founding_rate
        else:
            tier_name = self._resolve_persisted_tier_name(instructor_profile, tier_defs)
            commission_rate = self._tier_rate_for_name(tier_name, tier_defs)

        next_tier_name: str | None = None
        next_tier_threshold: int | None = None
        lessons_to_next_tier: int | None = None
        current_index = -1
        if not is_founding:
            current_index = next(
                (idx for idx, tier in enumerate(tier_defs) if tier["name"] == tier_name),
                0,
            )
            if current_index < len(tier_defs) - 1:
                next_tier = tier_defs[current_index + 1]
                next_tier_name = str(next_tier["name"])
                next_tier_threshold = int(next_tier["min_lessons"])
                lessons_to_next_tier = max(0, next_tier_threshold - completed_lessons_30d)

        tiers = [
            TierInfo(
                name=str(tier["name"]),
                display_name=str(tier["display_name"]),
                commission_pct=self._commission_rate_pct_float(tier["commission_rate"]),
                min_lessons=int(tier["min_lessons"]),
                max_lessons=(int(tier["max_lessons"]) if tier["max_lessons"] is not None else None),
                is_current=(not is_founding and tier_name == tier["name"]),
                is_unlocked=bool(
                    not is_founding
                    and (idx <= current_index or completed_lessons_30d >= int(tier["min_lessons"]))
                ),
            )
            for idx, tier in enumerate(tier_defs)
        ]

        return CommissionStatusResponse(
            is_founding=is_founding,
            tier_name=tier_name,
            commission_rate_pct=self._commission_rate_pct_float(commission_rate),
            activity_window_days=activity_window_days,
            completed_lessons_30d=completed_lessons_30d,
            next_tier_name=next_tier_name,
            next_tier_threshold=next_tier_threshold,
            lessons_to_next_tier=lessons_to_next_tier,
            tiers=tiers,
        )

    def _compute_pricing_from_inputs(
        self,
        *,
        inputs: PricingInputs,
        applied_credit_cents: int,
    ) -> PricingPreviewData:
        booking = inputs.booking

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
        fallback_tier_pct = self._default_instructor_tier_pct(inputs.pricing_config)
        tier_pct_decimal = tier_pct if tier_pct is not None else fallback_tier_pct

        student_fee_cents = self._round_to_int(Decimal(base_price_cents) * student_fee_pct)
        instructor_platform_fee_cents = self._round_to_int(
            Decimal(base_price_cents) * tier_pct_decimal
        )
        target_payout_cents = base_price_cents - instructor_platform_fee_cents

        # Part 6: Credits can only cover the lesson price, never the platform fee.
        # The minimum card charge is always the platform fee (student_fee_cents).
        credit_cents = min(int(applied_credit_cents), base_price_cents)
        lesson_after_credit = base_price_cents - credit_cents

        # Student pays: (lesson price - credits) + platform fee
        # Platform fee is ALWAYS charged to the card (minimum card charge)
        student_pay_cents = lesson_after_credit + student_fee_cents

        # Application fee includes student fee + instructor fee, minus credits
        # (credits reduce the lesson price, not fees)
        application_fee_raw = student_fee_cents + instructor_platform_fee_cents - credit_cents
        application_fee_cents = max(0, application_fee_raw)

        top_up_transfer_cents = 0
        if application_fee_cents == 0 and student_pay_cents < target_payout_cents:
            top_up_transfer_cents = target_payout_cents - student_pay_cents

        line_items = self._build_line_items(
            student_fee_cents=student_fee_cents,
            credit_cents=credit_cents,
            student_fee_pct=student_fee_pct,
        )

        pricing_data: PricingPreviewData = {
            "base_price_cents": base_price_cents,
            "student_fee_cents": student_fee_cents,
            "instructor_platform_fee_cents": instructor_platform_fee_cents,
            "target_instructor_payout_cents": target_payout_cents,
            "credit_applied_cents": credit_cents,
            "student_pay_cents": student_pay_cents,
            "application_fee_cents": application_fee_cents,
            "top_up_transfer_cents": top_up_transfer_cents,
            "instructor_tier_pct": float(tier_pct_decimal),
            "line_items": line_items,
        }

        return pricing_data

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
        if "remote" in location or "online" in location or "virtual" in location:
            return "remote"
        if location in {"student_location", "instructor_location", "neutral_location"}:
            if PricingService._meeting_location_indicates_remote(booking):
                return "remote"
            return "in_person"
        service = getattr(booking, "instructor_service", None)
        if service:
            offers_online = bool(getattr(service, "offers_online", False))
            offers_in_person = bool(getattr(service, "offers_travel", False)) or bool(
                getattr(service, "offers_at_location", False)
            )
            if offers_online and not offers_in_person:
                return "remote"
            if offers_in_person:
                return "in_person"
        if PricingService._meeting_location_indicates_remote(booking):
            return "remote"
        return "in_person"

    @staticmethod
    def _meeting_location_indicates_remote(booking: Booking) -> bool:
        meeting_location = str(getattr(booking, "meeting_location", "") or "").lower()
        if not meeting_location:
            return False
        return any(keyword in meeting_location for keyword in ("online", "remote", "virtual"))

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
        projected_increment = (
            1 if booking.status in {BookingStatus.CONFIRMED, BookingStatus.PENDING} else 0
        )
        return self._resolve_instructor_tier_pct_for_instructor(
            instructor_user_id=booking.instructor_id,
            instructor_profile=instructor_profile,
            pricing_config=pricing_config,
            projected_increment=projected_increment,
        )

    def _resolve_instructor_tier_pct_for_instructor(
        self,
        *,
        instructor_user_id: str,
        instructor_profile: Optional[InstructorProfile],
        pricing_config: Dict[str, Any],
        projected_increment: int = 0,
        completion_stats: tuple[int, Optional[datetime]] | None = None,
    ) -> Decimal:
        # NOTE: Founding instructors are immune to tier changes; always use founding rate.
        if instructor_profile and getattr(instructor_profile, "is_founding_instructor", False):
            return self._founding_rate_pct(pricing_config)

        tiers = sorted(
            pricing_config.get("instructor_tiers", []), key=lambda tier: tier.get("min", 0)
        )
        if not tiers:
            default_tiers = DEFAULT_PRICING_CONFIG.get("instructor_tiers", [])
            tiers = sorted(default_tiers, key=lambda tier: tier.get("min", 0))
        if not tiers:
            return Decimal("0")

        tier_pcts = [Decimal(str(tier["pct"])).quantize(Decimal("0.0001")) for tier in tiers]
        fallback_pct = max(tier_pcts)
        current_pct = fallback_pct
        if instructor_profile and instructor_profile.current_tier_pct is not None:
            current_pct = self._normalize_stored_tier_rate(
                instructor_profile.current_tier_pct,
                fallback=fallback_pct,
            )

        inactivity_days = int(pricing_config.get("tier_inactivity_reset_days", 90))
        activity_window_days = int(pricing_config.get("tier_activity_window_days", 30))
        now = datetime.now(timezone.utc)
        completed_count: int
        last_completed: Optional[datetime]
        if completion_stats is None:
            last_completed = self.booking_repository.get_instructor_last_completed_at(
                instructor_user_id
            )
            completed_count = self.booking_repository.count_instructor_completed_in_window(
                instructor_user_id,
                activity_window_days,
            )
        else:
            completed_count, last_completed = completion_stats
        if not last_completed or last_completed < now - timedelta(days=inactivity_days):
            return fallback_pct.quantize(Decimal("0.0001"))
        projected_count = max(0, completed_count + max(projected_increment, 0))

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
    def _normalize_stored_tier_rate(value: Any, *, fallback: Decimal) -> Decimal:
        try:
            rate = Decimal(str(value))
            if rate > 1:
                rate = rate / Decimal("100")
            return rate.quantize(Decimal("0.0001"))
        except (InvalidOperation, TypeError, ValueError):
            return fallback.quantize(Decimal("0.0001"))

    def _should_persist_tier_change(
        self,
        *,
        instructor_profile: InstructorProfile,
        resolved_rate: Decimal,
        pricing_config: Dict[str, Any],
    ) -> bool:
        fallback_rate = self._default_instructor_tier_pct(pricing_config)
        current_rate = self._normalize_stored_tier_rate(
            getattr(instructor_profile, "current_tier_pct", None),
            fallback=fallback_rate,
        )
        return current_rate != resolved_rate.quantize(Decimal("0.0001"))

    @staticmethod
    def _commission_rate_decimal(value: Any, *, fallback: Decimal = Decimal("0")) -> Decimal:
        try:
            return Decimal(str(value)).quantize(Decimal("0.0001"))
        except (InvalidOperation, TypeError, ValueError):
            return fallback.quantize(Decimal("0.0001"))

    @staticmethod
    def _commission_rate_pct_float(rate_decimal: Decimal) -> float:
        return float((rate_decimal * Decimal("100")).quantize(Decimal("0.01")))

    @classmethod
    def _founding_rate_pct(cls, pricing_config: Dict[str, Any]) -> Decimal:
        """Get the founding instructor commission rate from config."""
        fallback_rate = DEFAULT_PRICING_CONFIG.get(
            "founding_instructor_rate_pct",
            PRICING_DEFAULTS.get("founding_instructor_rate_pct", 0),
        )
        return cls._commission_rate_decimal(
            pricing_config.get("founding_instructor_rate_pct", fallback_rate),
            fallback=cls._commission_rate_decimal(fallback_rate),
        )

    @classmethod
    def _commission_tier_definitions(cls, pricing_config: Dict[str, Any]) -> List[TierDefinition]:
        configured = sorted(
            pricing_config.get("instructor_tiers", []), key=lambda tier: tier.get("min", 0)
        )
        default_tiers = sorted(
            DEFAULT_PRICING_CONFIG.get("instructor_tiers")
            or PRICING_DEFAULTS.get("instructor_tiers", []),
            key=lambda tier: tier.get("min", 0),
        )

        tier_defs: List[TierDefinition] = []
        tier_names = [("entry", "Entry"), ("growth", "Growth"), ("pro", "Pro")]
        for idx, (name, display_name) in enumerate(tier_names):
            fallback = (
                default_tiers[idx]
                if idx < len(default_tiers)
                else {"min": 0, "max": None, "pct": 0}
            )
            tier = configured[idx] if idx < len(configured) else fallback
            commission_rate = cls._commission_rate_decimal(
                tier.get("pct", fallback.get("pct", 0)),
                fallback=cls._commission_rate_decimal(fallback.get("pct", 0)),
            )
            min_lessons_raw = tier.get("min", fallback.get("min", 0))
            max_lessons_raw = tier.get("max", fallback.get("max"))
            try:
                min_lessons = int(min_lessons_raw)
            except (TypeError, ValueError):
                min_lessons = int(fallback.get("min", 0) or 0)
            try:
                max_lessons = int(max_lessons_raw) if max_lessons_raw is not None else None
            except (TypeError, ValueError):
                fallback_max = fallback.get("max")
                max_lessons = int(fallback_max) if fallback_max is not None else None

            tier_defs.append(
                {
                    "name": name,
                    "display_name": display_name,
                    "commission_rate": commission_rate,
                    "min_lessons": min_lessons,
                    "max_lessons": max_lessons,
                }
            )

        return tier_defs

    @classmethod
    def _resolve_persisted_tier_name(
        cls, instructor_profile: Optional[InstructorProfile], tier_defs: List[TierDefinition]
    ) -> str:
        if not tier_defs:
            return "entry"
        raw_pct = (
            getattr(instructor_profile, "current_tier_pct", None) if instructor_profile else None
        )
        if raw_pct is None:
            return "entry"
        try:
            current_rate = Decimal(str(raw_pct))
            if current_rate > 1:
                current_rate = current_rate / Decimal("100")
            current_rate = current_rate.quantize(Decimal("0.0001"))
        except (InvalidOperation, TypeError, ValueError):
            return "entry"

        for tier in tier_defs:
            tier_rate = tier["commission_rate"]
            if abs(current_rate - tier_rate) <= Decimal("0.0001"):
                return str(tier["name"])

        return "entry"

    @staticmethod
    def _tier_rate_for_name(tier_name: str, tier_defs: List[TierDefinition]) -> Decimal:
        for tier in tier_defs:
            if tier["name"] == tier_name:
                return tier["commission_rate"]
        if tier_defs:
            return tier_defs[0]["commission_rate"]
        return Decimal("0")

    @BaseService.measure_operation("pricing.update_instructor_tier")
    def update_instructor_tier(
        self, instructor_profile: InstructorProfile, new_tier_pct: float
    ) -> bool:
        """Update instructor's tier. Founding instructors are immune."""
        if getattr(instructor_profile, "is_founding_instructor", False):
            logger.info("Skipping tier update for founding instructor %s", instructor_profile.id)
            return False

        pct_value = Decimal(str(new_tier_pct))
        if pct_value <= 1:
            pct_value *= Decimal("100")
        instructor_profile.current_tier_pct = pct_value
        instructor_profile.last_tier_eval_at = datetime.now(timezone.utc)
        return True

    @BaseService.measure_operation("pricing.evaluate_and_persist_instructor_tier")
    def evaluate_and_persist_instructor_tier(
        self,
        *,
        instructor_user_id: str,
        instructor_profile: Optional[InstructorProfile] = None,
        pricing_config: Optional[Dict[str, Any]] = None,
        completion_stats: tuple[int, Optional[datetime]] | None = None,
    ) -> bool:
        resolved_config = pricing_config
        if resolved_config is None:
            resolved_config, _ = self.config_service.get_pricing_config()

        profile = instructor_profile
        if profile is None:
            profile = self._instructor_profile_repository.get_by_user_id(instructor_user_id)
        if profile is None:
            logger.warning(
                "Skipping tier evaluation; instructor profile missing for %s",
                instructor_user_id,
            )
            return False

        resolved_rate = self._resolve_instructor_tier_pct_for_instructor(
            instructor_user_id=instructor_user_id,
            instructor_profile=profile,
            pricing_config=resolved_config,
            completion_stats=completion_stats,
        )
        if not self._should_persist_tier_change(
            instructor_profile=profile,
            resolved_rate=resolved_rate,
            pricing_config=resolved_config,
        ):
            return False

        with self.transaction():
            self.update_instructor_tier(profile, float(resolved_rate))
        return True

    @BaseService.measure_operation("pricing.evaluate_active_instructor_tiers")
    def evaluate_active_instructor_tiers(self) -> TierEvaluationResults:
        pricing_config, _ = self.config_service.get_pricing_config()
        profiles = self._instructor_profile_repository.list_active_for_tier_evaluation()
        activity_window_days = int(pricing_config.get("tier_activity_window_days", 30))
        completion_stats_by_instructor = (
            self.booking_repository.get_instructor_completion_stats_in_window(
                [str(profile.user_id) for profile in profiles],
                activity_window_days,
            )
        )

        evaluated = 0
        updated = 0
        failed = 0
        for profile in profiles:
            evaluated += 1
            try:
                changed = self.evaluate_and_persist_instructor_tier(
                    instructor_user_id=str(profile.user_id),
                    instructor_profile=profile,
                    pricing_config=pricing_config,
                    completion_stats=completion_stats_by_instructor.get(
                        str(profile.user_id),
                        (0, None),
                    ),
                )
                if changed:
                    updated += 1
            except Exception as exc:
                failed += 1
                logger.error(
                    "Failed evaluating instructor tier for %s: %s",
                    getattr(profile, "user_id", None),
                    exc,
                )

        return {
            "evaluated": evaluated,
            "updated": updated,
            "failed": failed,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _default_instructor_tier_pct(pricing_config: Dict[str, Any]) -> Decimal:
        tiers = pricing_config.get("instructor_tiers")
        if not tiers:
            tiers = DEFAULT_PRICING_CONFIG.get("instructor_tiers", [])
        if tiers:
            entry_tier = min(tiers, key=lambda tier: tier.get("min", 0))
            pct = entry_tier.get("pct", 0)
            return Decimal(str(pct)).quantize(Decimal("0.0001"))
        # Fallback to the default config's entry tier (only used when no pricing config exists)
        default_tiers = DEFAULT_PRICING_CONFIG.get("instructor_tiers") or PRICING_DEFAULTS.get(
            "instructor_tiers", []
        )
        fallback_pct = default_tiers[0].get("pct", 0) if default_tiers else 0
        return Decimal(str(fallback_pct)).quantize(Decimal("0.0001"))

    @staticmethod
    def _build_line_items(
        *,
        student_fee_cents: int,
        credit_cents: int,
        student_fee_pct: Decimal,
    ) -> List[LineItemData]:
        label_pct = int(
            (student_fee_pct * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        items: List[LineItemData] = [
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
