# backend/tests/integration/test_instructor_service_all_services.py

from sqlalchemy.orm import Session

from app.models import ServiceCatalog, ServiceCategory
from app.services.instructor_service import InstructorService


class TestInstructorServiceAllServices:
    """Test suite for InstructorService.get_all_services_with_instructors method

    These are integration tests that use real database fixtures.
    """

    def test_get_all_services_with_instructors_from_cache(self, db: Session, mock_cache_service):
        """Test that cached data is returned when available"""
        # Setup cached data
        cached_data = {"categories": [{"id": 1, "name": "Cached Category"}], "metadata": {"cached": True}}
        mock_cache_service.get.return_value = cached_data

        # Create service
        instructor_service = InstructorService(db)
        instructor_service.cache_service = mock_cache_service

        # Call the method
        result = instructor_service.get_all_services_with_instructors()

        # Verify cache was checked
        mock_cache_service.get.assert_called_once_with("catalog:all-services-with-instructors")

        # Verify cached data was returned
        assert result == cached_data

    def test_get_all_services_with_instructors_with_data(
        self, db: Session, mock_cache_service, sample_instructors_with_services
    ):
        """Test fetching data when not in cache with real database data"""
        # No cached data
        mock_cache_service.get.return_value = None

        # Create service
        instructor_service = InstructorService(db)
        instructor_service.cache_service = mock_cache_service

        # Call the method
        result = instructor_service.get_all_services_with_instructors()

        # Verify structure
        assert "categories" in result
        assert "metadata" in result
        assert len(result["categories"]) >= 2  # At least Music and Sports & Fitness

        # Verify Music category
        music_cat = next((c for c in result["categories"] if c["slug"] == "music"), None)
        assert music_cat is not None
        assert music_cat["name"] == "Music"
        assert len(music_cat["services"]) >= 1  # At least Piano

        # Check Piano service has instructor
        piano_service = next((s for s in music_cat["services"] if s["slug"] == "piano"), None)
        assert piano_service is not None
        assert piano_service["active_instructors"] >= 1
        assert piano_service["instructor_count"] >= 1

        # Verify Sports & Fitness category
        sports_cat = next((c for c in result["categories"] if c["slug"] == "sports-fitness"), None)
        assert sports_cat is not None
        assert sports_cat["name"] == "Sports & Fitness"

        # Check Yoga service has instructor
        yoga_service = next((s for s in sports_cat["services"] if s["slug"] == "yoga"), None)
        assert yoga_service is not None
        assert yoga_service["active_instructors"] >= 1

        # Check Personal Training service exists
        # Note: We don't create a Personal Training instructor in our fixture,
        # but other tests or seed data might, so we just check the field exists
        pt_service = next((s for s in sports_cat["services"] if s["slug"] == "personal-training"), None)
        if pt_service:
            assert "active_instructors" in pt_service
            assert pt_service["active_instructors"] >= 0

        # Verify caching
        mock_cache_service.set.assert_called_once()
        # Check the arguments passed to cache.set() - it uses keyword args
        call_args = mock_cache_service.set.call_args
        if call_args[0]:  # positional args
            cache_key = call_args[0][0]
            call_args[0][1]
            ttl = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("ttl", 300)
        else:  # keyword args
            cache_key = call_args[1]["key"]
            call_args[1]["value"]
            ttl = call_args[1].get("ttl", 300)
        assert cache_key == "catalog:all-services-with-instructors"
        assert ttl == 300  # 5 minutes

        # Verify metadata
        assert result["metadata"]["total_categories"] >= 2
        assert result["metadata"]["total_services"] >= 3
        assert "updated_at" in result["metadata"]

    def test_get_all_services_with_instructors_service_ordering(
        self, db: Session, mock_cache_service, sample_instructors_with_services
    ):
        """Test that services are ordered correctly (active first, then by display order)"""
        mock_cache_service.get.return_value = None

        # Create service
        instructor_service = InstructorService(db)
        instructor_service.cache_service = mock_cache_service

        # Call the method
        result = instructor_service.get_all_services_with_instructors()

        # Check each category's services
        for category in result["categories"]:
            services = category["services"]
            if len(services) > 1:
                # Check that active services come before inactive ones
                active_services = [s for s in services if s["active_instructors"] > 0]
                inactive_services = [s for s in services if s["active_instructors"] == 0]

                # Active services should appear before inactive ones
                if active_services and inactive_services:
                    last_active_index = max(services.index(s) for s in active_services)
                    first_inactive_index = min(services.index(s) for s in inactive_services)
                    assert last_active_index < first_inactive_index

    def test_get_all_services_with_instructors_empty_categories(self, db: Session, mock_cache_service):
        """Test handling when no categories exist"""
        mock_cache_service.get.return_value = None

        # Clear all categories and services
        db.query(ServiceCatalog).delete()
        db.query(ServiceCategory).delete()
        db.commit()

        # Create service
        instructor_service = InstructorService(db)
        instructor_service.cache_service = mock_cache_service

        result = instructor_service.get_all_services_with_instructors()

        assert result["categories"] == []
        assert result["metadata"]["total_categories"] == 0
        assert result["metadata"]["total_services"] == 0

    def test_get_all_services_with_instructors_analytics_data(
        self, db: Session, mock_cache_service, sample_instructors_with_services
    ):
        """Test that analytics data is properly included"""
        mock_cache_service.get.return_value = None

        # Create service
        instructor_service = InstructorService(db)
        instructor_service.cache_service = mock_cache_service

        # Call the method
        result = instructor_service.get_all_services_with_instructors()

        # Check that services have analytics fields
        for category in result["categories"]:
            for service in category["services"]:
                # All services should have these fields
                assert "active_instructors" in service
                assert "instructor_count" in service
                assert "demand_score" in service
                assert "is_trending" in service

                # Price fields should only exist for services with instructors
                if service["active_instructors"] > 0:
                    assert "actual_min_price" in service
                    assert "actual_max_price" in service
                    assert service["actual_min_price"] is not None
                    assert service["actual_max_price"] is not None
                    assert service["actual_min_price"] <= service["actual_max_price"]
                else:
                    # Services without instructors may not have price fields
                    # or have them set to None
                    if "actual_min_price" in service:
                        assert service["actual_min_price"] is None
                    if "actual_max_price" in service:
                        assert service["actual_max_price"] is None
