"""Referrer reporting and dashboard queries."""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import func

from ...models.referrals import InstructorReferralPayout, ReferralAttribution, ReferralCode
from .mixin_base import ReferralRewardRepositoryMixinBase

REFERRER_DASHBOARD_MAX_ROWS = 500


class ReferrerReportingMixin(ReferralRewardRepositoryMixinBase):
    """Read-heavy reporting queries for referrers."""

    def count_referrer_payouts_by_status(self, referrer_user_id: str, status: str) -> int:
        """Count payouts for a referrer by status."""
        result = (
            self.db.query(func.count(InstructorReferralPayout.id))
            .filter(
                InstructorReferralPayout.referrer_user_id == referrer_user_id,
                InstructorReferralPayout.stripe_transfer_status == status,
            )
            .scalar()
        )
        return int(result or 0)

    def sum_referrer_completed_payouts(self, referrer_user_id: str) -> int:
        """Sum completed payout amounts for a referrer (in cents)."""
        result = (
            self.db.query(func.coalesce(func.sum(InstructorReferralPayout.amount_cents), 0))
            .filter(
                InstructorReferralPayout.referrer_user_id == referrer_user_id,
                InstructorReferralPayout.stripe_transfer_status == "completed",
            )
            .scalar()
        )
        return int(result or 0)

    def count_referred_instructors_by_referrer(self, referrer_user_id: str) -> int:
        """
        Count instructors who were referred by this user.

        Joins referral attributions with instructor profiles to count
        only referred users who became instructors.
        """
        from app.models.instructor import InstructorProfile

        result = (
            self.db.query(func.count(ReferralAttribution.id))
            .join(ReferralCode, ReferralAttribution.code_id == ReferralCode.id)
            .join(
                InstructorProfile,
                ReferralAttribution.referred_user_id == InstructorProfile.user_id,
            )
            .filter(ReferralCode.referrer_user_id == referrer_user_id)
            .scalar()
        )
        return int(result or 0)

    def count_referred_users_by_referrer(self, referrer_user_id: str) -> int:
        """Count all referred users for the given referrer."""
        result = (
            self.db.query(func.count(ReferralAttribution.id))
            .join(ReferralCode, ReferralAttribution.code_id == ReferralCode.id)
            .filter(ReferralCode.referrer_user_id == referrer_user_id)
            .scalar()
        )
        return int(result or 0)

    def get_referred_instructors_with_payout_status(
        self,
        referrer_user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Get instructors referred by this user with payout status context.

        Returns a list of dicts with:
        - user_id, first_name, last_name
        - referred_at (attribution timestamp)
        - is_live, went_live_at (onboarding completion timestamp)
        - first_lesson_completed_at (min completed booking timestamp)
        - stripe_transfer_status, payout_amount_cents
        """
        from app.models.booking import Booking, BookingStatus
        from app.models.instructor import InstructorProfile
        from app.models.user import User

        first_lesson_subq = (
            self.db.query(
                Booking.instructor_id.label("instructor_id"),
                func.min(Booking.completed_at).label("first_lesson_completed_at"),
            )
            .filter(Booking.status == BookingStatus.COMPLETED)
            .group_by(Booking.instructor_id)
            .subquery()
        )

        query = (
            self.db.query(
                User.id.label("user_id"),
                User.first_name,
                User.last_name,
                ReferralAttribution.ts.label("referred_at"),
                InstructorProfile.is_live,
                InstructorProfile.onboarding_completed_at.label("went_live_at"),
                first_lesson_subq.c.first_lesson_completed_at,
                InstructorReferralPayout.stripe_transfer_status,
                InstructorReferralPayout.amount_cents.label("payout_amount_cents"),
            )
            .select_from(ReferralAttribution)
            .join(ReferralCode, ReferralAttribution.code_id == ReferralCode.id)
            .join(User, ReferralAttribution.referred_user_id == User.id)
            .join(InstructorProfile, User.id == InstructorProfile.user_id)
            .outerjoin(
                first_lesson_subq,
                User.id == first_lesson_subq.c.instructor_id,
            )
            .outerjoin(
                InstructorReferralPayout,
                User.id == InstructorReferralPayout.referred_instructor_id,
            )
            .filter(ReferralCode.referrer_user_id == referrer_user_id)
            .order_by(ReferralAttribution.ts.desc())
            .offset(offset)
            .limit(limit)
        )

        results: List[Dict[str, Any]] = []
        for row in query.all():
            results.append(
                {
                    "user_id": row.user_id,
                    "first_name": row.first_name,
                    "last_name": row.last_name,
                    "referred_at": row.referred_at,
                    "is_live": bool(row.is_live),
                    "went_live_at": row.went_live_at,
                    "first_lesson_completed_at": row.first_lesson_completed_at,
                    "stripe_transfer_status": row.stripe_transfer_status,
                    "payout_amount_cents": row.payout_amount_cents,
                }
            )

        return results

    def list_referrer_dashboard_rows(self, referrer_user_id: str) -> List[Dict[str, Any]]:
        """Return normalized referral dashboard rows for an instructor referrer."""
        from app.models.booking import Booking, BookingStatus
        from app.models.instructor import InstructorProfile
        from app.models.user import User

        instructor_first_lesson_subq = (
            self.db.query(
                Booking.instructor_id.label("user_id"),
                func.min(Booking.completed_at).label("first_lesson_completed_at"),
            )
            .filter(Booking.status == BookingStatus.COMPLETED)
            .group_by(Booking.instructor_id)
            .subquery()
        )

        student_first_lesson_subq = (
            self.db.query(
                Booking.student_id.label("user_id"),
                func.min(Booking.completed_at).label("first_lesson_completed_at"),
            )
            .filter(Booking.status == BookingStatus.COMPLETED)
            .group_by(Booking.student_id)
            .subquery()
        )

        query = (
            self.db.query(
                ReferralAttribution.id.label("attribution_id"),
                ReferralAttribution.referred_user_id.label("user_id"),
                ReferralAttribution.ts.label("referred_at"),
                User.first_name,
                User.last_name,
                InstructorProfile.user_id.label("instructor_user_id"),
                instructor_first_lesson_subq.c.first_lesson_completed_at.label(
                    "instructor_first_lesson_completed_at"
                ),
                student_first_lesson_subq.c.first_lesson_completed_at.label(
                    "student_first_lesson_completed_at"
                ),
                InstructorReferralPayout.id.label("payout_id"),
                InstructorReferralPayout.amount_cents.label("payout_amount_cents"),
                InstructorReferralPayout.created_at.label("payout_created_at"),
                InstructorReferralPayout.transferred_at,
                InstructorReferralPayout.failed_at,
                InstructorReferralPayout.failure_reason,
                InstructorReferralPayout.stripe_transfer_status,
            )
            .select_from(ReferralAttribution)
            .join(ReferralCode, ReferralAttribution.code_id == ReferralCode.id)
            .join(User, ReferralAttribution.referred_user_id == User.id)
            .outerjoin(InstructorProfile, User.id == InstructorProfile.user_id)
            .outerjoin(
                instructor_first_lesson_subq,
                User.id == instructor_first_lesson_subq.c.user_id,
            )
            .outerjoin(
                student_first_lesson_subq,
                User.id == student_first_lesson_subq.c.user_id,
            )
            .outerjoin(
                InstructorReferralPayout,
                User.id == InstructorReferralPayout.referred_instructor_id,
            )
            .filter(ReferralCode.referrer_user_id == referrer_user_id)
            .order_by(ReferralAttribution.ts.desc())
            .limit(REFERRER_DASHBOARD_MAX_ROWS)
        )

        results: List[Dict[str, Any]] = []
        for row in query.all():
            is_instructor = row.instructor_user_id is not None
            first_lesson_completed_at = (
                row.instructor_first_lesson_completed_at
                if is_instructor
                else row.student_first_lesson_completed_at
            )
            results.append(
                {
                    "attribution_id": row.attribution_id,
                    "user_id": row.user_id,
                    "first_name": row.first_name,
                    "last_name": row.last_name,
                    "referred_at": row.referred_at,
                    "referral_type": "instructor" if is_instructor else "student",
                    "first_lesson_completed_at": first_lesson_completed_at,
                    "payout_id": row.payout_id,
                    "payout_amount_cents": row.payout_amount_cents,
                    "payout_created_at": row.payout_created_at,
                    "transferred_at": row.transferred_at,
                    "failed_at": row.failed_at,
                    "failure_reason": row.failure_reason,
                    "stripe_transfer_status": row.stripe_transfer_status,
                }
            )

        return results
