# backend/app/services/badge_award_service.py
"""Service for awarding and finalizing student badges."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any, Dict, Optional, Set

from sqlalchemy.orm import Session

from ..core.timezone_utils import get_user_timezone
from ..notifications.policy import can_send_now, record_send
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
            progress_snapshot = self._build_momentum_progress_snapshot(
                momentum_definition,
                student_id,
                instructor_id,
                lesson_id,
                booked_at_utc,
                completed_at_utc,
            )
            if progress_snapshot:
                self.repository.upsert_progress(
                    student_id,
                    momentum_definition.id,
                    progress_snapshot,
                    now_utc=now,
                )

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

        with self.repository.transaction():
            for award, definition in pending_rows:
                if self._is_student_currently_eligible(award.student_id, definition, now_utc):
                    self.repository.mark_award_confirmed(award, confirmed_at=now_utc)
                    self._maybe_notify_badge_awarded(award.student_id, definition, now_utc)
                    confirmed += 1
                else:
                    self.repository.mark_award_revoked(award, revoked_at=now_utc)
                    revoked += 1

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
        send_notifications: bool = True,
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
            if hold_hours <= 0 and send_notifications:
                self._maybe_notify_badge_awarded(student_id, badge_definition, now_utc)

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

    def _build_momentum_progress_snapshot(
        self,
        definition,
        student_id: str,
        instructor_id: str,
        lesson_id: str,
        booked_at_utc: Optional[datetime],
        completed_at_utc: datetime,
    ) -> Dict[str, Any]:
        criteria = definition.criteria_config or {}
        goal = int(criteria.get("goal", 2) or 2)
        goal = goal if goal > 0 else 2
        booked_at = booked_at_utc or completed_at_utc

        snapshot: Dict[str, Any] = {
            "current": 1,
            "goal": goal,
            "percent": min(100, int((1 / goal) * 100)) if goal else 0,
            "same_instructor": False,
            "booked_within_window": False,
            "completed_within_window": False,
            "eligible_pair": False,
        }
        previous = self.repository.get_latest_completed_lesson(
            student_id,
            before=completed_at_utc,
            exclude_booking_id=lesson_id,
        )
        snapshot["last_booked_at"] = booked_at.isoformat()
        snapshot["last_completed_at"] = completed_at_utc.isoformat()

        if not previous:
            return snapshot

        first_completed_at = previous.get("completed_at")
        if first_completed_at:
            snapshot["first_completed_at"] = first_completed_at.isoformat()

        same_instructor = previous.get("instructor_id") == instructor_id
        snapshot["same_instructor"] = bool(same_instructor)

        window_days_to_book = int(criteria.get("window_days_to_book", 0) or 0)
        booked_within_window = False
        if first_completed_at and booked_at >= first_completed_at:
            if window_days_to_book <= 0:
                booked_within_window = True
            else:
                booked_within_window = booked_at - first_completed_at <= timedelta(
                    days=window_days_to_book
                )
        snapshot["booked_within_window"] = booked_within_window

        window_days_to_complete = int(criteria.get("window_days_to_complete", 0) or 0)
        completed_within_window = False
        if booked_at and completed_at_utc >= booked_at:
            if window_days_to_complete <= 0:
                completed_within_window = True
            else:
                completed_within_window = completed_at_utc - booked_at <= timedelta(
                    days=window_days_to_complete
                )
        snapshot["completed_within_window"] = completed_within_window

        eligible_pair = bool(same_instructor and booked_within_window and completed_within_window)
        snapshot["eligible_pair"] = eligible_pair
        snapshot["current"] = goal if eligible_pair else 1
        if goal:
            snapshot["percent"] = min(100, int((snapshot["current"] / goal) * 100))
        else:
            snapshot["percent"] = 100 if snapshot["current"] else 0
        return snapshot

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

    def backfill_user_badges(
        self,
        student_id: str,
        now_utc: datetime,
        *,
        quality_window_days: int = 90,
        send_notifications: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Idempotently recompute and (optionally) award badges for one student from current DB state.

        Returns a summary dict:
          {
            "milestones": int,
            "streak": int,
            "explorer": int,
            "quality_pending": int,
            "skipped_existing": int,
            "dry_run": bool,
          }
        """

        summary: Dict[str, Any] = {
            "milestones": 0,
            "streak": 0,
            "explorer": 0,
            "quality_pending": 0,
            "skipped_existing": 0,
            "dry_run": dry_run,
        }

        definitions = {
            definition.slug: definition
            for definition in self.repository.list_active_badge_definitions()
        }
        if not definitions:
            return summary

        award_rows = self.repository.list_student_badge_awards(student_id)
        existing_award_ids: Set[str] = {
            row["badge_id"]
            for row in award_rows
            if row.get("badge_id") and row.get("status") in {"pending", "confirmed"}
        }

        total_completed = self.repository.count_completed_lessons(student_id)

        def _record_award(
            definition,
            summary_field: str,
            progress_snapshot: Dict[str, Any],
        ) -> None:
            if not definition:
                return

            if definition.id in existing_award_ids:
                summary["skipped_existing"] += 1
                return

            summary[summary_field] += 1
            if dry_run:
                return

            self._award_according_to_hold(
                student_id,
                definition,
                progress_snapshot,
                now_utc,
                send_notifications=send_notifications,
            )
            existing_award_ids.add(definition.id)

        # ------------------------
        # Milestone badges
        # ------------------------
        for slug in self.MILESTONE_SLUGS:
            definition = definitions.get(slug)
            if not definition:
                continue
            criteria = definition.criteria_config or {}
            goal = int(criteria.get("goal", 0) or 0)
            if goal <= 0:
                continue

            percent = min(100, int((total_completed * 100) / goal)) if goal else 0
            progress_snapshot = {
                "current": total_completed,
                "goal": goal,
                "percent": percent,
            }
            if not dry_run:
                self.repository.upsert_progress(
                    student_id,
                    definition.id,
                    progress_snapshot,
                    now_utc=now_utc,
                )

            if total_completed >= goal:
                award_snapshot = {
                    "current": total_completed,
                    "goal": goal,
                }
                _record_award(definition, "milestones", award_snapshot)

        # ------------------------
        # Consistent learner (streak)
        # ------------------------
        consistent_definition = definitions.get(self.CONSISTENT_SLUG)
        if consistent_definition:
            criteria = consistent_definition.criteria_config or {}
            goal = int(criteria.get("goal", 0) or 3)
            goal = goal if goal > 0 else 3
            grace_days = int(criteria.get("grace_days", 1) or 1)

            streak = 0
            student = self.user_repository.get_by_id(student_id)
            user_tz = None
            if student:
                try:
                    user_tz = get_user_timezone(student)
                except Exception:
                    user_tz = None

            if user_tz:
                completion_times = self.repository.list_completed_lesson_times(student_id)
                if completion_times:
                    completions_local = [dt.astimezone(user_tz) for dt in completion_times]
                    now_local = now_utc.astimezone(user_tz)
                    streak = compute_week_streak_local(
                        completions_local,
                        now_local,
                        grace_days=grace_days,
                    )

            percent = min(100, int((min(streak, goal) / goal) * 100)) if goal else 0
            streak_progress = {
                "current": streak,
                "goal": goal,
                "percent": percent,
            }
            if not dry_run:
                self.repository.upsert_progress(
                    student_id,
                    consistent_definition.id,
                    streak_progress,
                    now_utc=now_utc,
                )

            if streak >= goal:
                award_snapshot = {
                    "streak": streak,
                    "goal": goal,
                    "grace_days": grace_days,
                }
                _record_award(consistent_definition, "streak", award_snapshot)
                # If there was no existing award and we were eligible, summary["streak"] increments

        # ------------------------
        # Explorer badge
        # ------------------------
        explorer_definition = definitions.get("explorer")
        if explorer_definition:
            criteria = explorer_definition.criteria_config or {}
            show_threshold = int(criteria.get("show_after_total_lessons", 0) or 0)
            goal_categories = int(criteria.get("distinct_categories", 0) or 0)
            min_avg_rating = float(criteria.get("min_overall_avg_rating", 0.0) or 0.0)

            distinct_categories = self.repository.count_distinct_completed_categories(student_id)
            has_rebook = self.repository.has_rebook_in_any_category(student_id)
            avg_rating = self.repository.get_overall_student_avg_rating(student_id)

            goal = goal_categories if goal_categories > 0 else max(distinct_categories, 1)
            percent = min(100, int((min(distinct_categories, goal) / goal) * 100)) if goal else 0
            explorer_progress = {
                "current": distinct_categories,
                "goal": goal,
                "percent": percent,
                "has_rebook": has_rebook,
                "avg_rating": round(avg_rating, 2),
            }
            if not dry_run:
                self.repository.upsert_progress(
                    student_id,
                    explorer_definition.id,
                    explorer_progress,
                    now_utc=now_utc,
                )

            if total_completed >= show_threshold:
                goal_met = goal_categories <= 0 or distinct_categories >= goal_categories
                rating_met = avg_rating >= min_avg_rating
                if goal_met and has_rebook and rating_met:
                    snapshot = {
                        "distinct_categories": distinct_categories,
                        "has_rebook": has_rebook,
                        "avg_rating": round(avg_rating, 2),
                    }
                    _record_award(explorer_definition, "explorer", snapshot)

        # ------------------------
        # Quality badge (top student)
        # ------------------------
        quality_definition = definitions.get("top_student")
        if quality_definition:
            criteria = quality_definition.criteria_config or {}
            min_total_lessons = int(criteria.get("min_total_lessons", 0) or 0)
            min_reviews = int(criteria.get("min_reviews", 0) or 0)
            min_avg_rating = float(criteria.get("min_avg_rating", 0.0) or 0.0)
            max_cancel_rate = float(criteria.get("max_cancel_noshow_rate_pct_60d", 100.0) or 100.0)
            distinct_required = int(criteria.get("distinct_instructors_min", 0) or 0)
            single_instructor_goal = int(criteria.get("or_single_instructor_min_lessons", 0) or 0)

            if total_completed >= min_total_lessons:
                window_days = int(quality_window_days or 0)
                if window_days <= 0:
                    window_days = 90
                window_start = now_utc - timedelta(days=window_days)

                review_stats = self.repository.get_review_stats_since(student_id, window_start)
                if (
                    review_stats["count"] >= min_reviews
                    and review_stats["avg_rating"] >= min_avg_rating
                ):
                    cancel_window_days = min(window_days, 60) if window_days > 0 else 60
                    cancel_rate = self.repository.get_cancel_noshow_rate_pct_window(
                        student_id, now_utc, cancel_window_days
                    )
                    if cancel_rate <= max_cancel_rate:
                        distinct_instructors = (
                            self.repository.count_distinct_instructors_for_student(student_id)
                        )
                        max_lessons_single = self.repository.get_max_lessons_with_single_instructor(
                            student_id
                        )
                        depth_met = False
                        if distinct_required > 0 and distinct_instructors >= distinct_required:
                            depth_met = True
                        elif (
                            single_instructor_goal > 0
                            and max_lessons_single >= single_instructor_goal
                        ):
                            depth_met = True

                        if depth_met:
                            snapshot = {
                                "window_start": window_start.isoformat(),
                                "review_count": review_stats["count"],
                                "avg_rating": round(review_stats["avg_rating"], 2),
                                "cancel_rate_pct": round(cancel_rate, 2),
                                "distinct_instructors": distinct_instructors,
                                "max_lessons_single_instructor": max_lessons_single,
                                "quality_window_days": window_days,
                            }
                            _record_award(quality_definition, "quality_pending", snapshot)

        return summary

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

    def _maybe_notify_badge_awarded(
        self, student_id: str, badge_definition, now_utc: datetime
    ) -> None:
        if not self.notification_service:
            return

        user = self.user_repository.get_by_id(student_id)
        if not user or not getattr(user, "email", None):
            return

        allowed, reason, key = can_send_now(user, now_utc, self.cache_service)
        if not allowed:
            logger.info(
                "Badge notification skipped for %s (%s)",
                student_id,
                reason,
            )
            return

        if self.notification_service.send_badge_awarded_email(user, badge_definition.name):
            record_send(key, self.cache_service)

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
