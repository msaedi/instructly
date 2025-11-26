# backend/tests/routes/test_public_robust_example.py
"""
Example of how to write robust tests that work with any configuration.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.core.config import settings
from tests._utils.bitmap_avail import seed_day
from tests.helpers.configuration_helpers import (
    assert_full_detail_response,
    assert_minimal_detail_response,
    assert_summary_detail_response,
    override_public_api_config,
)


class TestPublicAPIRobustExample:
    """Examples of configuration-aware tests."""

    def test_adapts_to_current_configuration(self, client, db: Session, test_instructor):
        """Test that adapts to whatever configuration is active."""
        # Create test data using bitmap storage
        today = date.today()
        seed_day(db, test_instructor.id, today, [("09:00", "10:00")])

        # Make request
        response = client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/availability", params={"start_date": today.isoformat()}
        )

        assert response.status_code == 200
        data = response.json()

        # Use appropriate assertions based on current config
        if settings.public_availability_detail_level == "full":
            assert_full_detail_response(data)
            # Can do specific full-detail checks
            assert len(data["availability_by_date"][today.isoformat()]["available_slots"]) == 1
        elif settings.public_availability_detail_level == "summary":
            assert_summary_detail_response(data)
            # Can do specific summary checks
            assert data["availability_summary"][today.isoformat()]["morning_available"] is True
        else:  # minimal
            assert_minimal_detail_response(data)
            # Can do specific minimal checks
            assert data["has_availability"] is True

    def test_with_forced_configuration(self, client, db: Session, test_instructor):
        """Test that forces a specific configuration using context manager."""
        # Fixed: Removed non-existent fixture and use context manager instead
        with override_public_api_config(detail_level="full"):
            # This test will ALWAYS use full detail, regardless of .env settings
            today = date.today()
            seed_day(db, test_instructor.id, today, [("09:00", "10:00")])

            response = client.get(
                f"/api/v1/public/instructors/{test_instructor.id}/availability", params={"start_date": today.isoformat()}
            )

            assert response.status_code == 200
            data = response.json()

            # Can safely assume full detail structure
            assert "availability_by_date" in data
            assert today.isoformat() in data["availability_by_date"]
            assert len(data["availability_by_date"][today.isoformat()]["available_slots"]) == 1

    def test_with_context_manager_override(self, client, db: Session, test_instructor):
        """Test using context manager for temporary override."""
        today = date.today()
        seed_day(db, test_instructor.id, today, [("09:00", "10:00")])

        # Test with multiple configurations in one test
        with override_public_api_config(detail_level="minimal", days=7):
            response = client.get(
                f"/api/v1/public/instructors/{test_instructor.id}/availability", params={"start_date": today.isoformat()}
            )

            assert response.status_code == 200
            data = response.json()

            # Minimal response checks
            assert "has_availability" in data
            assert data["has_availability"] is True
            assert "availability_by_date" not in data

        # Now test with different config
        with override_public_api_config(detail_level="summary"):
            response = client.get(
                f"/api/v1/public/instructors/{test_instructor.id}/availability", params={"start_date": today.isoformat()}
            )

            assert response.status_code == 200
            data = response.json()

            # Summary response checks
            assert "availability_summary" in data
            assert data["detail_level"] == "summary"

    def test_critical_functionality_all_detail_levels(self, client, db: Session, test_instructor):
        """Test critical functionality works with all detail levels."""
        # Create test data using bitmap storage
        today = date.today()
        seed_day(db, test_instructor.id, today, [("09:00", "10:00")])

        # Test with each detail level
        for detail_level in ["full", "summary", "minimal"]:
            with override_public_api_config(detail_level=detail_level):
                response = client.get(
                    f"/api/v1/public/instructors/{test_instructor.id}/availability",
                    params={"start_date": today.isoformat()},
                )

                assert response.status_code == 200, f"Failed with detail_level={detail_level}"
                data = response.json()

                # Common fields that should exist in all levels
                assert "instructor_id" in data
                assert data["instructor_id"] == test_instructor.id
                assert "instructor_first_name" in data
                assert "instructor_last_initial" in data

                # The response structure differs, but all should indicate availability exists
                if detail_level == "full":
                    has_slots = len(data["availability_by_date"][today.isoformat()]["available_slots"]) > 0
                    assert has_slots is True
                elif detail_level == "summary":
                    has_availability = data["availability_summary"][today.isoformat()]["total_hours"] > 0
                    assert has_availability is True
                else:  # minimal
                    assert data["has_availability"] is True
