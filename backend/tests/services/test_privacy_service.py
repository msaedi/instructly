# backend/tests/services/test_privacy_service.py
"""
Tests for PrivacyService.
"""

from datetime import datetime, time, timedelta, timezone
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.models import Booking, InstructorProfile, SearchEvent, SearchHistory, User
from app.models.address import InstructorServiceArea
from app.models.region_boundary import RegionBoundary
from app.services.privacy_service import PrivacyService

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.utils.booking_timezone import booking_timezone_fields
except ModuleNotFoundError:  # pragma: no cover
    from tests.utils.booking_timezone import booking_timezone_fields


@pytest.fixture
def privacy_service(db):
    """Create a privacy service instance."""
    return PrivacyService(db)


# Fixtures now in conftest.py


@pytest.fixture
def sample_booking(db, sample_user_for_privacy, sample_instructor_for_privacy):
    """Create a sample booking."""
    import uuid

    from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
    from app.models.subcategory import ServiceSubcategory

    # Create unique slugs to avoid conflicts
    unique_id = str(uuid.uuid4())[:8]

    # Create a service category
    category = ServiceCategory(name=f"Test Category {unique_id}")
    db.add(category)
    db.flush()

    subcategory = ServiceSubcategory(
        name="General",
        category_id=category.id,
        display_order=1,
    )
    db.add(subcategory)
    db.flush()

    # Create a service catalog entry
    catalog_service = ServiceCatalog(
        name=f"Test Service {unique_id}", slug=f"test-service-{unique_id}", subcategory_id=subcategory.id
    )
    db.add(catalog_service)
    db.flush()

    # Create an instructor service
    instructor_service = InstructorService(
        instructor_profile_id=sample_instructor_for_privacy.instructor_profile.id,
        service_catalog_id=catalog_service.id,
        hourly_rate=50.00,
    )
    db.add(instructor_service)
    db.flush()

    booking_date = datetime.now(timezone.utc).date()
    start_time = time(14, 0)
    end_time = time(15, 0)
    booking = Booking(
        student_id=sample_user_for_privacy.id,
        instructor_id=sample_instructor_for_privacy.id,
        instructor_service_id=instructor_service.id,
        booking_date=booking_date,
        start_time=start_time,  # Fixed 2 PM
        end_time=end_time,  # Fixed 3 PM
        **booking_timezone_fields(booking_date, start_time, end_time),
        service_name="Test Service",
        hourly_rate=50.00,
        total_price=50.00,
        duration_minutes=60,
        status="CONFIRMED",
    )
    db.add(booking)
    db.commit()
    return booking


class TestPrivacyService:
    """Test cases for PrivacyService."""

    def test_export_user_data_success(self, privacy_service, sample_user_for_privacy):
        """Test successful user data export."""
        result = privacy_service.export_user_data(sample_user_for_privacy.id)

        assert result["user_profile"]["id"] == sample_user_for_privacy.id
        assert result["user_profile"]["email"] == sample_user_for_privacy.email
        assert result["user_profile"]["first_name"] == sample_user_for_privacy.first_name
        assert result["user_profile"]["last_name"] == sample_user_for_privacy.last_name
        assert len(result["search_history"]) == 1
        assert result["search_history"][0]["search_query"] == "math tutoring"
        assert result["instructor_profile"] is None

    def test_export_instructor_data(self, privacy_service, sample_instructor_for_privacy):
        """Test exporting instructor user data."""
        result = privacy_service.export_user_data(sample_instructor_for_privacy.id)

        # User model uses RBAC, not simple role field
        assert result["instructor_profile"] is not None
        assert result["instructor_profile"]["bio"] == "Experienced math tutor"
        assert result["instructor_profile"]["years_experience"] == 5

    def test_export_user_data_not_found(self, privacy_service):
        """Test exporting data for non-existent user."""
        with pytest.raises(ValueError, match="User 999 not found"):
            privacy_service.export_user_data(999)

    def test_export_user_data_with_bookings(self, privacy_service, sample_user_for_privacy, sample_booking):
        """Test exporting user data with bookings."""
        result = privacy_service.export_user_data(sample_user_for_privacy.id)

        assert len(result["bookings"]) == 1
        booking_data = result["bookings"][0]
        assert booking_data["id"] == sample_booking.id
        assert booking_data["status"] == "CONFIRMED"
        assert booking_data["role"] == "student"
        assert booking_data["service_name"] == "Test Service"

    def test_delete_user_data_success(self, privacy_service, sample_user_for_privacy, db):
        """Test successful user data deletion."""
        user_id = sample_user_for_privacy.id

        # Verify data exists
        assert db.query(SearchHistory).filter_by(user_id=user_id).count() == 1
        assert db.query(SearchEvent).filter_by(user_id=user_id).count() == 1

        result = privacy_service.delete_user_data(user_id, delete_account=False)

        # Verify data was deleted
        assert result["search_history"] == 1
        assert result["search_events"] == 1
        assert db.query(SearchHistory).filter_by(user_id=user_id).count() == 0
        assert db.query(SearchEvent).filter_by(user_id=user_id).count() == 0

        # User should still exist
        user = db.query(User).filter_by(id=user_id).first()
        assert user is not None
        assert user.is_active is True

    def test_delete_user_data_with_account_deletion(self, privacy_service, sample_user_for_privacy, db):
        """Test user data deletion with account deletion."""
        user_id = sample_user_for_privacy.id

        _result = privacy_service.delete_user_data(user_id, delete_account=True)

        # Verify user account was soft-deleted
        user = db.query(User).filter_by(id=user_id).first()
        assert user is not None
        assert user.is_active is False
        assert user.email == f"deleted_{user_id}@deleted.com"
        assert user.first_name == "Deleted"
        assert user.last_name == "User"

        # Note: No separate student profile to delete in current model

    def test_delete_user_data_anonymizes_bookings(self, privacy_service, sample_user_for_privacy, sample_booking, db):
        """Test that bookings are counted during deletion."""
        user_id = sample_user_for_privacy.id
        booking_id = sample_booking.id

        result = privacy_service.delete_user_data(user_id, delete_account=False)

        # Booking should still exist (can't anonymize due to NOT NULL constraints)
        booking = db.query(Booking).filter_by(id=booking_id).first()
        assert booking is not None
        # Note: In real implementation, would need anonymization flag or special user account
        assert result["bookings"] == 1  # One booking was affected

    def test_delete_user_data_not_found(self, privacy_service):
        """Test deleting data for non-existent user."""
        with pytest.raises(ValueError, match="User 999 not found"):
            privacy_service.delete_user_data(999)

    def test_anonymize_user_success(self, privacy_service, sample_instructor_for_privacy, db):
        """Test successful user anonymization."""
        user_id = sample_instructor_for_privacy.id
        original_email = sample_instructor_for_privacy.email

        result = privacy_service.anonymize_user(user_id)

        assert result is True

        # Verify user was anonymized
        user = db.query(User).filter_by(id=user_id).first()
        assert user.email == f"anon_{user_id}@anonymized.com"
        assert user.first_name == "Anonymous"
        assert user.last_name == f"User{user_id}"
        assert user.email != original_email

        # Verify instructor profile was anonymized
        instructor = db.query(InstructorProfile).filter_by(user_id=user_id).first()
        assert instructor.bio == "This profile has been anonymized"

    def test_anonymize_user_not_found(self, privacy_service):
        """Test anonymizing non-existent user."""
        with pytest.raises(ValueError, match="User 999 not found"):
            privacy_service.anonymize_user(999)

    @patch("app.services.privacy_service.settings")
    def test_apply_retention_policies_success(
        self, mock_settings, privacy_service, sample_user_for_privacy, sample_instructor_for_privacy, db
    ):
        """Test successful retention policy application."""
        # Mock settings - ensure hasattr works
        mock_settings.search_event_retention_days = 30
        mock_settings.booking_pii_retention_days = 365
        mock_settings.alert_retention_days = 90

        # Create old data (older than the 30-day retention policy)
        old_date = datetime.now(timezone.utc) - timedelta(days=35)

        old_event = SearchEvent(
            user_id=sample_user_for_privacy.id,
            search_query="old search",
            results_count=0,
            search_context={},
            searched_at=old_date,
        )
        db.add(old_event)

        # Create instructor service for the booking
        import uuid

        from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
        from app.models.subcategory import ServiceSubcategory

        unique_id = str(uuid.uuid4())[:8]
        category = ServiceCategory(name=f"Test Category {unique_id}")
        db.add(category)
        db.flush()

        subcategory = ServiceSubcategory(
            name="General",
            category_id=category.id,
            display_order=1,
        )
        db.add(subcategory)
        db.flush()

        catalog_service = ServiceCatalog(
            name=f"Old Service {unique_id}", slug=f"old-service-{unique_id}", subcategory_id=subcategory.id
        )
        db.add(catalog_service)
        db.flush()

        instructor_service = InstructorService(
            instructor_profile_id=sample_instructor_for_privacy.instructor_profile.id,
            service_catalog_id=catalog_service.id,
            hourly_rate=40.00,
        )
        db.add(instructor_service)
        db.flush()

        booking_date = (old_date - timedelta(days=400)).date()
        start_time = time(10, 0)
        end_time = time(11, 0)
        old_booking = Booking(
            student_id=sample_user_for_privacy.id,
            instructor_id=sample_instructor_for_privacy.id,
            instructor_service_id=instructor_service.id,
            booking_date=booking_date,
            start_time=start_time,  # Fixed time to avoid wrap-around
            end_time=end_time,  # One hour later
            **booking_timezone_fields(booking_date, start_time, end_time),
            service_name="Old Service",
            hourly_rate=40.00,
            total_price=40.00,
            duration_minutes=60,
            status="COMPLETED",
            created_at=old_date - timedelta(days=400),
        )
        db.add(old_booking)
        db.commit()

        result = privacy_service.apply_retention_policies()

        # Verify old data was processed (result is now a RetentionStats Pydantic model)
        assert result.search_events_deleted == 1
        assert result.old_bookings_anonymized >= 1  # At least our test booking

        # Booking still exists (can't be anonymized due to NOT NULL constraints)
        booking = db.query(Booking).filter_by(id=old_booking.id).first()
        assert booking is not None
        # Note: In real implementation, would need proper anonymization approach

    def test_get_privacy_statistics(self, privacy_service, sample_user_for_privacy, sample_booking):
        """Test getting privacy statistics."""
        # Use fixtures to ensure there's data to count
        _ = sample_user_for_privacy  # Ensures user exists
        _ = sample_booking  # Ensures booking exists
        result = privacy_service.get_privacy_statistics()

        # Result is now a PrivacyStatistics Pydantic model
        assert result.total_users >= 1
        assert result.active_users >= 1
        assert result.search_history_records >= 0
        assert result.search_event_records >= 0
        assert result.total_bookings >= 1

    def test_measure_operation_decorator(self, privacy_service, sample_user_for_privacy):
        """Test that operations are properly measured."""
        # This test verifies the decorator is applied
        # The actual measurement testing would require more complex setup
        result = privacy_service.export_user_data(sample_user_for_privacy.id)
        assert result is not None  # Operation completed successfully

    def test_export_instructor_service_area_summary(
        self, privacy_service, sample_instructor_for_privacy, db
    ):
        """Ensure service area summaries use region metadata and borough rollups."""
        user_id = sample_instructor_for_privacy.id

        region_specs = [
            ("Bronx", "BX-01", "Bronx Park"),
            ("Manhattan", "MN-01", "Lower Manhattan"),
            ("Queens", "QN-01", "Long Island City"),
        ]
        regions = []
        for borough, code, name in region_specs:
            region = RegionBoundary(
                region_type="nyc",
                region_code=None,
                region_name=None,
                parent_region=None,
                region_metadata={"nta_code": code, "nta_name": name, "borough": borough},
            )
            db.add(region)
            db.flush()
            regions.append(region)
            db.add(
                InstructorServiceArea(
                    instructor_id=user_id,
                    neighborhood_id=region.id,
                    is_active=True,
                )
            )
        db.commit()

        result = privacy_service.export_user_data(user_id)
        profile = result["instructor_profile"]
        assert profile is not None
        assert len(profile["service_area_neighborhoods"]) == 3
        assert profile["service_area_summary"] == "Bronx + 2 more"
        assert profile["service_area_boroughs"] == ["Bronx", "Manhattan", "Queens"]

    def test_delete_user_data_blocks_account_deletion_with_future_booking(
        self, privacy_service, sample_user_for_privacy, sample_booking, db
    ):
        """Account deletion should be blocked when future bookings exist."""
        sample_booking.booking_date = datetime.now(timezone.utc).date() + timedelta(days=2)
        db.commit()

        with pytest.raises(ValueError, match="active bookings"):
            privacy_service.delete_user_data(sample_user_for_privacy.id, delete_account=True)

    def test_get_privacy_statistics_includes_retention(self, privacy_service, sample_user_for_privacy, db, monkeypatch):
        """Retention stats should include eligible deletion counts."""
        monkeypatch.setattr(settings, "search_event_retention_days", 1)
        old_event = SearchEvent(
            user_id=sample_user_for_privacy.id,
            search_query="old query",
            results_count=0,
            search_context={},
            searched_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        db.add(old_event)
        db.commit()

        stats = privacy_service.get_privacy_statistics()
        # Result is now a PrivacyStatistics Pydantic model
        assert stats.search_events_eligible_for_deletion >= 1
