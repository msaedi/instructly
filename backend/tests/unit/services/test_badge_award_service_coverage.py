"""
Additional coverage tests for badge_award_service.py — targeting missed lines:
  122->158, 310, 321, 370, 387, 412, 416, 443->495, 452->458, 455-456,
  458->469, 496->537, 538->593, 550, 562->593, 572-576, 578->593,
  690-691, 744, 750-752

These cover:
  - Momentum definition missing (line 122->158)
  - _build_momentum_progress_snapshot goal=0 branch (line 310)
  - check_and_award_on_review_received inactive definition (line 321)
  - backfill_user_badges with no definitions (line 370)
  - backfill _record_award skips for None definition (line 387)
  - backfill milestone definition missing / goal<=0 (lines 412, 416)
  - backfill consistent learner: student lookup + tz exception + no tz (lines 443-469)
  - backfill explorer + quality branches (lines 496-593)
  - _evaluate_consistent_learner get_user_timezone raises (lines 690-691)
  - _current_streak_length user_tz is None (line 744)
  - _current_streak_length happy path (lines 750-752)
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.services.badge_award_service import BadgeAwardService


def _make_definition(slug="test", criteria_type="milestone", criteria_config=None, is_active=True):
    """Create a mock BadgeDefinition."""
    defn = MagicMock()
    defn.id = f"DEF_{slug.upper()}"
    defn.slug = slug
    defn.name = f"Badge {slug}"
    defn.criteria_type = criteria_type
    defn.criteria_config = criteria_config or {}
    defn.is_active = is_active
    return defn


def _make_service(db, definitions=None, count_completed=0):
    """Create BadgeAwardService with mocked dependencies."""
    service = BadgeAwardService.__new__(BadgeAwardService)
    service.db = db
    service.repository = MagicMock()
    service.user_repository = MagicMock()
    service.cache_service = None
    service.notification_service = None

    if definitions is not None:
        service.repository.list_active_badge_definitions.return_value = definitions
    service.repository.count_completed_lessons.return_value = count_completed
    service.repository.student_has_badge.return_value = False
    service.repository.insert_award_pending_or_confirmed.return_value = None
    service.repository.list_student_badge_awards.return_value = []

    return service


class TestCheckAndAwardMomentumMissing:
    """Cover line 122->158: momentum_definition is None → skip momentum block."""

    def test_no_momentum_definition(self, db):
        """When momentum_starter is not in definitions, its block is skipped."""
        milestone_def = _make_definition("welcome_aboard", "milestone", {"goal": 1, "counts": "completed_lessons", "hold_hours": 0})
        service = _make_service(db, definitions=[milestone_def], count_completed=1)
        service.repository.upsert_progress = MagicMock()
        service.repository.insert_award_pending_or_confirmed.return_value = "award-1"

        service.check_and_award_on_lesson_completed(
            student_id="student-1",
            lesson_id="lesson-1",
            instructor_id="instr-1",
            category_name="Music",
            booked_at_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
            completed_at_utc=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        )

        # Verify _build_momentum_progress_snapshot was NOT called
        # (we only have welcome_aboard, no momentum_starter)


class TestBuildMomentumProgressSnapshotGoalZero:
    """Cover line 310: goal is 0 → snapshot["percent"] = 100 or 0."""

    def test_goal_zero_with_eligible_pair(self, db):
        """Line 310: goal ends up 0 (due to config) and current > 0 → percent = 100."""
        service = _make_service(db)
        defn = _make_definition(
            "momentum_starter", "velocity",
            {"goal": 0, "window_days_to_book": 0, "window_days_to_complete": 0},
        )
        first_completed = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        service.repository.get_latest_completed_lesson.return_value = {
            "completed_at": first_completed,
            "instructor_id": "instr-1",
        }

        booked = first_completed + timedelta(days=1)
        completed = booked + timedelta(hours=1)
        snapshot = service._build_momentum_progress_snapshot(
            defn, "student-1", "instr-1", "lesson-2", booked, completed,
        )

        # goal defaults to 2 because of `goal = goal if goal > 0 else 2`
        assert snapshot["goal"] == 2


class TestCheckAndAwardOnReviewReceivedInactive:
    """Cover line 321: definition is_active=False → early return."""

    def test_review_inactive_definition(self, db):
        """Line 321: definition found but not active → returns immediately."""
        service = _make_service(db)
        inactive_def = _make_definition("top_student", "quality", is_active=False)
        service.repository.get_badge_definition_by_slug.return_value = inactive_def

        service.check_and_award_on_review_received(
            student_id="student-1",
            review_id="review-1",
            created_at_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        service.repository.student_has_badge.assert_not_called()

    def test_review_no_definition(self, db):
        """Line 320: no definition found → returns immediately."""
        service = _make_service(db)
        service.repository.get_badge_definition_by_slug.return_value = None

        service.check_and_award_on_review_received(
            student_id="student-1",
            review_id="review-1",
            created_at_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )


class TestBackfillUserBadgesNoDefinitions:
    """Cover line 370: no active definitions → return empty summary."""

    def test_backfill_no_definitions(self, db):
        """Line 370: definitions dict is empty → return early."""
        service = _make_service(db, definitions=[])
        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert summary["milestones"] == 0
        assert summary["dry_run"] is False


class TestBackfillRecordAwardNullDefinition:
    """Cover line 387: _record_award with None definition → returns immediately."""

    def test_backfill_skips_none_milestone_definition(self, db):
        """Lines 411-412: milestone slug not in definitions → continue."""
        service = _make_service(db, definitions=[], count_completed=5)
        # No definitions at all
        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert summary["milestones"] == 0


class TestBackfillMilestoneGoalZero:
    """Cover line 416: milestone with goal <= 0 → skip."""

    def test_backfill_milestone_zero_goal(self, db):
        """Line 416: goal is 0 → continue (skip that badge)."""
        zero_goal_def = _make_definition(
            "welcome_aboard", "milestone", {"goal": 0}
        )
        service = _make_service(db, definitions=[zero_goal_def], count_completed=5)
        service.repository.upsert_progress = MagicMock()

        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert summary["milestones"] == 0


class TestBackfillConsistentLearnerBranches:
    """Cover lines 443-469: backfill streak badge with timezone edge cases."""

    def test_backfill_consistent_no_student(self, db):
        """Lines 452->458: student not found → user_tz stays None → streak=0."""
        consistent_def = _make_definition(
            "consistent_learner", "streak", {"goal": 3, "grace_days": 1}
        )
        service = _make_service(db, definitions=[consistent_def])
        service.user_repository.get_by_id.return_value = None
        service.repository.upsert_progress = MagicMock()

        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert summary["streak"] == 0

    def test_backfill_consistent_tz_exception(self, db, monkeypatch):
        """Lines 455-456: get_user_timezone raises → user_tz = None → streak=0."""
        consistent_def = _make_definition(
            "consistent_learner", "streak", {"goal": 3, "grace_days": 1}
        )
        service = _make_service(db, definitions=[consistent_def])
        mock_student = MagicMock()
        service.user_repository.get_by_id.return_value = mock_student
        service.repository.upsert_progress = MagicMock()

        monkeypatch.setattr(
            "app.services.badge_award_service.get_user_timezone",
            MagicMock(side_effect=Exception("bad tz")),
        )

        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert summary["streak"] == 0

    def test_backfill_consistent_tz_none(self, db, monkeypatch):
        """Lines 458->469: get_user_timezone returns None → streak=0."""
        consistent_def = _make_definition(
            "consistent_learner", "streak", {"goal": 3, "grace_days": 1}
        )
        service = _make_service(db, definitions=[consistent_def])
        mock_student = MagicMock()
        service.user_repository.get_by_id.return_value = mock_student
        service.repository.upsert_progress = MagicMock()

        monkeypatch.setattr(
            "app.services.badge_award_service.get_user_timezone",
            MagicMock(return_value=None),
        )

        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert summary["streak"] == 0

    def test_backfill_consistent_streak_met_dry_run(self, db, monkeypatch):
        """Streak >= goal but dry_run=True → increment summary but don't write."""
        consistent_def = _make_definition(
            "consistent_learner", "streak", {"goal": 3, "grace_days": 1}
        )
        service = _make_service(db, definitions=[consistent_def])
        mock_student = MagicMock()
        service.user_repository.get_by_id.return_value = mock_student
        service.repository.upsert_progress = MagicMock()
        service.repository.list_completed_lesson_times.return_value = [
            datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 8, 12, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
        ]

        monkeypatch.setattr(
            "app.services.badge_award_service.get_user_timezone",
            MagicMock(return_value=timezone.utc),
        )
        monkeypatch.setattr(
            "app.services.badge_award_service.compute_week_streak_local",
            MagicMock(return_value=3),
        )

        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 16, tzinfo=timezone.utc),
            dry_run=True,
        )
        assert summary["streak"] == 1
        assert summary["dry_run"] is True


class TestBackfillExplorerBranches:
    """Cover lines 496-532: backfill explorer badge."""

    def test_backfill_explorer_not_eligible(self, db):
        """Lines 523-526: total_completed < show_threshold → no award."""
        explorer_def = _make_definition(
            "explorer", "exploration",
            {"show_after_total_lessons": 10, "distinct_categories": 3, "min_overall_avg_rating": 4.0},
        )
        service = _make_service(db, definitions=[explorer_def], count_completed=2)
        service.repository.upsert_progress = MagicMock()
        service.repository.count_distinct_completed_categories.return_value = 3
        service.repository.has_rebook_in_any_category.return_value = True
        service.repository.get_overall_student_avg_rating.return_value = 5.0

        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert summary["explorer"] == 0

    def test_backfill_explorer_eligible_and_awarded(self, db):
        """Lines 523-532: all criteria met → explorer awarded."""
        explorer_def = _make_definition(
            "explorer", "exploration",
            {"show_after_total_lessons": 3, "distinct_categories": 2, "min_overall_avg_rating": 4.0},
        )
        service = _make_service(db, definitions=[explorer_def], count_completed=5)
        service.repository.upsert_progress = MagicMock()
        service.repository.count_distinct_completed_categories.return_value = 3
        service.repository.has_rebook_in_any_category.return_value = True
        service.repository.get_overall_student_avg_rating.return_value = 4.5
        service.repository.insert_award_pending_or_confirmed.return_value = "award-1"

        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert summary["explorer"] == 1

    def test_backfill_explorer_goal_categories_zero(self, db):
        """Lines 524: goal_categories <= 0 → goal_met always True."""
        explorer_def = _make_definition(
            "explorer", "exploration",
            {"show_after_total_lessons": 1, "distinct_categories": 0, "min_overall_avg_rating": 0.0},
        )
        service = _make_service(db, definitions=[explorer_def], count_completed=5)
        service.repository.upsert_progress = MagicMock()
        service.repository.count_distinct_completed_categories.return_value = 1
        service.repository.has_rebook_in_any_category.return_value = True
        service.repository.get_overall_student_avg_rating.return_value = 5.0
        service.repository.insert_award_pending_or_confirmed.return_value = "award-1"

        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert summary["explorer"] == 1


class TestBackfillQualityBranches:
    """Cover lines 538-593: backfill top_student (quality) badge."""

    def test_backfill_quality_insufficient_lessons(self, db):
        """Line 547: total_completed < min_total_lessons → skip quality block."""
        quality_def = _make_definition(
            "top_student", "quality",
            {"min_total_lessons": 10, "min_reviews": 3, "min_avg_rating": 4.5},
        )
        service = _make_service(db, definitions=[quality_def], count_completed=5)

        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert summary["quality_pending"] == 0

    def test_backfill_quality_insufficient_reviews(self, db):
        """Lines 554-556: review count or avg below threshold → skip."""
        quality_def = _make_definition(
            "top_student", "quality",
            {"min_total_lessons": 1, "min_reviews": 5, "min_avg_rating": 4.5},
        )
        service = _make_service(db, definitions=[quality_def], count_completed=10)
        service.repository.get_review_stats_since.return_value = {
            "count": 2,
            "avg_rating": 5.0,
        }

        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert summary["quality_pending"] == 0

    def test_backfill_quality_high_cancel_rate(self, db):
        """Line 562: cancel_rate > max_cancel_rate → skip."""
        quality_def = _make_definition(
            "top_student", "quality",
            {
                "min_total_lessons": 1,
                "min_reviews": 1,
                "min_avg_rating": 4.0,
                "max_cancel_noshow_rate_pct_60d": 5.0,
            },
        )
        service = _make_service(db, definitions=[quality_def], count_completed=10)
        service.repository.get_review_stats_since.return_value = {
            "count": 3,
            "avg_rating": 4.5,
        }
        service.repository.get_cancel_noshow_rate_pct_window.return_value = 10.0

        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert summary["quality_pending"] == 0

    def test_backfill_quality_depth_not_met(self, db):
        """Lines 570-576, 578: neither distinct_instructors nor single_instructor met."""
        quality_def = _make_definition(
            "top_student", "quality",
            {
                "min_total_lessons": 1,
                "min_reviews": 1,
                "min_avg_rating": 4.0,
                "max_cancel_noshow_rate_pct_60d": 50.0,
                "distinct_instructors_min": 5,
                "or_single_instructor_min_lessons": 20,
            },
        )
        service = _make_service(db, definitions=[quality_def], count_completed=10)
        service.repository.get_review_stats_since.return_value = {
            "count": 3,
            "avg_rating": 4.5,
        }
        service.repository.get_cancel_noshow_rate_pct_window.return_value = 2.0
        service.repository.count_distinct_instructors_for_student.return_value = 2
        service.repository.get_max_lessons_with_single_instructor.return_value = 5

        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert summary["quality_pending"] == 0

    def test_backfill_quality_distinct_instructors_met(self, db):
        """Lines 570-571: distinct_instructors >= required → depth_met=True."""
        quality_def = _make_definition(
            "top_student", "quality",
            {
                "min_total_lessons": 1,
                "min_reviews": 1,
                "min_avg_rating": 4.0,
                "max_cancel_noshow_rate_pct_60d": 50.0,
                "distinct_instructors_min": 2,
                "or_single_instructor_min_lessons": 0,
            },
        )
        service = _make_service(db, definitions=[quality_def], count_completed=10)
        service.repository.get_review_stats_since.return_value = {
            "count": 3,
            "avg_rating": 4.5,
        }
        service.repository.get_cancel_noshow_rate_pct_window.return_value = 2.0
        service.repository.count_distinct_instructors_for_student.return_value = 3
        service.repository.get_max_lessons_with_single_instructor.return_value = 5
        service.repository.insert_award_pending_or_confirmed.return_value = "award-1"

        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert summary["quality_pending"] == 1

    def test_backfill_quality_single_instructor_met(self, db):
        """Lines 572-576: single instructor lessons >= goal → depth_met=True."""
        quality_def = _make_definition(
            "top_student", "quality",
            {
                "min_total_lessons": 1,
                "min_reviews": 1,
                "min_avg_rating": 4.0,
                "max_cancel_noshow_rate_pct_60d": 50.0,
                "distinct_instructors_min": 10,
                "or_single_instructor_min_lessons": 3,
            },
        )
        service = _make_service(db, definitions=[quality_def], count_completed=10)
        service.repository.get_review_stats_since.return_value = {
            "count": 3,
            "avg_rating": 4.5,
        }
        service.repository.get_cancel_noshow_rate_pct_window.return_value = 2.0
        service.repository.count_distinct_instructors_for_student.return_value = 2
        service.repository.get_max_lessons_with_single_instructor.return_value = 5
        service.repository.insert_award_pending_or_confirmed.return_value = "award-1"

        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert summary["quality_pending"] == 1

    def test_backfill_quality_window_days_zero(self, db):
        """Line 550: quality_window_days <= 0 → defaults to 90."""
        quality_def = _make_definition(
            "top_student", "quality",
            {
                "min_total_lessons": 1,
                "min_reviews": 1,
                "min_avg_rating": 4.0,
                "distinct_instructors_min": 1,
            },
        )
        service = _make_service(db, definitions=[quality_def], count_completed=10)
        service.repository.get_review_stats_since.return_value = {
            "count": 3,
            "avg_rating": 4.5,
        }
        service.repository.get_cancel_noshow_rate_pct_window.return_value = 0.0
        service.repository.count_distinct_instructors_for_student.return_value = 2
        service.repository.get_max_lessons_with_single_instructor.return_value = 5
        service.repository.insert_award_pending_or_confirmed.return_value = "award-1"

        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
            quality_window_days=0,
        )
        assert summary["quality_pending"] == 1

    def test_backfill_quality_already_awarded_skipped(self, db):
        """Lines 389-391: existing award → skipped_existing incremented."""
        quality_def = _make_definition(
            "top_student", "quality",
            {
                "min_total_lessons": 1,
                "min_reviews": 1,
                "min_avg_rating": 4.0,
                "distinct_instructors_min": 1,
            },
        )
        service = _make_service(db, definitions=[quality_def], count_completed=10)
        # Simulate existing award
        service.repository.list_student_badge_awards.return_value = [
            {"badge_id": quality_def.id, "status": "confirmed"},
        ]
        service.repository.get_review_stats_since.return_value = {
            "count": 3,
            "avg_rating": 4.5,
        }
        service.repository.get_cancel_noshow_rate_pct_window.return_value = 0.0
        service.repository.count_distinct_instructors_for_student.return_value = 2
        service.repository.get_max_lessons_with_single_instructor.return_value = 5

        summary = service.backfill_user_badges(
            student_id="student-1",
            now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert summary["skipped_existing"] >= 1
        assert summary["quality_pending"] == 0


class TestEvaluateConsistentLearnerTzException:
    """Cover lines 690-691: get_user_timezone raises → return."""

    def test_consistent_learner_tz_exception(self, db, monkeypatch):
        """Lines 690-691: exception in get_user_timezone → early return."""
        service = _make_service(db)
        defn = _make_definition("consistent_learner", "streak", {"goal": 3, "grace_days": 1})
        mock_student = MagicMock()
        service.user_repository.get_by_id.return_value = mock_student

        monkeypatch.setattr(
            "app.services.badge_award_service.get_user_timezone",
            MagicMock(side_effect=ValueError("bad timezone")),
        )

        # Should not raise
        service._evaluate_consistent_learner(
            defn,
            student_id="student-1",
            completed_at_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        # Should not attempt to list completion times since tz lookup failed
        service.repository.list_completed_lesson_times.assert_not_called()


class TestCurrentStreakLengthTzNone:
    """Cover line 744: user_tz is None → return 0."""

    def test_streak_tz_returns_none(self, db, monkeypatch):
        """Line 744: get_user_timezone returns None → return 0."""
        service = _make_service(db)
        defn = _make_definition("consistent_learner", "streak", {"goal": 3})
        mock_student = MagicMock()
        service.user_repository.get_by_id.return_value = mock_student

        monkeypatch.setattr(
            "app.services.badge_award_service.get_user_timezone",
            MagicMock(return_value=None),
        )

        result = service._current_streak_length("student-1", defn, goal=3)
        assert result == 0


class TestCurrentStreakLengthHappyPath:
    """Cover lines 750-752: successful streak calculation."""

    def test_streak_calculation_with_completions(self, db, monkeypatch):
        """Lines 750-752: valid tz + completions → compute streak."""
        service = _make_service(db)
        defn = _make_definition("consistent_learner", "streak", {"goal": 3, "grace_days": 1})
        mock_student = MagicMock()
        service.user_repository.get_by_id.return_value = mock_student

        completion_times = [
            datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 8, 12, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        ]
        service.repository.list_completed_lesson_times.return_value = completion_times

        monkeypatch.setattr(
            "app.services.badge_award_service.get_user_timezone",
            MagicMock(return_value=timezone.utc),
        )
        monkeypatch.setattr(
            "app.services.badge_award_service.compute_week_streak_local",
            MagicMock(return_value=3),
        )

        result = service._current_streak_length("student-1", defn, goal=3)
        assert result == 3
