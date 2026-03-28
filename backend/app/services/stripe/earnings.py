from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from importlib import import_module
import logging
import math
from typing import TYPE_CHECKING, Any, Optional

from ...constants.payment_status import map_payment_status
from ...constants.pricing_defaults import PRICING_DEFAULTS
from ...core.exceptions import ServiceException
from ...models.user import User
from ...repositories.factory import RepositoryFactory
from ...schemas.payment_schemas import (
    CreditBalanceResponse,
    EarningsResponse,
    InstructorInvoiceSummary,
    PayoutHistoryResponse,
    PayoutSummary,
    TransactionHistoryItem,
)
from ..base import BaseService
from ..config_service import ConfigService
from ..payment_summary_service import build_student_payment_summary

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...repositories.instructor_profile_repository import InstructorProfileRepository
    from ...repositories.payment_repository import PaymentRepository

logger = logging.getLogger(__name__)


def _stripe_service_module() -> Any:
    return import_module("app.services.stripe_service")


def _resolve_repository_factory() -> Any:
    facade_factory = getattr(_stripe_service_module(), "RepositoryFactory", RepositoryFactory)
    return facade_factory if facade_factory is not RepositoryFactory else RepositoryFactory


def _resolve_payment_summary_builder() -> Any:
    facade_builder = getattr(
        _stripe_service_module(),
        "build_student_payment_summary",
        build_student_payment_summary,
    )
    return (
        facade_builder
        if facade_builder is not build_student_payment_summary
        else build_student_payment_summary
    )


class StripeEarningsMixin(BaseService):
    """Instructor earnings, reports, payout history, and transaction history."""

    db: Session
    config_service: ConfigService
    instructor_repository: InstructorProfileRepository
    payment_repository: PaymentRepository

    def _money_to_cents(self, value: Optional[Any]) -> int:
        if value is None:
            return 0
        try:
            return int((Decimal(value) * Decimal("100")).quantize(Decimal("1")))
        except Exception:
            return 0

    def _compute_base_price_cents(self, hourly_rate: Any, duration_minutes: int) -> int:
        """Calculate base lesson price from hourly rate and duration."""
        try:
            rate = Decimal(str(hourly_rate or 0))
            cents_value = rate * Decimal(duration_minutes) * Decimal(100) / Decimal(60)
            return int(cents_value.quantize(Decimal("1")))
        except Exception:
            return 0

    def _get_instructor_tier_pct(self, config: dict[str, Any], instructor_profile: Any) -> float:
        """Get instructor's platform fee tier percentage."""
        is_founding = getattr(instructor_profile, "is_founding_instructor", False)
        if is_founding is True:
            default_rate = PRICING_DEFAULTS.get("founding_instructor_rate_pct", 0)
            raw_rate = config.get("founding_instructor_rate_pct", default_rate)
            try:
                return float(Decimal(str(raw_rate)))
            except Exception:
                return float(default_rate)

        tiers = config.get("instructor_tiers") or PRICING_DEFAULTS.get("instructor_tiers", [])
        if tiers:
            entry_tier = min(tiers, key=lambda tier: tier.get("min", 0))
            default_entry_pct = PRICING_DEFAULTS.get("instructor_tiers", [{}])[0].get("pct", 0)
            default_pct = float(entry_tier.get("pct", default_entry_pct))
        else:
            default_pct = float(PRICING_DEFAULTS.get("instructor_tiers", [{}])[0].get("pct", 0))

        raw_pct = getattr(instructor_profile, "current_tier_pct", None)
        if raw_pct is None:
            return default_pct
        try:
            pct_decimal = Decimal(str(raw_pct))
            if pct_decimal > 1:
                pct_decimal = pct_decimal / Decimal("100")
            return float(pct_decimal)
        except Exception:
            return default_pct

    def _load_earnings_summary_context(self, user: User) -> dict[str, Any]:
        profile = self.instructor_repository.get_by_user_id(user.id)
        if not profile:
            raise ServiceException("Instructor profile not found", code="not_found")

        pricing_config, _ = self.config_service.get_pricing_config()
        return {
            "profile": profile,
            "earnings": self.get_instructor_earnings(user.id),
            "pricing_config": pricing_config,
            "payment_repo": self.payment_repository,
            "tip_repo": _resolve_repository_factory().create_review_tip_repository(self.db),
            "instructor_payments": self.payment_repository.get_instructor_payment_history(
                instructor_id=user.id,
                limit=100,
            ),
        }

    def _build_instructor_invoice_summary(
        self,
        *,
        payment: Any,
        payment_repo: Any,
        pricing_config: dict[str, Any],
        tip_repo: Any,
        fallback_tier_pct: float,
        student_fee_pct: float,
    ) -> tuple[InstructorInvoiceSummary | None, int, int, int, int]:
        booking = payment.booking
        if not booking:
            return None, 0, 0, 0, 0

        minutes = int(getattr(booking, "duration_minutes", 0) or 0)
        student = getattr(booking, "student", None)
        student_name = None
        if student:
            last_initial = (student.last_name or "").strip()[:1]
            student_name = (
                f"{student.first_name} {last_initial}." if last_initial else student.first_name
            )

        try:
            summary = _resolve_payment_summary_builder()(
                booking=booking,
                pricing_config=pricing_config,
                payment_repo=payment_repo,
                review_tip_repo=tip_repo,
            )
        except Exception:
            summary = None

        total_paid_cents = int(payment.amount or 0)
        tip_cents = self._money_to_cents(summary.tip_paid if summary else None)
        lesson_price_cents = (
            payment.base_price_cents
            if payment.base_price_cents is not None
            else self._compute_base_price_cents(booking.hourly_rate, minutes)
        )
        actual_tier_pct = (
            float(payment.instructor_tier_pct)
            if payment.instructor_tier_pct is not None
            else fallback_tier_pct
        )
        instructor_share_cents = (
            payment.instructor_payout_cents
            if payment.instructor_payout_cents is not None
            else max(0, int(payment.amount or 0) - int(payment.application_fee or 0))
        )
        platform_fee_cents = math.ceil(Decimal(lesson_price_cents) * Decimal(str(actual_tier_pct)))
        student_fee_cents = int(Decimal(lesson_price_cents) * Decimal(str(student_fee_pct)))
        invoice = InstructorInvoiceSummary(
            booking_id=booking.id,
            lesson_date=booking.booking_date,
            start_time=booking.start_time,
            service_name=booking.service_name,
            student_name=student_name,
            duration_minutes=minutes or None,
            total_paid_cents=total_paid_cents,
            tip_cents=tip_cents,
            instructor_share_cents=instructor_share_cents,
            status=map_payment_status(payment.status),
            created_at=payment.created_at,
            lesson_price_cents=lesson_price_cents,
            platform_fee_cents=platform_fee_cents,
            platform_fee_rate=actual_tier_pct,
            student_fee_cents=student_fee_cents,
        )
        return invoice, minutes, lesson_price_cents, platform_fee_cents, tip_cents

    @BaseService.measure_operation("stripe_get_instructor_earnings_summary")
    def get_instructor_earnings_summary(self, *, user: User) -> EarningsResponse:
        """Aggregate instructor earnings summary and invoice list."""
        context = self._load_earnings_summary_context(user)
        pricing_config = context["pricing_config"]
        profile = context["profile"]
        fallback_tier_pct = self._get_instructor_tier_pct(pricing_config, profile)
        student_fee_pct = float(
            pricing_config.get("student_fee_pct", PRICING_DEFAULTS["student_fee_pct"])
        )

        invoices: list[InstructorInvoiceSummary] = []
        total_minutes = 0
        total_lesson_value = 0
        total_platform_fees = 0
        total_tips = 0

        for payment in context["instructor_payments"]:
            (
                invoice,
                minutes,
                lesson_price_cents,
                platform_fee_cents,
                tip_cents,
            ) = self._build_instructor_invoice_summary(
                payment=payment,
                payment_repo=context["payment_repo"],
                pricing_config=pricing_config,
                tip_repo=context["tip_repo"],
                fallback_tier_pct=fallback_tier_pct,
                student_fee_pct=student_fee_pct,
            )
            if invoice is None:
                continue
            invoices.append(invoice)
            total_minutes += minutes
            total_lesson_value += lesson_price_cents
            total_platform_fees += platform_fee_cents
            total_tips += tip_cents

        earnings = context["earnings"]
        return EarningsResponse(
            total_earned=earnings.get("total_earned"),
            total_fees=earnings.get("total_fees"),
            booking_count=earnings.get("booking_count"),
            average_earning=earnings.get("average_earning"),
            hours_invoiced=(total_minutes / 60.0) if total_minutes else 0.0,
            service_count=len(context["instructor_payments"]),
            period_start=earnings.get("period_start"),
            period_end=earnings.get("period_end"),
            invoices=invoices,
            total_lesson_value=total_lesson_value,
            total_platform_fees=total_platform_fees,
            total_tips=total_tips,
        )

    @BaseService.measure_operation("stripe_get_instructor_payout_history")
    def get_instructor_payout_history(
        self, *, user: User, limit: int = 50
    ) -> PayoutHistoryResponse:
        """Get payout history for an instructor."""
        profile = self.instructor_repository.get_by_user_id(user.id)
        if not profile:
            raise ServiceException("Instructor profile not found", code="not_found")

        payout_events = self.payment_repository.get_instructor_payout_history(
            instructor_profile_id=profile.id,
            limit=limit,
        )
        payouts: list[PayoutSummary] = []
        total_paid_cents = 0
        total_pending_cents = 0
        for event in payout_events:
            amount_cents = event.amount_cents or 0
            payout_status = event.status or "unknown"
            if payout_status == "paid":
                total_paid_cents += amount_cents
            elif payout_status in ("pending", "in_transit"):
                total_pending_cents += amount_cents
            payouts.append(
                PayoutSummary(
                    id=event.payout_id,
                    amount_cents=amount_cents,
                    status=payout_status,
                    arrival_date=event.arrival_date,
                    failure_code=event.failure_code,
                    failure_message=event.failure_message,
                    created_at=event.created_at,
                )
            )
        return PayoutHistoryResponse(
            payouts=payouts,
            total_paid_cents=total_paid_cents,
            total_pending_cents=total_pending_cents,
            payout_count=len(payouts),
        )

    @BaseService.measure_operation("stripe_get_user_transaction_history")
    def get_user_transaction_history(
        self, *, user: User, limit: int = 20, offset: int = 0
    ) -> list[TransactionHistoryItem]:
        """Return transaction history for a user."""
        fetch_limit = max(limit + offset + 10, limit)
        payment_repo = self.payment_repository
        transactions = payment_repo.get_user_payment_history(
            user_id=user.id, limit=fetch_limit, offset=0
        )
        payment_summary_builder = _resolve_payment_summary_builder()
        tip_repo = _resolve_repository_factory().create_review_tip_repository(self.db)
        pricing_config, _ = self.config_service.get_pricing_config()

        result: list[TransactionHistoryItem] = []
        seen_bookings: set[str] = set()
        for payment in transactions:
            booking = payment.booking
            if not booking or booking.id in seen_bookings:
                continue
            seen_bookings.add(booking.id)
            try:
                summary = payment_summary_builder(
                    booking=booking,
                    pricing_config=pricing_config,
                    payment_repo=payment_repo,
                    review_tip_repo=tip_repo,
                )
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
                continue

            instructor = booking.instructor
            instructor_name = "Instructor"
            if instructor and instructor.last_name:
                instructor_name = f"{instructor.first_name} {instructor.last_name[0]}."
            elif instructor and instructor.first_name:
                instructor_name = instructor.first_name
            result.append(
                TransactionHistoryItem(
                    id=payment.id,
                    booking_id=booking.id,
                    service_name=booking.service_name,
                    instructor_name=instructor_name,
                    booking_date=booking.booking_date.isoformat(),
                    start_time=booking.start_time.isoformat(),
                    end_time=booking.end_time.isoformat(),
                    duration_minutes=booking.duration_minutes,
                    hourly_rate=float(booking.hourly_rate),
                    lesson_amount=summary.lesson_amount,
                    service_fee=summary.service_fee,
                    credit_applied=summary.credit_applied,
                    tip_amount=summary.tip_amount,
                    tip_paid=summary.tip_paid,
                    tip_status=summary.tip_status,
                    total_paid=summary.total_paid,
                    status=payment.status,
                    created_at=payment.created_at.isoformat(),
                )
            )
            if len(result) >= offset + limit:
                break
        return result[offset : offset + limit]

    @BaseService.measure_operation("stripe_get_user_credit_balance")
    def get_user_credit_balance(self, *, user: User) -> CreditBalanceResponse:
        """Return credit balance for a user."""
        from ..credit_service import CreditService

        credit_service = CreditService(self.db)
        total_cents = credit_service.get_available_balance(user_id=user.id)
        reserved_cents = credit_service.get_reserved_balance(user_id=user.id)

        earliest_exp: str | None = None
        try:
            credits = credit_service.credit_repository.get_available_credits(user_id=user.id)
            expiries = [c.expires_at for c in credits if getattr(c, "expires_at", None) is not None]
            if expiries:
                earliest_exp = min(expiries).isoformat()
        except Exception:
            earliest_exp = None

        return CreditBalanceResponse(
            available=float(total_cents) / 100.0,
            expires_at=earliest_exp,
            pending=float(reserved_cents) / 100.0,
        )

    @BaseService.measure_operation("stripe_get_platform_revenue_stats")
    def get_platform_revenue_stats(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> dict[str, Any]:
        """Get platform revenue statistics."""
        try:
            return dict(self.payment_repository.get_platform_revenue_stats(start_date, end_date))
        except Exception as exc:
            self.logger.error("Error getting platform revenue stats: %s", exc)
            raise ServiceException(f"Failed to get revenue stats: {str(exc)}")

    @BaseService.measure_operation("stripe_get_instructor_earnings")
    def get_instructor_earnings(
        self,
        instructor_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Get instructor earnings statistics."""
        try:
            return dict(
                self.payment_repository.get_instructor_earnings(instructor_id, start_date, end_date)
            )
        except Exception as exc:
            self.logger.error("Error getting instructor earnings: %s", exc)
            raise ServiceException(f"Failed to get instructor earnings: {str(exc)}")
