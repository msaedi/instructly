# backend/app/services/badge_award_service.py
"""Service for awarding and finalizing student badges."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..core.timezone_utils import get_user_timezone
from ..repositories.badge_repository import BadgeRepository
from ..repositories.factory import RepositoryFactory
from ..services.cache_service import CacheService
from ..services.notification_service import NotificationService
from ..utils.streaks import compute_week_streak_local

logger = logging.getLogger(__name__)


class BadgeAwardService:
    """Award badges based on lesson completion milestones and momentum."""

    MILESTONE_SLUGS = [
        "welcome_aboard",
        "foundation_builder",
        "first_steps",
        "dedicated_learner",
    ]
    MOMENTUM_SLUG = "momentum_starter"
    CONSISTENT_SLUG = "consistent_learner"

    def __init__(
        self,
        db: Session,
        notification_service: Optional[NotificationService] = None,
        cache_service: Optional[CacheService] = None,
    ):
        self.db = db
        self.repository: BadgeRepository = RepositoryFactory.create_badge_repository(db)
        self.user_repository = RepositoryFactory.create_user_repository(db)
        if cache_service is None:
            try:
                cache_service = CacheService(db)
            except Exception as exc:
                logger.warning("CacheService unavailable for BadgeAwardService: %s", exc)
                cache_service = None
        self.cache_service = cache_service

        if notification_service is None:
            try:
                notification_service = NotificationService(db)
            except Exception as exc:
                logger.warning("NotificationService unavailable: %s", exc)
                notification_service = None
        self.notification_service = notification_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_and_award_on_lesson_completed(
        self,
        student_id: str,
        lesson_id: str,
        *,
        instructor_id: str,
        category_slug: Optional[str],  # reserved for future badges
        booked_at_utc: Optional[datetime],
        completed_at_utc: datetime,
    ) -> None:
        """Evaluate milestone and momentum badges after a lesson is completed."""

        definitions = {
            definition.slug: definition
            for definition in self.repository.list_active_badge_definitions()
        }

        now = completed_at_utc

        # Milestone progress + awards
        total_completed = self.repository.count_completed_lessons(student_id)
        for slug in self.MILESTONE_SLUGS:
            definition = definitions.get(slug)
            if not definition:
                continue

            criteria = definition.criteria_config or {}
            goal = int(criteria.get("goal", 0))
            if goal <= 0:
                continue

            progress_snapshot = {
                "current": min(total_completed, goal),
                "goal": goal,
            }
            self.repository.upsert_progress(
                student_id,
                definition.id,
                progress_snapshot,
                now_utc=now,
            )

            if total_completed >= goal and not self.repository.student_has_badge(
                student_id, definition.id
            ):
                award_snapshot = {
                    "current": total_completed,
                    "goal": goal,
                }
                self._award_according_to_hold(student_id, definition, award_snapshot, now)

        # Momentum starter check
        momentum_definition = definitions.get(self.MOMENTUM_SLUG)
        if momentum_definition:
            if self._is_momentum_criteria_met_on_completion(
                momentum_definition,
                student_id,
                instructor_id,
                lesson_id,
                booked_at_utc,
                completed_at_utc,
            ) and not self.repository.student_has_badge(student_id, momentum_definition.id):
                snapshot = {
                    "qualified": True,
                    "first_completed_at": self._get_latest_completed_lesson_time(
                        student_id, completed_at_utc, lesson_id
                    ),
                    "booked_at": (booked_at_utc or completed_at_utc).isoformat(),
                    "completed_at": completed_at_utc.isoformat(),
                }
                self._award_according_to_hold(student_id, momentum_definition, snapshot, now)

        # Weekly streak badge (consistent learner)
        consistent_definition = definitions.get(self.CONSISTENT_SLUG)
        if consistent_definition:
            self._evaluate_consistent_learner(
                consistent_definition,
                student_id=student_id,
                completed_at_utc=completed_at_utc,
            )

        explorer_definition = definitions.get("explorer")
        if explorer_definition:
            self._evaluate_explorer(
                explorer_definition,
                student_id=student_id,
                completed_at_utc=completed_at_utc,
            )

    def finalize_pending_badges(self, now_utc: datetime) -> Dict[str, int]:
        """Confirm or revoke pending badges whose holds have elapsed."""

        confirmed = revoked = 0
        pending_rows = list(self.repository.get_pending_awards_due(now_utc))

        for award, definition in pending_rows:
            if self._is_student_currently_eligible(award.student_id, definition, now_utc):
                self.repository.mark_award_confirmed(award, confirmed_at=now_utc)
                confirmed += 1
            else:
                self.repository.mark_award_revoked(award, revoked_at=now_utc)
                revoked += 1

        # repo-pattern-migrate: TODO: migrate to repository (unit-of-work/commit)
        self.db.flush()
        # repo-pattern-migrate: TODO: migrate to repository (unit-of-work/commit)
        self.db.commit()

        return {"confirmed": confirmed, "revoked": revoked}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _award_according_to_hold(
        self,
        student_id: str,
        badge_definition,
        progress_snapshot: Dict[str, Any],
        now_utc: datetime,
    ) -> None:
        criteria = badge_definition.criteria_config or {}
        hold_hours = int(criteria.get("hold_hours", 0))
        award_id = self.repository.insert_award_pending_or_confirmed(
            student_id,
            badge_definition.id,
            hold_hours=hold_hours,
            progress_snapshot=progress_snapshot,
            now_utc=now_utc,
        )
        if award_id:
            status = "pending" if hold_hours > 0 else "confirmed"
            masked_student = f"***{student_id[-4:]}"
            logger.info(
                "Awarded badge %s to student %s (status=%s)",
                badge_definition.slug,
                masked_student,
                status,
            )

    def _get_latest_completed_lesson_time(
        self,
        student_id: str,
        completed_at_utc: datetime,
        lesson_id: str,
    ) -> Optional[str]:
        info = self.repository.get_latest_completed_lesson(
            student_id,
            before=completed_at_utc,
            exclude_booking_id=lesson_id,
        )
        if not info:
            return None
        return info["completed_at"].isoformat() if info["completed_at"] else None

    def check_and_award_on_review_received(
        self,
        student_id: str,
        review_id: str,
        created_at_utc: datetime,
    ) -> None:
        definition = self.repository.get_badge_definition_by_slug("top_student")
        if not definition or not definition.is_active:
            return

        if self.repository.student_has_badge(student_id, definition.id):
            return

        if self._is_top_student_eligible_now(student_id, created_at_utc, definition):
            snapshot = {
                "eligible_at": created_at_utc.isoformat(),
                "review_id": review_id,
            }
            self._award_according_to_hold(student_id, definition, snapshot, created_at_utc)

    def _is_student_currently_eligible(
        self, student_id: str, definition, now_utc: datetime
    ) -> bool:
        criteria_type = (definition.criteria_type or "").lower()
        criteria = definition.criteria_config or {}

        if criteria_type == "milestone" and criteria.get("counts") == "completed_lessons":
            goal = int(criteria.get("goal", 0))
            if goal <= 0:
                return False
            total = self.repository.count_completed_lessons(student_id)
            return total >= goal

        if criteria_type == "velocity":
            return self._is_momentum_criteria_currently_met(definition, student_id)

        if criteria_type == "quality":
            return self._is_top_student_eligible_now(student_id, now_utc, definition)

        if criteria_type == "exploration":
            return self._is_explorer_eligible_now(student_id, definition)

        if criteria_type == "streak":
            goal = int(criteria.get("goal", 0) or 0)
            streak = self._current_streak_length(student_id, definition, goal=goal or 3)
            return goal > 0 and streak >= goal

        # Default to True for badge types we do not re-evaluate yet.
        return True

    # ------------------------------------------------------------------
    # Momentum helpers
    # ------------------------------------------------------------------

    def _is_momentum_criteria_met_on_completion(
        self,
        definition,
        student_id: str,
        instructor_id: str,
        lesson_id: str,
        booked_at_utc: Optional[datetime],
        completed_at_utc: datetime,
    ) -> bool:
        criteria = definition.criteria_config or {}

        previous = self.repository.get_latest_completed_lesson(
            student_id,
            before=completed_at_utc,
            exclude_booking_id=lesson_id,
        )
        if not previous:
            return False

        first_completed_at = previous["completed_at"]
        if not first_completed_at:
            return False

        if criteria.get("same_instructor_required") and previous["instructor_id"] != instructor_id:
            return False

        booked_at = booked_at_utc or completed_at_utc
        if booked_at < first_completed_at:
            return False

        window_days_to_book = int(criteria.get("window_days_to_book", 0) or 0)
        if window_days_to_book and booked_at - first_completed_at > timedelta(
            days=window_days_to_book
        ):
            return False

        window_days_to_complete = int(criteria.get("window_days_to_complete", 0) or 0)
        if window_days_to_complete and completed_at_utc - booked_at > timedelta(
            days=window_days_to_complete
        ):
            return False

        return True

    def _evaluate_consistent_learner(
        self,
        definition,
        *,
        student_id: str,
        completed_at_utc: datetime,
    ) -> None:
        criteria = definition.criteria_config or {}
        goal = int(criteria.get("goal", 0) or 3)
        grace_days = int(criteria.get("grace_days", 1) or 1)

        student = self.user_repository.get_by_id(student_id)
        if not student:
            return

        try:
            user_tz = get_user_timezone(student)
        except Exception:
            return

        if user_tz is None:
            return

        completion_times = self.repository.list_completed_lesson_times(student_id)
        if not completion_times:
            streak = 0
        else:
            now_local = completed_at_utc.astimezone(user_tz)
            completions_local = [dt.astimezone(user_tz) for dt in completion_times]
            streak = compute_week_streak_local(
                completions_local,
                now_local,
                grace_days=grace_days,
            )

        goal = goal if goal > 0 else 3
        percent = min(100, int((streak / goal) * 100)) if goal else 0
        progress_snapshot = {
            "current": streak,
            "goal": goal,
            "percent": percent,
        }
        self.repository.upsert_progress(
            student_id,
            definition.id,
            progress_snapshot,
            now_utc=completed_at_utc,
        )

        if streak >= goal and not self.repository.student_has_badge(student_id, definition.id):
            snapshot = {
                "streak": streak,
                "goal": goal,
                "grace_days": grace_days,
            }
            self._award_according_to_hold(student_id, definition, snapshot, completed_at_utc)

    def _current_streak_length(self, student_id: str, definition, goal: int) -> int:
        criteria = definition.criteria_config or {}
        grace_days = int(criteria.get("grace_days", 1) or 1)

        student = self.user_repository.get_by_id(student_id)
        if not student:
            return 0
        try:
            user_tz = get_user_timezone(student)
        except Exception:
            return 0
        if user_tz is None:
            return 0

        completion_times = self.repository.list_completed_lesson_times(student_id)
        if not completion_times:
            return 0

        completions_local = [dt.astimezone(user_tz) for dt in completion_times]
        now_local = completion_times[0].astimezone(user_tz)
        return compute_week_streak_local(completions_local, now_local, grace_days=grace_days)

    def _is_momentum_criteria_currently_met(self, definition, student_id: str) -> bool:
        criteria = definition.criteria_config or {}
        window_days_to_book = int(criteria.get("window_days_to_book", 0) or 0)
        window_days_to_complete = int(criteria.get("window_days_to_complete", 0) or 0)
        require_same_instructor = bool(criteria.get("same_instructor_required"))

        completed_lessons = self.repository.list_completed_lessons(student_id)
        if len(completed_lessons) < 2:
            return False

        for i in range(1, len(completed_lessons)):
            first = completed_lessons[i - 1]
            second = completed_lessons[i]

            first_completed_at = first["completed_at"]
            second_completed_at = second["completed_at"]
            booked_at = second["booked_at"] or second_completed_at

            if require_same_instructor and first["instructor_id"] != second["instructor_id"]:
                continue

            if booked_at < first_completed_at:
                continue

            if window_days_to_book and booked_at - first_completed_at > timedelta(
                days=window_days_to_book
            ):
                continue

            if window_days_to_complete and second_completed_at - booked_at > timedelta(
                days=window_days_to_complete
            ):
                continue

            return True

        return False

    def _is_top_student_eligible_now(
        self,
        student_id: str,
        now_utc: datetime,
        definition,
    ) -> bool:
        criteria = definition.criteria_config or {}

        min_total_lessons = int(criteria.get("min_total_lessons", 0) or 0)
        if self.repository.count_completed_lessons(student_id) < min_total_lessons:
            return False

        stats = self.repository.get_review_stats(student_id)
        min_reviews = int(criteria.get("min_reviews", 0) or 0)
        min_avg_rating = float(criteria.get("min_avg_rating", 0.0) or 0.0)
        if stats["count"] < min_reviews or stats["avg_rating"] < min_avg_rating:
            return False

        max_cancel_rate = float(criteria.get("max_cancel_noshow_rate_pct_60d", 100.0) or 100.0)
        cancel_rate = self.repository.get_cancel_noshow_rate_pct_60d(student_id, now_utc)
        if cancel_rate > max_cancel_rate:
            return False

        distinct_required = int(criteria.get("distinct_instructors_min", 0) or 0)
        if (
            distinct_required
            and self.repository.count_distinct_instructors_for_student(student_id)
            >= distinct_required
        ):
            return True

        single_instructor_goal = int(criteria.get("or_single_instructor_min_lessons", 0) or 0)
        if single_instructor_goal <= 0:
            return False

        return (
            self.repository.get_max_lessons_with_single_instructor(student_id)
            >= single_instructor_goal
        )

    def _evaluate_explorer(
        self,
        definition,
        *,
        student_id: str,
        completed_at_utc: datetime,
    ) -> None:
        criteria = definition.criteria_config or {}
        total_completed = self.repository.count_completed_lessons(student_id)
        show_threshold = int(criteria.get("show_after_total_lessons", 0) or 0)

        goal_categories = int(criteria.get("distinct_categories", 0) or 0)
        distinct_categories = self.repository.count_distinct_completed_categories(student_id)
        has_rebook = self.repository.has_rebook_in_any_category(student_id)
        avg_rating = self.repository.get_overall_student_avg_rating(student_id)
        min_avg = float(criteria.get("min_overall_avg_rating", 0.0) or 0.0)

        goal = goal_categories if goal_categories > 0 else max(distinct_categories, 1)
        percent = min(100, int((min(distinct_categories, goal) / goal) * 100)) if goal else 0
        progress_snapshot = {
            "current": distinct_categories,
            "goal": goal,
            "percent": percent,
            "has_rebook": has_rebook,
            "avg_rating": round(avg_rating, 2),
        }

        self.repository.upsert_progress(
            student_id,
            definition.id,
            progress_snapshot,
            now_utc=completed_at_utc,
        )

        if total_completed < show_threshold:
            return

        if (
            distinct_categories >= goal_categories
            and has_rebook
            and avg_rating >= min_avg
            and not self.repository.student_has_badge(student_id, definition.id)
        ):
            snapshot = {
                "distinct_categories": distinct_categories,
                "has_rebook": has_rebook,
                "avg_rating": round(avg_rating, 2),
            }
            self._award_according_to_hold(student_id, definition, snapshot, completed_at_utc)

    def _is_explorer_eligible_now(self, student_id: str, definition) -> bool:
        criteria = definition.criteria_config or {}
        total_completed = self.repository.count_completed_lessons(student_id)
        show_threshold = int(criteria.get("show_after_total_lessons", 0) or 0)
        if total_completed < show_threshold:
            return False

        goal_categories = int(criteria.get("distinct_categories", 0) or 0)
        min_avg = float(criteria.get("min_overall_avg_rating", 0.0) or 0.0)

        distinct_categories = self.repository.count_distinct_completed_categories(student_id)
        if goal_categories and distinct_categories < goal_categories:
            return False

        if not self.repository.has_rebook_in_any_category(student_id):
            return False

        avg_rating = self.repository.get_overall_student_avg_rating(student_id)
        if avg_rating < min_avg:
            return False

        return True


__all__ = ["BadgeAwardService"]
