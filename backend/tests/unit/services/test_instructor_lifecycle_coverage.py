# backend/tests/unit/services/test_instructor_lifecycle_coverage.py
"""
Additional coverage tests for InstructorLifecycleService.

This file extends tests/services/test_instructor_lifecycle_service.py
to cover previously missed lines:
- Line 57: return True when event_type not in FUNNEL_STAGES
- Line 69, 87, 94, 101, 112: Early returns when _should_record_stage returns False
- Lines 118-122: Paused idempotency logic
- Lines 127-130: Reactivated idempotency logic
- Lines 167-168: Exception handling for invalid founding_instructor_cap config
- Line 207: Skipping stuck instructor rows with no stage value
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.repositories.instructor_lifecycle_repository import InstructorLifecycleRepository
from app.services.instructor_lifecycle_service import (
    FUNNEL_STAGES,
    STAGE_DESCRIPTIONS,
    InstructorLifecycleService,
)


class TestShouldRecordStage:
    """Tests for _should_record_stage internal logic."""

    def test_non_funnel_event_always_recorded(self, db, test_instructor):
        """Line 57: Non-funnel events (like 'paused') should always return True."""
        service = InstructorLifecycleService(db)

        # 'paused' is NOT in FUNNEL_STAGES, so should always be recorded
        result = service._should_record_stage(test_instructor.id, "paused")
        assert result is True

        # 'reactivated' is also not in FUNNEL_STAGES
        result = service._should_record_stage(test_instructor.id, "reactivated")
        assert result is True

    def test_backward_progression_blocked(self, db, test_instructor):
        """Moving backward in the funnel should be blocked."""
        service = InstructorLifecycleService(db)

        # Record forward progression
        service.record_registration(test_instructor.id)
        service.record_profile_submitted(test_instructor.id)

        # Trying to go back should be blocked
        result = service._should_record_stage(test_instructor.id, "registered")
        assert result is False

    def test_current_stage_not_in_funnel(self, db, test_instructor):
        """When current stage is not a funnel stage, new events should be allowed."""
        service = InstructorLifecycleService(db)
        repo = InstructorLifecycleRepository(db)

        # Record a non-funnel event directly
        repo.record_event(test_instructor.id, "paused")

        # Now any funnel stage should be recordable (return True on line 62)
        result = service._should_record_stage(test_instructor.id, "registered")
        assert result is True


class TestEarlyReturnPaths:
    """Tests for early return paths when _should_record_stage returns False."""

    def test_registration_blocked_when_past_stage(self, db, test_instructor):
        """Line 69: Early return for registration."""
        service = InstructorLifecycleService(db)
        repo = InstructorLifecycleRepository(db)

        service.record_registration(test_instructor.id)
        service.record_profile_submitted(test_instructor.id)
        initial_count = len(repo.get_events_for_user(test_instructor.id))

        # Try to record registration again (we're past it)
        service.record_registration(test_instructor.id)

        final_count = len(repo.get_events_for_user(test_instructor.id))
        assert final_count == initial_count

    def test_services_configured_blocked_when_past_stage(self, db, test_instructor):
        """Line 87: Early return for services_configured."""
        service = InstructorLifecycleService(db)
        repo = InstructorLifecycleRepository(db)

        service.record_registration(test_instructor.id)
        service.record_profile_submitted(test_instructor.id)
        service.record_services_configured(test_instructor.id)
        service.record_bgc_initiated(test_instructor.id)
        initial_count = len(repo.get_events_for_user(test_instructor.id))

        # Try to record services_configured again
        service.record_services_configured(test_instructor.id)

        final_count = len(repo.get_events_for_user(test_instructor.id))
        assert final_count == initial_count

    def test_bgc_initiated_blocked_when_past_stage(self, db, test_instructor):
        """Line 94: Early return for bgc_initiated."""
        service = InstructorLifecycleService(db)
        repo = InstructorLifecycleRepository(db)

        service.record_registration(test_instructor.id)
        service.record_bgc_initiated(test_instructor.id)
        service.record_bgc_completed(test_instructor.id, status="passed")
        initial_count = len(repo.get_events_for_user(test_instructor.id))

        # Try to record bgc_initiated again
        service.record_bgc_initiated(test_instructor.id)

        final_count = len(repo.get_events_for_user(test_instructor.id))
        assert final_count == initial_count

    def test_bgc_completed_blocked_when_past_stage(self, db, test_instructor):
        """Line 101: Early return for bgc_completed."""
        service = InstructorLifecycleService(db)
        repo = InstructorLifecycleRepository(db)

        service.record_registration(test_instructor.id)
        service.record_bgc_completed(test_instructor.id, status="passed")
        service.record_went_live(test_instructor.id)
        initial_count = len(repo.get_events_for_user(test_instructor.id))

        # Try to record bgc_completed again
        service.record_bgc_completed(test_instructor.id, status="passed")

        final_count = len(repo.get_events_for_user(test_instructor.id))
        assert final_count == initial_count

    def test_went_live_blocked_when_already_live(self, db, test_instructor):
        """Line 112: Early return for went_live."""
        service = InstructorLifecycleService(db)
        repo = InstructorLifecycleRepository(db)

        service.record_registration(test_instructor.id)
        service.record_went_live(test_instructor.id)
        initial_count = len(repo.get_events_for_user(test_instructor.id))

        # Try to record went_live again
        service.record_went_live(test_instructor.id)

        final_count = len(repo.get_events_for_user(test_instructor.id))
        assert final_count == initial_count


class TestPausedIdempotency:
    """Tests for paused idempotency logic (lines 118-122)."""

    def test_duplicate_pause_blocked(self, db, test_instructor):
        """Lines 118-120: Should NOT record if already paused."""
        service = InstructorLifecycleService(db)
        repo = InstructorLifecycleRepository(db)

        service.record_registration(test_instructor.id)
        service.record_went_live(test_instructor.id)
        service.record_paused(test_instructor.id, reason="first pause")
        initial_count = len(repo.get_events_for_user(test_instructor.id))

        # Try to pause again
        service.record_paused(test_instructor.id, reason="second pause")

        final_count = len(repo.get_events_for_user(test_instructor.id))
        assert final_count == initial_count

    def test_pause_without_reason(self, db, test_instructor):
        """Lines 121-122: Should record paused without reason (metadata=None)."""
        service = InstructorLifecycleService(db)
        repo = InstructorLifecycleRepository(db)

        service.record_registration(test_instructor.id)
        service.record_went_live(test_instructor.id)
        service.record_paused(test_instructor.id)  # No reason

        event = repo.get_latest_event_for_user(test_instructor.id)
        assert event is not None
        assert event.event_type == "paused"
        assert event.metadata_json is None

    def test_pause_with_reason(self, db, test_instructor):
        """Should record paused with reason in metadata."""
        service = InstructorLifecycleService(db)
        repo = InstructorLifecycleRepository(db)

        service.record_registration(test_instructor.id)
        service.record_went_live(test_instructor.id)
        service.record_paused(test_instructor.id, reason="vacation")

        event = repo.get_latest_event_for_user(test_instructor.id)
        assert event is not None
        assert event.event_type == "paused"
        assert event.metadata_json["reason"] == "vacation"


class TestReactivatedIdempotency:
    """Tests for reactivated idempotency logic (lines 127-130)."""

    def test_duplicate_reactivation_blocked(self, db, test_instructor):
        """Lines 127-130: Should NOT record if already reactivated."""
        service = InstructorLifecycleService(db)
        repo = InstructorLifecycleRepository(db)

        service.record_registration(test_instructor.id)
        service.record_went_live(test_instructor.id)
        service.record_paused(test_instructor.id)
        service.record_reactivated(test_instructor.id)
        initial_count = len(repo.get_events_for_user(test_instructor.id))

        # Try to reactivate again
        service.record_reactivated(test_instructor.id)

        final_count = len(repo.get_events_for_user(test_instructor.id))
        assert final_count == initial_count

    def test_reactivation_after_pause(self, db, test_instructor):
        """Should record reactivation after pause."""
        service = InstructorLifecycleService(db)
        repo = InstructorLifecycleRepository(db)

        service.record_registration(test_instructor.id)
        service.record_went_live(test_instructor.id)
        service.record_paused(test_instructor.id)
        service.record_reactivated(test_instructor.id)

        event = repo.get_latest_event_for_user(test_instructor.id)
        assert event is not None
        assert event.event_type == "reactivated"


class TestFoundingCapConfigExceptions:
    """Tests for founding_cap config exception handling (lines 167-168)."""

    def test_handles_type_error_in_founding_cap(self, db, test_instructor):
        """Line 167-168: Should handle TypeError (None value)."""
        service = InstructorLifecycleService(db)

        with patch("app.services.instructor_lifecycle_service.ConfigService") as MockConfigService:
            mock_config = MagicMock()
            mock_config.get_pricing_config.return_value = (
                {"founding_instructor_cap": None},  # None causes TypeError
                datetime.now(timezone.utc),
            )
            MockConfigService.return_value = mock_config

            with patch("app.services.instructor_lifecycle_service.InstructorProfileRepository") as MockRepo:
                mock_repo = MagicMock()
                mock_repo.count_founding_instructors.return_value = 0
                MockRepo.return_value = mock_repo

                summary = service.get_funnel_summary()
                assert summary["founding_cap"]["cap"] == 100  # Default

    def test_handles_value_error_in_founding_cap(self, db, test_instructor):
        """Line 167-168: Should handle ValueError (non-numeric string)."""
        service = InstructorLifecycleService(db)

        with patch("app.services.instructor_lifecycle_service.ConfigService") as MockConfigService:
            mock_config = MagicMock()
            mock_config.get_pricing_config.return_value = (
                {"founding_instructor_cap": "not_a_number"},  # String causes ValueError
                datetime.now(timezone.utc),
            )
            MockConfigService.return_value = mock_config

            with patch("app.services.instructor_lifecycle_service.InstructorProfileRepository") as MockRepo:
                mock_repo = MagicMock()
                mock_repo.count_founding_instructors.return_value = 0
                MockRepo.return_value = mock_repo

                summary = service.get_funnel_summary()
                assert summary["founding_cap"]["cap"] == 100  # Default


class TestStuckInstructorsNoStage:
    """Tests for skipping rows without stage value (line 207)."""

    def test_skips_rows_without_stage(self, db, test_instructor):
        """Line 207: Should skip rows where stage is None/empty."""
        service = InstructorLifecycleService(db)

        with patch.object(
            service.repository,
            "get_stuck_instructors",
            return_value=[
                {"user_id": "1", "stage": "registered", "days_stuck": 10},
                {"user_id": "2", "stage": None, "days_stuck": 10},  # No stage
                {"user_id": "3", "stage": "", "days_stuck": 10},  # Empty stage
            ],
        ):
            result = service.get_stuck_instructors()

            # Summary should only include the row with valid stage
            summary_stages = {s["stage"] for s in result["summary"]}
            assert "registered" in summary_stages
            assert None not in summary_stages
            assert "" not in summary_stages


class TestPauseReactivationCycle:
    """Tests for pause/reactivation cycle behavior."""

    def test_multiple_pause_reactivation_cycles(self, db, test_instructor):
        """Should allow multiple pause/reactivation cycles."""
        service = InstructorLifecycleService(db)
        repo = InstructorLifecycleRepository(db)

        service.record_registration(test_instructor.id)
        service.record_went_live(test_instructor.id)

        # First cycle
        service.record_paused(test_instructor.id, reason="vacation")
        service.record_reactivated(test_instructor.id)

        # Second cycle
        service.record_paused(test_instructor.id, reason="personal")
        service.record_reactivated(test_instructor.id)

        events = repo.get_events_for_user(test_instructor.id)
        event_types = [e.event_type for e in events]

        assert event_types.count("paused") == 2
        assert event_types.count("reactivated") == 2


class TestStageDescriptions:
    """Tests for stage descriptions constant."""

    def test_all_funnel_stages_have_descriptions(self):
        """All funnel stages should have descriptions."""
        for stage in FUNNEL_STAGES:
            assert stage in STAGE_DESCRIPTIONS, f"Missing description for {stage}"

    def test_non_funnel_stages_have_descriptions(self):
        """Paused and reactivated should have descriptions."""
        assert "paused" in STAGE_DESCRIPTIONS
        assert "reactivated" in STAGE_DESCRIPTIONS
