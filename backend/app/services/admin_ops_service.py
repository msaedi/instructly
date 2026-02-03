"""Service for MCP Admin Operations - bookings, payments, and user support."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.booking import BookingStatus, PaymentStatus
from app.repositories.admin_ops_repository import AdminOpsRepository

from .base import BaseService

logger = logging.getLogger(__name__)


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
