"""Service for MCP Admin Operations - bookings, payments, and user support."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import logging
import re
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.payment import PaymentEvent
from app.repositories.admin_ops_repository import AdminOpsRepository
from app.repositories.factory import RepositoryFactory

from .base import BaseService

logger = logging.getLogger(__name__)

DOUBLE_CHARGE_WINDOW_MINUTES = 5
PAYMENT_TIMELINE_STATUSES = {
    "scheduled",
    "authorized",
    "captured",
    "settled",
    "failed",
    "refunded",
    "locked",
}

_STRIPE_REF_KEYS: dict[str, str] = {
    "payment_intent_id": "payment_intent",
    "stripe_payment_intent_id": "payment_intent",
    "charge_id": "charge",
    "refund_id": "refund",
}

_FAILURE_HINTS = {
    "card_declined": ("declined", "card was declined", "do_not_honor"),
    "insufficient_funds": ("insufficient funds", "insufficient"),
    "expired_card": ("expired card", "expired"),
    "incorrect_cvc": ("cvc", "cvv", "security code"),
    "processing_error": ("processing error", "api_error"),
}

_FAILURE_CATEGORY_RE = re.compile(r"^[a-z0-9_]+$")


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _redact_stripe_id(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    last4 = cleaned[-4:] if len(cleaned) > 4 else cleaned
    prefix = cleaned.split("_", 1)[0] if "_" in cleaned else ""
    if prefix:
        return f"{prefix}_...{last4}"
    return f"...{last4}" if len(cleaned) > 4 else last4


def _extract_amount_cents(event_data: dict[str, Any]) -> Optional[int]:
    for key in (
        "amount_cents",
        "amount_captured_cents",
        "amount_received",
        "amount_refunded",
        "refund_amount_cents",
        "refunded_cents",
    ):
        amount = _coerce_int(event_data.get(key))
        if amount is not None:
            return amount
    return None


def _infer_failure_category(event_type: str, event_data: dict[str, Any]) -> Optional[str]:
    for key in ("error_type", "error_code", "failure_reason"):
        value = event_data.get(key)
        if isinstance(value, str) and value.strip():
            normalized = value.strip().lower()
            if _FAILURE_CATEGORY_RE.match(normalized):
                return normalized
            for category, hints in _FAILURE_HINTS.items():
                if any(hint in normalized for hint in hints):
                    return category

    error_text = event_data.get("error")
    if isinstance(error_text, str) and error_text.strip():
        lowered = error_text.strip().lower()
        for category, hints in _FAILURE_HINTS.items():
            if any(hint in lowered for hint in hints):
                return category
        return "unknown_error"

    if "fail" in event_type.lower():
        return "unknown_error"
    return None


def _is_successful_charge(event_type: str) -> bool:
    lowered = event_type.lower()
    if "fail" in lowered or "skipped" in lowered or "already_done" in lowered:
        return False
    if "captured" in lowered:
        return True
    if lowered == "reauth_and_capture_success" or "capture_success" in lowered:
        return True
    return False


class AdminOpsService(BaseService):
    """Service for admin operations via MCP - bookings, payments, user support."""

    VALID_PERIODS = {"today", "yesterday", "this_week", "last_7_days", "this_month"}
    MAX_RECENT_BOOKINGS_LIMIT = 100
    MAX_RECENT_BOOKINGS_HOURS = 168  # 1 week
    MAX_PAYOUTS_LIMIT = 100
    MAX_USER_BOOKINGS_LIMIT = 100

    def __init__(self, db: Session) -> None:
        """Initialize the service."""
        super().__init__(db)
        self.repository = AdminOpsRepository(db)
        self.payment_repository = RepositoryFactory.create_payment_repository(db)

    @staticmethod
    def _format_privacy_name(first_name: str | None, last_name: str | None) -> str:
        """Format name as 'FirstName L.' for privacy."""
        if not first_name:
            return "Unknown"
        name = first_name.strip()
        if last_name and last_name.strip():
            name += f" {last_name.strip()[0].upper()}."
        return name

    @staticmethod
    def _get_period_dates(period: str) -> tuple[date, date]:
        """Get start and end dates for a period string."""
        if period not in AdminOpsService.VALID_PERIODS:
            raise ValueError(
                f"Invalid period: {period}. Valid options: {AdminOpsService.VALID_PERIODS}"
            )

        today = datetime.now(timezone.utc).date()

        if period == "today":
            return today, today
        elif period == "yesterday":
            yesterday = today - timedelta(days=1)
            return yesterday, yesterday
        elif period == "this_week":
            # Monday to today
            start = today - timedelta(days=today.weekday())
            return start, today
        elif period == "last_7_days":
            start = today - timedelta(days=6)
            return start, today
        elif period == "this_month":
            start = today.replace(day=1)
            return start, today
        else:
            # Default to today
            return today, today

    # ==================== Booking Summary ====================

    def _query_booking_summary(self, start_date: date, end_date: date) -> dict[str, Any]:
        """Query booking summary data for a date range."""
        # Get all bookings in range using repository
        bookings = self.repository.get_bookings_in_date_range_with_service(start_date, end_date)

        # Count by status
        by_status: dict[str, int] = {}
        total_revenue_cents = 0

        for booking in bookings:
            status = booking.status or "unknown"
            by_status[status] = by_status.get(status, 0) + 1
            # Only count revenue for completed/confirmed bookings
            if status in (BookingStatus.COMPLETED.value, BookingStatus.CONFIRMED.value):
                if booking.total_price:
                    total_revenue_cents += int(booking.total_price * 100)

        total_bookings = len(bookings)
        avg_booking_value_cents = total_revenue_cents // total_bookings if total_bookings > 0 else 0

        # Count new vs repeat students
        student_ids = [b.student_id for b in bookings if b.student_id]
        unique_students = set(student_ids)

        # A "new" student is one whose first booking is in this period
        first_booking_dates = self.repository.get_first_booking_dates_for_students(
            list(unique_students)
        )

        new_students = 0
        repeat_students = 0

        for student_id in unique_students:
            first_booking_date = first_booking_dates.get(str(student_id))
            if first_booking_date and first_booking_date >= start_date:
                new_students += 1
            else:
                repeat_students += 1

        # Get top categories (instructor_service.category is a property that returns str)
        category_counts: dict[str, int] = {}
        for booking in bookings:
            if booking.instructor_service:
                cat = booking.instructor_service.category
                if cat:
                    category_counts[cat] = category_counts.get(cat, 0) + 1

        top_categories_list: list[dict[str, Any]] = [
            {"category": k, "count": v} for k, v in category_counts.items()
        ]
        top_categories = sorted(
            top_categories_list,
            key=lambda x: int(x["count"]),
            reverse=True,
        )[:5]

        return {
            "total_bookings": total_bookings,
            "by_status": by_status,
            "total_revenue_cents": total_revenue_cents,
            "avg_booking_value_cents": avg_booking_value_cents,
            "new_students": new_students,
            "repeat_students": repeat_students,
            "top_categories": top_categories,
        }

    @BaseService.measure_operation("get_booking_summary")
    async def get_booking_summary(
        self,
        period: str | None = "today",
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        period_label: str | None = None,
    ) -> dict[str, Any]:
        """Get booking summary for a time period or explicit date range."""
        now = datetime.now(timezone.utc)

        if start_date or end_date:
            if not start_date or not end_date:
                raise ValueError("start_date and end_date must be provided together")
            query_start = start_date
            query_end = end_date
            period_value = period_label or "custom_range"
        else:
            period_value = period or "today"
            query_start, query_end = self._get_period_dates(period_value)

        result = await asyncio.to_thread(self._query_booking_summary, query_start, query_end)

        return {
            "summary": {
                "period": period_value,
                **result,
            },
            "checked_at": now,
        }

    # ==================== Recent Bookings ====================

    def _query_recent_bookings(
        self,
        status: str | None,
        limit: int,
        hours: int,
    ) -> list[dict[str, Any]]:
        """Query recent bookings with optional filters."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        bookings = self.repository.get_recent_bookings_with_details(
            cutoff=cutoff,
            status=status,
            limit=limit,
        )

        result = []
        for b in bookings:
            # Get category name safely (instructor_service.category is a property that returns str)
            category = ""
            if b.instructor_service:
                category = b.instructor_service.category or ""

            result.append(
                {
                    "booking_id": b.id,
                    "status": b.status or "unknown",
                    "booking_date": str(b.booking_date) if b.booking_date else "",
                    "start_time": str(b.start_time) if b.start_time else "",
                    "end_time": str(b.end_time) if b.end_time else "",
                    "student_name": self._format_privacy_name(
                        b.student.first_name if b.student else None,
                        b.student.last_name if b.student else None,
                    ),
                    "instructor_name": self._format_privacy_name(
                        b.instructor.first_name if b.instructor else None,
                        b.instructor.last_name if b.instructor else None,
                    ),
                    "service_name": b.service_name or "",
                    "category": category,
                    "total_cents": int(b.total_price * 100) if b.total_price else 0,
                    "location_type": b.location_type or "",
                    "created_at": b.created_at.isoformat() if b.created_at else "",
                }
            )

        return result

    @BaseService.measure_operation("get_recent_bookings")
    async def get_recent_bookings(
        self,
        status: str | None = None,
        limit: int = 20,
        hours: int = 24,
    ) -> dict[str, Any]:
        """Get recent bookings with optional filters."""
        now = datetime.now(timezone.utc)

        # Cap parameters
        effective_limit = min(limit, self.MAX_RECENT_BOOKINGS_LIMIT)
        effective_hours = min(hours, self.MAX_RECENT_BOOKINGS_HOURS)

        bookings = await asyncio.to_thread(
            self._query_recent_bookings, status, effective_limit, effective_hours
        )

        return {
            "bookings": bookings,
            "count": len(bookings),
            "filters_applied": {
                "status": status,
                "limit": effective_limit,
                "hours": effective_hours,
            },
            "checked_at": now,
        }

    # ==================== Payment Pipeline ====================

    def _query_payment_pipeline(self) -> dict[str, Any]:
        """Query payment pipeline status."""
        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)
        cutoff_24h = now + timedelta(hours=24)

        # Current state counts using repository methods
        pending_authorization = self.repository.count_bookings_by_payment_and_status(
            payment_status=PaymentStatus.SCHEDULED.value,
            booking_status=BookingStatus.CONFIRMED.value,
        )

        authorized = self.repository.count_bookings_by_payment_and_status(
            payment_status=PaymentStatus.AUTHORIZED.value,
            booking_status=BookingStatus.CONFIRMED.value,
        )

        pending_capture = self.repository.count_bookings_by_payment_and_status(
            payment_status=PaymentStatus.AUTHORIZED.value,
            booking_status=BookingStatus.COMPLETED.value,
        )

        # Captured in last 7 days
        captured = self.repository.count_bookings_by_payment_and_status(
            payment_status=PaymentStatus.SETTLED.value,
            updated_since=seven_days_ago,
        )

        # Failed in last 7 days
        failed = self.repository.count_failed_payments(updated_since=seven_days_ago)

        # Refunded in last 7 days
        refunded = self.repository.count_refunded_bookings(updated_since=seven_days_ago)

        # Alerts: overdue authorizations
        overdue_authorizations = self.repository.count_overdue_authorizations(
            cutoff_time=cutoff_24h
        )

        # Overdue captures (completed > 24h ago but still authorized)
        completed_24h_ago = now - timedelta(hours=24)
        overdue_captures = self.repository.count_overdue_captures(
            completed_before=completed_24h_ago
        )

        # Revenue calculations (last 7 days)
        captured_sum = self.repository.sum_captured_amount(updated_since=seven_days_ago)
        total_captured_cents = int(captured_sum * 100) if captured_sum else 0

        # Sum actual platform fees from settled bookings in last 7 days
        platform_fees_cents = self.repository.sum_platform_fees(seven_days_ago.date(), now.date())
        instructor_payouts_cents = total_captured_cents - platform_fees_cents

        # Refunded amount estimate (would need more specific tracking)
        total_refunded_cents = 0  # Simplified - would need settlement tracking

        return {
            "pending_authorization": pending_authorization,
            "authorized": authorized,
            "pending_capture": pending_capture,
            "captured": captured,
            "failed": failed,
            "refunded": refunded,
            "overdue_authorizations": overdue_authorizations,
            "overdue_captures": overdue_captures,
            "total_captured_cents": total_captured_cents,
            "total_refunded_cents": total_refunded_cents,
            "net_revenue_cents": total_captured_cents - total_refunded_cents,
            "platform_fees_cents": platform_fees_cents,
            "instructor_payouts_cents": instructor_payouts_cents,
        }

    @BaseService.measure_operation("get_payment_pipeline")
    async def get_payment_pipeline(self) -> dict[str, Any]:
        """Get payment pipeline status."""
        now = datetime.now(timezone.utc)

        result = await asyncio.to_thread(self._query_payment_pipeline)

        return {
            **result,
            "checked_at": now,
        }

    # ==================== Pending Payouts ====================

    def _query_pending_payouts(self, limit: int) -> list[dict[str, Any]]:
        """Query instructors with pending payouts."""
        results = self.repository.get_instructors_with_pending_payouts(limit=limit)

        payouts = []
        for user, pending_amount, lesson_count, oldest_date in results:
            stripe_connected = False
            if user.instructor_profile and user.instructor_profile.stripe_connected_account:
                stripe_connected = bool(
                    user.instructor_profile.stripe_connected_account.onboarding_completed
                )

            payouts.append(
                {
                    "instructor_id": user.id,
                    "instructor_name": self._format_privacy_name(user.first_name, user.last_name),
                    "pending_amount_cents": int(pending_amount * 100) if pending_amount else 0,
                    "completed_lessons": lesson_count or 0,
                    "oldest_pending_date": oldest_date.isoformat() if oldest_date else "",
                    "stripe_connected": stripe_connected,
                }
            )

        return payouts

    @BaseService.measure_operation("get_pending_payouts")
    async def get_pending_payouts(self, limit: int = 20) -> dict[str, Any]:
        """Get instructors with pending payouts."""
        now = datetime.now(timezone.utc)
        effective_limit = min(limit, self.MAX_PAYOUTS_LIMIT)

        payouts = await asyncio.to_thread(self._query_pending_payouts, effective_limit)

        total_pending_cents = sum(p["pending_amount_cents"] for p in payouts)

        return {
            "payouts": payouts,
            "total_pending_cents": total_pending_cents,
            "instructor_count": len(payouts),
            "checked_at": now,
        }

    # ==================== User Lookup ====================

    def _query_user_lookup(self, identifier: str) -> dict[str, Any] | None:
        """Look up a user by email, phone, or ID."""
        user = None

        # Try email first
        if "@" in identifier:
            user = self.repository.get_user_by_email_with_profile(identifier)
        # Try phone (starts with + or is numeric)
        elif identifier.startswith("+") or identifier.replace("-", "").replace(" ", "").isdigit():
            user = self.repository.get_user_by_phone_with_profile(identifier)
        # Try user ID (ULID is 26 chars)
        else:
            user = self.repository.get_user_by_id_with_profile(identifier)

        if not user:
            return None

        # Determine role
        role = "student"
        if user.instructor_profile:
            role = "instructor"

        # Get booking stats using repository
        total_bookings = self.repository.count_student_bookings(user.id)
        total_spent = self.repository.sum_student_spent(user.id)
        total_spent_cents = int(total_spent * 100) if total_spent else 0

        # Get stripe customer ID through relationship
        stripe_customer_id = None
        if user.stripe_customer:
            stripe_customer_id = user.stripe_customer.stripe_customer_id

        result = {
            "user_id": user.id,
            "email": user.email or "",
            "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
            "role": role,
            "created_at": user.created_at.isoformat() if user.created_at else "",
            "last_login": None,  # Not tracked in User model
            "is_verified": bool(user.is_active),  # Use is_active as proxy for verified
            "is_founding": False,
            "total_bookings": total_bookings,
            "total_spent_cents": total_spent_cents,
            "stripe_customer_id": stripe_customer_id,
            "phone": user.phone,
        }

        # Add instructor-specific fields
        if user.instructor_profile:
            profile = user.instructor_profile
            result["is_founding"] = bool(profile.is_founding_instructor)
            result["instructor_status"] = "live" if profile.is_live else "onboarding"

            # Total lessons taught using repository
            total_lessons = self.repository.count_instructor_completed_lessons(user.id)
            result["total_lessons"] = total_lessons

            # Total earned using repository
            total_earned = self.repository.sum_instructor_earned(user.id)
            # Deduct platform fee (use current tier or estimate)
            tier_pct = float(profile.current_tier_pct or 15)
            instructor_cut = 1 - (tier_pct / 100)
            result["total_earned_cents"] = (
                int(total_earned * 100 * instructor_cut) if total_earned else 0
            )

            # Rating info - would need review query
            result["rating"] = None
            result["review_count"] = 0

            # Stripe account
            if profile.stripe_connected_account:
                result["stripe_account_id"] = profile.stripe_connected_account.stripe_account_id

        return result

    @BaseService.measure_operation("lookup_user")
    async def lookup_user(self, identifier: str) -> dict[str, Any]:
        """Look up a user by email, phone, or ID."""
        now = datetime.now(timezone.utc)

        user = await asyncio.to_thread(self._query_user_lookup, identifier)

        return {
            "found": user is not None,
            "user": user,
            "checked_at": now,
        }

    # ==================== User Booking History ====================

    def _query_user_booking_history(
        self, user_id: str, limit: int
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """Query a user's booking history."""
        user = self.repository.get_user_with_instructor_profile(user_id)

        if not user:
            return None, []

        # Determine role
        role = "instructor" if user.instructor_profile else "student"
        is_instructor = role == "instructor"

        # Get bookings using repository
        bookings = self.repository.get_user_booking_history(
            user_id=user_id,
            is_instructor=is_instructor,
            limit=limit,
        )

        result = []
        for b in bookings:
            # Get category name safely (instructor_service.category is a property that returns str)
            category = ""
            if b.instructor_service:
                category = b.instructor_service.category or ""

            result.append(
                {
                    "booking_id": b.id,
                    "status": b.status or "unknown",
                    "booking_date": str(b.booking_date) if b.booking_date else "",
                    "start_time": str(b.start_time) if b.start_time else "",
                    "end_time": str(b.end_time) if b.end_time else "",
                    "student_name": self._format_privacy_name(
                        b.student.first_name if b.student else None,
                        b.student.last_name if b.student else None,
                    ),
                    "instructor_name": self._format_privacy_name(
                        b.instructor.first_name if b.instructor else None,
                        b.instructor.last_name if b.instructor else None,
                    ),
                    "service_name": b.service_name or "",
                    "category": category,
                    "total_cents": int(b.total_price * 100) if b.total_price else 0,
                    "location_type": b.location_type or "",
                    "created_at": b.created_at.isoformat() if b.created_at else "",
                }
            )

        user_info = {
            "user_id": user.id,
            "user_name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
            "user_role": role,
        }

        return user_info, result

    @BaseService.measure_operation("get_user_booking_history")
    async def get_user_booking_history(self, user_id: str, limit: int = 20) -> dict[str, Any]:
        """Get a user's booking history."""
        now = datetime.now(timezone.utc)
        effective_limit = min(limit, self.MAX_USER_BOOKINGS_LIMIT)

        user_info, bookings = await asyncio.to_thread(
            self._query_user_booking_history, user_id, effective_limit
        )

        if not user_info:
            return {
                "user_id": user_id,
                "user_name": "",
                "user_role": "",
                "bookings": [],
                "total_count": 0,
                "checked_at": now,
            }

        return {
            **user_info,
            "bookings": bookings,
            "total_count": len(bookings),
            "checked_at": now,
        }

    # ==================== Payment Timeline ====================

    def _resolve_credits_applied_cents(self, events: Sequence[PaymentEvent]) -> int:
        credit_cents = 0
        for event in events:
            data = event.event_data or {}
            if event.event_type == "credits_applied":
                credit_cents = int(data.get("applied_cents", 0) or 0)
            elif credit_cents == 0 and event.event_type in {
                "auth_succeeded_credits_only",
                "auth_succeeded",
                "auth_retry_succeeded",
            }:
                credit_cents = int(
                    data.get(
                        "credits_applied_cents",
                        data.get("applied_credit_cents", data.get("original_amount_cents", 0)),
                    )
                    or 0
                )
        return max(0, credit_cents)

    def _resolve_gross_cents(self, booking: Booking, credits_applied_cents: int) -> int:
        if booking.payment_intent and booking.payment_intent.amount is not None:
            return int(booking.payment_intent.amount) + credits_applied_cents
        if booking.total_price is None:
            return credits_applied_cents
        try:
            return int((Decimal(str(booking.total_price)) * 100).quantize(Decimal("1")))
        except Exception:
            return credits_applied_cents

    def _resolve_platform_fee_cents(self, booking: Booking) -> int:
        payment_intent = booking.payment_intent
        if payment_intent and payment_intent.application_fee is not None:
            return int(payment_intent.application_fee)
        return 0

    def _resolve_instructor_payout_cents(self, booking: Booking, platform_fee_cents: int) -> int:
        payment_intent = booking.payment_intent
        if payment_intent and payment_intent.instructor_payout_cents is not None:
            return int(payment_intent.instructor_payout_cents)
        if payment_intent and payment_intent.amount is not None:
            return max(0, int(payment_intent.amount) - platform_fee_cents)
        return 0

    def _build_amounts(self, booking: Booking, credits_applied_cents: int) -> dict[str, float]:
        gross_cents = self._resolve_gross_cents(booking, credits_applied_cents)
        platform_fee_cents = self._resolve_platform_fee_cents(booking)
        instructor_payout_cents = self._resolve_instructor_payout_cents(booking, platform_fee_cents)
        return {
            "gross": round(gross_cents / 100.0, 2),
            "platform_fee": round(platform_fee_cents / 100.0, 2),
            "credits_applied": round(credits_applied_cents / 100.0, 2),
            "tip": 0.0,
            "net_to_instructor": round(instructor_payout_cents / 100.0, 2),
        }

    def _map_event_state(self, event_type: str) -> Optional[str]:
        lowered = event_type.lower()
        if "auth" in lowered and "failed" in lowered:
            return "authorization_failed"
        if "auth" in lowered and "succeeded" in lowered:
            return "authorized"
        if "auth" in lowered and ("scheduled" in lowered or "attempt" in lowered):
            return "scheduled"
        if "capture" in lowered and "failed" in lowered:
            return "capture_failed"
        if "captured" in lowered or "capture_success" in lowered:
            return "captured"
        if "refund" in lowered and "failed" in lowered:
            return "refund_failed"
        if "refund" in lowered:
            return "refunded"
        return None

    def _build_status_timeline(
        self, booking: Booking, events: Sequence[PaymentEvent]
    ) -> list[dict[str, Any]]:
        timeline: list[dict[str, Any]] = []
        seen: set[str] = set()
        for event in events:
            state = self._map_event_state(event.event_type)
            if not state or state in seen:
                continue
            ts = _ensure_utc(event.created_at) if event.created_at else datetime.now(timezone.utc)
            timeline.append({"ts": ts, "state": state})
            seen.add(state)

        pd = booking.payment_detail
        if (pd.auth_scheduled_for if pd else None) and "scheduled" not in seen:
            timeline.append({"ts": _ensure_utc(pd.auth_scheduled_for), "state": "scheduled"})
            seen.add("scheduled")

        pd_payment_status = pd.payment_status if pd else None
        if (
            pd_payment_status
            and pd_payment_status.lower() == PaymentStatus.AUTHORIZED.value
            and "authorized" not in seen
        ):
            ts = (
                (pd.auth_attempted_at if pd else None)
                or booking.updated_at
                or datetime.now(timezone.utc)
            )
            timeline.append({"ts": _ensure_utc(ts), "state": "authorized"})
            seen.add("authorized")

        if pd_payment_status and pd_payment_status.lower() in {"settled", "refunded"}:
            if "settled" not in seen:
                ts = booking.updated_at or booking.completed_at or datetime.now(timezone.utc)
                timeline.append({"ts": _ensure_utc(ts), "state": "settled"})
        timeline.sort(key=lambda item: item["ts"])
        return timeline

    def _resolve_scheduled_capture_at(self, booking: Booking) -> datetime | None:
        if not booking.booking_start_utc or booking.duration_minutes is None:
            return None
        start = _ensure_utc(booking.booking_start_utc)
        duration_minutes = int(booking.duration_minutes)
        return start + timedelta(minutes=duration_minutes) + timedelta(hours=24)

    def _resolve_scheduled_authorize_at(self, booking: Booking) -> datetime | None:
        if not booking.booking_start_utc or booking.duration_minutes is None:
            return None
        return _ensure_utc(booking.booking_start_utc) - timedelta(hours=24)

    def _normalize_payment_status(
        self,
        booking: Booking,
        status_timeline: list[dict[str, Any]],
        failure: Optional[dict[str, Any]],
    ) -> str:
        pd = booking.payment_detail
        _ps = pd.payment_status if pd else None
        raw_status = str(_ps).lower() if _ps else ""
        last_state: str | None = None
        if status_timeline:
            state_value = status_timeline[-1].get("state")
            if isinstance(state_value, str):
                last_state = state_value
        if raw_status in {"settled", "locked"}:
            return raw_status

        if last_state in {"authorization_failed", "capture_failed", "refund_failed"}:
            return "failed"
        if last_state in {"refunded", "captured", "authorized", "scheduled", "settled"}:
            if last_state in {"refunded", "captured"}:
                return last_state
            if raw_status in PAYMENT_TIMELINE_STATUSES:
                return raw_status
            return last_state
        if raw_status in PAYMENT_TIMELINE_STATUSES:
            return raw_status
        if failure:
            return "failed"
        return raw_status or (last_state or "unknown")

    def _build_provider_refs(
        self, booking: Booking, events: Sequence[PaymentEvent]
    ) -> dict[str, str]:
        refs: dict[str, str] = {}
        pd = booking.payment_detail
        pd_intent_id = pd.payment_intent_id if pd else None
        if pd_intent_id:
            redacted = _redact_stripe_id(pd_intent_id)
            if redacted:
                refs["payment_intent"] = redacted

        for event in events:
            data = event.event_data or {}
            for key, kind in _STRIPE_REF_KEYS.items():
                if kind in refs:
                    continue
                redacted = _redact_stripe_id(data.get(key))
                if redacted:
                    refs[kind] = redacted
        return refs

    def _build_failure(self, events: Sequence[PaymentEvent]) -> Optional[dict[str, Any]]:
        for event in reversed(list(events)):
            data = event.event_data or {}
            category = _infer_failure_category(event.event_type, data)
            if not category:
                continue
            ts = _ensure_utc(event.created_at) if event.created_at else datetime.now(timezone.utc)
            return {"category": category, "last_failed_at": ts}
        return None

    def _build_refunds(self, events: Sequence[PaymentEvent]) -> list[dict[str, Any]]:
        refunds: list[dict[str, Any]] = []
        for event in events:
            if "refund" not in event.event_type.lower():
                continue
            data = event.event_data or {}
            status = "pending"
            lowered = event.event_type.lower()
            if "failed" in lowered:
                status = "failed"
            elif "refunded" in lowered:
                status = "succeeded"
            refund_id = _redact_stripe_id(data.get("refund_id"))
            amount_cents = _coerce_int(data.get("amount_refunded"))
            if amount_cents is None:
                amount_cents = _coerce_int(data.get("refund_amount_cents"))
            ts = _ensure_utc(event.created_at) if event.created_at else None
            refunds.append(
                {
                    "refund_id": refund_id,
                    "amount": round((amount_cents or 0) / 100.0, 2) if amount_cents else None,
                    "status": status,
                    "created_at": ts,
                }
            )
        return refunds

    def _detect_double_charge(self, grouped_events: dict[str, list[PaymentEvent]]) -> bool:
        window = timedelta(minutes=DOUBLE_CHARGE_WINDOW_MINUTES)
        captures: list[tuple[datetime, int]] = []
        for events in grouped_events.values():
            for event in events:
                if not _is_successful_charge(event.event_type):
                    continue
                data = event.event_data or {}
                amount_cents = _extract_amount_cents(data)
                if amount_cents is None:
                    continue
                ts = (
                    _ensure_utc(event.created_at)
                    if event.created_at
                    else datetime.now(timezone.utc)
                )
                captures.append((ts, amount_cents))

        captures.sort(key=lambda item: item[0])
        recent_by_amount: dict[int, list[datetime]] = {}
        for ts, amount in captures:
            recent_times = [
                recorded for recorded in recent_by_amount.get(amount, []) if ts - recorded <= window
            ]
            if recent_times:
                return True
            recent_times.append(ts)
            recent_by_amount[amount] = recent_times
        return False

    def _query_payment_timeline(
        self,
        *,
        booking_id: Optional[str],
        user_id: Optional[str],
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, Any]:
        bookings: list[Booking] = []
        if booking_id:
            booking = self.repository.get_booking_with_payment_intent(booking_id)
            if booking:
                bookings = [booking]
        elif user_id:
            bookings = self.repository.get_user_bookings_for_payment_timeline(
                user_id=user_id,
                start_time=start_time,
                end_time=end_time,
            )

        if booking_id:
            events = self.payment_repository.get_payment_events_for_booking(
                booking_id,
                start_time=start_time,
                end_time=end_time,
            )
        else:
            events = self.payment_repository.get_payment_events_for_user(
                user_id or "",
                start_time=start_time,
                end_time=end_time,
            )

        grouped: dict[str, list[PaymentEvent]] = {}
        for event in events:
            grouped.setdefault(event.booking_id, []).append(event)

        booking_map: dict[str, Booking] = {booking.id: booking for booking in bookings}
        for event in events:
            if event.booking:
                booking_map.setdefault(event.booking_id, event.booking)

        payments: list[dict[str, Any]] = []
        has_failed_payment = False
        has_pending_refund = False
        summary_by_status = {status: 0 for status in PAYMENT_TIMELINE_STATUSES}

        for booking_id_value, booking in booking_map.items():
            booking_events = grouped.get(booking_id_value, [])
            booking_events.sort(key=lambda ev: ev.created_at or datetime.now(timezone.utc))

            credits_applied_cents = self._resolve_credits_applied_cents(booking_events)
            status_timeline = self._build_status_timeline(booking, booking_events)
            provider_refs = self._build_provider_refs(booking, booking_events)
            failure = self._build_failure(booking_events)
            refunds = self._build_refunds(booking_events)

            if failure is not None:
                has_failed_payment = True
            if any(refund.get("status") == "pending" for refund in refunds):
                has_pending_refund = True

            status_value = self._normalize_payment_status(booking, status_timeline, failure)
            created_at = booking.created_at or (
                _ensure_utc(booking_events[0].created_at)
                if booking_events
                else datetime.now(timezone.utc)
            )
            scheduled_authorize_at = None
            scheduled_capture_at = None
            if status_value in {
                PaymentStatus.SCHEDULED.value,
                PaymentStatus.AUTHORIZED.value,
            }:
                scheduled_authorize_at = self._resolve_scheduled_authorize_at(booking)
                scheduled_capture_at = self._resolve_scheduled_capture_at(booking)

            payments.append(
                {
                    "booking_id": booking.id,
                    "created_at": _ensure_utc(created_at),
                    "amount": self._build_amounts(booking, credits_applied_cents),
                    "status": status_value,
                    "status_timeline": status_timeline,
                    "scheduled_authorize_at": scheduled_authorize_at,
                    "scheduled_capture_at": scheduled_capture_at,
                    "provider_refs": provider_refs,
                    "failure": failure,
                    "refunds": refunds,
                }
            )
            summary_by_status[status_value] = summary_by_status.get(status_value, 0) + 1

        payments.sort(key=lambda item: item["created_at"], reverse=True)
        possible_double_charge = self._detect_double_charge(grouped)
        return {
            "payments": payments,
            "summary": {"by_status": summary_by_status},
            "flags": {
                "has_failed_payment": has_failed_payment,
                "has_pending_refund": has_pending_refund,
                "possible_double_charge": possible_double_charge,
            },
            "total_count": len(payments),
        }

    @BaseService.measure_operation("get_payment_timeline")
    async def get_payment_timeline(
        self,
        *,
        booking_id: Optional[str],
        user_id: Optional[str],
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._query_payment_timeline,
            booking_id=booking_id,
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
        )
