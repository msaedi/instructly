# backend/tests/integration/repository_patterns/test_instructor_profile_query_patterns.py
"""
Document all query patterns used in InstructorProfileRepository.

This serves as the specification for the InstructorProfileRepository
query patterns and integration tests.
"""

from datetime import date, time, timedelta
from typing import List

import pytest
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload
from tests._utils.bitmap_avail import seed_day

from app.core.ulid_helper import generate_ulid
from app.models.address import InstructorServiceArea
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.region_boundary import RegionBoundary
from app.models.service_catalog import InstructorService as Service, ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory
from app.models.user import User

try:  # pragma: no cover - allow execution from backend/ or repo root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe

try:  # pragma: no cover - fallback when tests run from backend/
    from backend.tests.conftest import add_service_areas_for_boroughs  # noqa: I001
    from backend.tests.conftest import seed_service_areas_from_legacy  # noqa: I001
except ModuleNotFoundError:  # pragma: no cover
    from tests.conftest import add_service_areas_for_boroughs  # noqa: I001
    from tests.conftest import seed_service_areas_from_legacy  # noqa: I001


@pytest.fixture
def test_service(db: Session, test_instructor: User) -> Service:
    """Create a test service for the test instructor."""
    # Get instructor profile
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()

    if not profile:
        profile = InstructorProfile(
            user_id=test_instructor.id,
            bio="Test bio",
            years_experience=5,
        )
        db.add(profile)
        db.flush()
        add_service_areas_for_boroughs(db, user=test_instructor, boroughs=["Manhattan"])

    # Get or create catalog service
    category = db.query(ServiceCategory).first()
    if not category:
        category = ServiceCategory(name="Test Category")
        db.add(category)
        db.flush()

    subcategory = db.query(ServiceSubcategory).filter(ServiceSubcategory.category_id == category.id).first()
    if not subcategory:
        subcategory = ServiceSubcategory(name="General", category_id=category.id, display_order=1)
        db.add(subcategory)
        db.flush()

    service_ulid = generate_ulid()
    catalog_service = (
        db.query(ServiceCatalog).filter(ServiceCatalog.slug == f"test-service-{service_ulid.lower()}").first()
    )
    if not catalog_service:
        catalog_service = ServiceCatalog(
            name="Test Service", slug=f"test-service-{service_ulid.lower()}", subcategory_id=subcategory.id
        )
        db.add(catalog_service)
        db.flush()

    service = Service(
        instructor_profile_id=profile.id,
        service_catalog_id=catalog_service.id,
        hourly_rate=50.0,
        description="Test service",
        is_active=True,
    )
    db.add(service)
    db.commit()
    return service


@pytest.fixture
def test_instructors_with_profiles(db: Session) -> List[User]:
    """Create multiple test instructors with profiles and services."""
    instructors = []

    # Create instructors with different characteristics
    instructor_data = [
        {
            "name": "Senior Instructor",
            "email": "senior@test.com",
            "years_experience": 10,
            "bio": "Experienced instructor with 10 years",
            "service_areas": "Manhattan",
            "instructor_services": ["Advanced Math", "Physics"],
            "rates": [100.0, 120.0],
        },
        {
            "name": "Mid-Level Instructor",
            "email": "mid@test.com",
            "years_experience": 5,
            "bio": "Skilled instructor with 5 years",
            "service_areas": "Brooklyn",
            "instructor_services": ["Basic Math", "Chemistry"],
            "rates": [70.0, 80.0],
        },
        {
            "name": "Junior Instructor",
            "email": "junior@test.com",
            "years_experience": 2,
            "bio": "Enthusiastic new instructor",
            "service_areas": "Manhattan",
            "instructor_services": ["Elementary Math"],
            "rates": [50.0],
        },
        {
            "name": "Specialized Instructor",
            "email": "specialist@test.com",
            "years_experience": 8,
            "bio": "Specialist in advanced topics",
            "service_areas": "Queens",
            "instructor_services": ["Quantum Physics", "Advanced Calculus", "Research Methods"],
            "rates": [150.0, 140.0, 160.0],
        },
    ]

    for data in instructor_data:
        # Create user
        name_parts = data["name"].split(" ", 1)
        user = User(
            first_name=name_parts[0] if name_parts else "Test",
            last_name=name_parts[1] if len(name_parts) > 1 else "User",
            email=data["email"],
            hashed_password="test_hash",
            phone="+12125550000",
            zip_code="10001",
            is_active=True,
        )
        db.add(user)
        db.flush()

        # Create profile
        profile = InstructorProfile(
            user_id=user.id,
            bio=data["bio"],
            years_experience=data["years_experience"],
            min_advance_booking_hours=24,
            buffer_time_minutes=15,
        )
        db.add(profile)
        db.flush()

        seed_service_areas_from_legacy(db, user, data["service_areas"])

        # Get or create category for services
        category = db.query(ServiceCategory).first()
        if not category:
            category = ServiceCategory(name="Test Category")
            db.add(category)
            db.flush()

        subcategory = db.query(ServiceSubcategory).filter(ServiceSubcategory.category_id == category.id).first()
        if not subcategory:
            subcategory = ServiceSubcategory(name="General", category_id=category.id, display_order=1)
            db.add(subcategory)
            db.flush()

        # Create services
        for i, (skill, rate) in enumerate(zip(data["instructor_services"], data["rates"])):
            # Get or create catalog service
            skill_slug = skill.lower().replace(" ", "-")
            catalog_service = db.query(ServiceCatalog).filter(ServiceCatalog.slug == skill_slug).first()
            if not catalog_service:
                catalog_service = ServiceCatalog(name=skill, slug=skill_slug, subcategory_id=subcategory.id)
                db.add(catalog_service)
                db.flush()

            service = Service(
                instructor_profile_id=profile.id,
                service_catalog_id=catalog_service.id,
                hourly_rate=rate,
                description=f"{skill} tutoring service",
                is_active=True,
            )
            db.add(service)

        instructors.append(user)

    db.commit()
    return instructors


class TestInstructorProfileQueryPatterns:
    """Document every query pattern for InstructorProfileRepository."""

    def test_query_pattern_get_all_with_details(self, db: Session, test_instructors_with_profiles: List[User]):
        """Document query for getting all profiles with eager loading."""
        # Document the exact query pattern with eager loading
        query = (
            db.query(InstructorProfile)
            .options(joinedload(InstructorProfile.user), selectinload(InstructorProfile.instructor_services))
            .join(User)
            .filter(User.is_active == True)
            .order_by(InstructorProfile.created_at.desc())
        )

        results = query.all()

        # Repository method signature:
        # def get_all_with_details(self, skip: int = 0, limit: int = 100) -> List[InstructorProfile]

        # Verify eager loading worked
        assert len(results) >= 4
        for profile in results:
            assert profile.user is not None
            assert hasattr(profile, "instructor_services")
            assert profile.user.is_active == True

    def test_query_pattern_get_by_user_id_with_details(self, db: Session, test_instructors_with_profiles: List[User]):
        """Document query for getting profile by user ID with all relations."""
        instructor = test_instructors_with_profiles[0]
        user_id = instructor.id

        # Document the query pattern
        query = (
            db.query(InstructorProfile)
            .options(joinedload(InstructorProfile.user), selectinload(InstructorProfile.instructor_services))
            .filter(InstructorProfile.user_id == user_id)
        )

        result = query.first()

        # Repository method:
        # def get_by_user_id_with_details(self, user_id: int) -> Optional[InstructorProfile]

        assert result is not None
        assert result.user_id == user_id
        assert result.user is not None
        assert len(result.instructor_services) > 0

    def test_query_pattern_get_profiles_by_area(self, db: Session, test_instructors_with_profiles: List[User]):
        """Document query for filtering profiles by geographic area."""
        target_area = "Manhattan"

        # Document the query pattern
        query = (
            db.query(InstructorProfile)
            .options(joinedload(InstructorProfile.user), selectinload(InstructorProfile.instructor_services))
            .join(User)
            .filter(User.is_active == True)
            .join(InstructorServiceArea, InstructorServiceArea.instructor_id == User.id)
            .join(RegionBoundary, InstructorServiceArea.neighborhood_id == RegionBoundary.id)
            .filter(func.lower(RegionBoundary.parent_region) == target_area.lower())
            .distinct()
            .order_by(InstructorProfile.years_experience.desc())
        )

        results = query.all()

        # Repository method:
        # def get_profiles_by_area(self, area: str) -> List[InstructorProfile]

        assert len(results) >= 2  # Senior and Junior instructors
        for profile in results:
            boroughs = {
                getattr(area.neighborhood, "parent_region", "")
                for area in getattr(profile.user, "service_areas", [])
            }
            assert target_area in boroughs
            assert profile.user.is_active is True

    def test_query_pattern_get_profiles_by_experience(self, db: Session, test_instructors_with_profiles: List[User]):
        """Document query for filtering profiles by minimum years of experience."""
        min_years = 5

        # Document the query pattern
        query = (
            db.query(InstructorProfile)
            .options(joinedload(InstructorProfile.user), selectinload(InstructorProfile.instructor_services))
            .filter(InstructorProfile.years_experience >= min_years)
            .join(User)
            .filter(User.is_active == True)
            .order_by(InstructorProfile.years_experience.desc())
        )

        results = query.all()

        # Repository method:
        # def get_profiles_by_experience(self, min_years: int) -> List[InstructorProfile]

        assert len(results) >= 3  # Senior, Mid-level, and Specialist
        for profile in results:
            assert profile.years_experience >= min_years

    def test_query_pattern_search_profiles_by_skill(self, db: Session, test_instructors_with_profiles: List[User]):
        """Document query for searching profiles by service skill."""
        search_skill = "Math"

        # Complex query joining services and catalog
        query = (
            db.query(InstructorProfile)
            .distinct()
            .options(joinedload(InstructorProfile.user), selectinload(InstructorProfile.instructor_services))
            .join(Service)
            .join(ServiceCatalog, Service.service_catalog_id == ServiceCatalog.id)
            .filter(and_(ServiceCatalog.name.ilike(f"%{search_skill}%"), Service.is_active == True))
            .join(User)
            .filter(User.is_active == True)
        )

        results = query.all()

        # Repository method:
        # def search_profiles_by_skill(self, skill_keyword: str) -> List[InstructorProfile]

        assert len(results) >= 3  # All except Specialist have Math services
        for profile in results:
            # Verify at least one service matches
            matching_services = [
                s
                for s in profile.instructor_services
                if s.catalog_entry and search_skill.lower() in s.catalog_entry.name.lower()
            ]
            assert len(matching_services) > 0

    def test_query_pattern_get_profiles_by_rate_range(self, db: Session, test_instructors_with_profiles: List[User]):
        """Document query for filtering profiles by hourly rate range."""
        min_rate = 50.0
        max_rate = 100.0

        # Query profiles with at least one service in rate range
        query = (
            db.query(InstructorProfile)
            .distinct()
            .options(joinedload(InstructorProfile.user), selectinload(InstructorProfile.instructor_services))
            .join(Service)
            .filter(and_(Service.hourly_rate >= min_rate, Service.hourly_rate <= max_rate, Service.is_active == True))
            .join(User)
            .filter(User.is_active == True)
        )

        results = query.all()

        # Repository method:
        # def get_profiles_by_rate_range(self, min_rate: float, max_rate: float) -> List[InstructorProfile]

        assert len(results) >= 3  # Junior, Mid, Senior have services in range
        for profile in results:
            # Verify at least one service is in range
            services_in_range = [s for s in profile.instructor_services if min_rate <= s.hourly_rate <= max_rate]
            assert len(services_in_range) > 0

    def test_query_pattern_count_profiles(self, db: Session, test_instructors_with_profiles: List[User]):
        """Document query for counting active instructor profiles."""
        # Simple count query
        count = db.query(func.count(InstructorProfile.id)).join(User).filter(User.is_active == True).scalar()

        # Repository method:
        # def count_profiles(self, active_only: bool = True) -> int

        assert count >= 4

    def test_query_pattern_get_profile_with_availability_summary(
        self, db: Session, test_instructors_with_profiles: List[User]
    ):
        """Document query for profile with availability statistics."""
        instructor = test_instructors_with_profiles[0]

        # Create some availability for testing using bitmap storage
        today = date.today()
        for i in range(5):
            seed_day(db, instructor.id, today + timedelta(days=i), [("10:00", "11:00")])
        db.commit()

        # Complex query with subquery for availability stats (using AvailabilityDay)
        from app.models import AvailabilityDay
        availability_subquery = (
            db.query(
                AvailabilityDay.instructor_id,
                func.count(AvailabilityDay.day_date).label("total_days"),
                func.min(AvailabilityDay.day_date).label("first_available"),
                func.max(AvailabilityDay.day_date).label("last_available"),
            )
            .filter(AvailabilityDay.day_date >= today)
            .group_by(AvailabilityDay.instructor_id)
            .subquery()
        )

        query = (
            db.query(
                InstructorProfile,
                availability_subquery.c.total_days,
                availability_subquery.c.first_available,
                availability_subquery.c.last_available,
            )
            .outerjoin(availability_subquery, InstructorProfile.user_id == availability_subquery.c.instructor_id)
            .filter(InstructorProfile.user_id == instructor.id)
        )

        result = query.first()

        # Repository method:
        # def get_profile_with_availability_summary(self, user_id: int) -> Dict

        assert result is not None
        profile, total_days, first_available, last_available = result
        assert total_days >= 5
        assert first_available == today
        assert last_available == today + timedelta(days=4)

    def test_query_pattern_get_profiles_with_booking_stats(
        self, db: Session, test_instructors_with_profiles: List[User], test_student: User
    ):
        """Document query for profiles with booking statistics."""
        # Create some bookings for testing
        instructor_ids = [instructor.id for instructor in test_instructors_with_profiles[:2]]
        for i, instructor_id in enumerate(instructor_ids):
            # Get service for this instructor
            profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor_id).first()
            service = (
                db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
            )

            for j in range(i + 1):  # Different number of bookings
                create_booking_pg_safe(
                    db,
                    instructor_id=instructor_id,
                    student_id=test_student.id,
                    instructor_service_id=service.id,
                    booking_date=date.today() - timedelta(days=j),
                    start_time=time(10, 0),
                    end_time=time(11, 0),
                    status=BookingStatus.COMPLETED,
                    service_name="Test Service",
                    hourly_rate=50.0,
                    total_price=50.0,
                    duration_minutes=60,
                    offset_index=j,
                )
        db.commit()

        # Query with booking statistics
        booking_stats = (
            db.query(
                Booking.instructor_id,
                func.count(Booking.id).label("total_bookings"),
                func.count(func.distinct(Booking.student_id)).label("unique_students"),
            )
            .filter(Booking.status == BookingStatus.COMPLETED)
            .group_by(Booking.instructor_id)
            .subquery()
        )

        query = (
            db.query(
                InstructorProfile,
                func.coalesce(booking_stats.c.total_bookings, 0).label("total_bookings"),
                func.coalesce(booking_stats.c.unique_students, 0).label("unique_students"),
            )
            .outerjoin(booking_stats, InstructorProfile.user_id == booking_stats.c.instructor_id)
            .options(joinedload(InstructorProfile.user), selectinload(InstructorProfile.instructor_services))
            .order_by(booking_stats.c.total_bookings.desc().nullslast())
        )

        results = query.all()

        # Repository method:
        # def get_profiles_with_booking_stats(self) -> List[Tuple[InstructorProfile, int, int]]

        assert len(results) >= 4
        # First result should have most bookings
        first_profile, first_bookings, first_students = results[0]
        assert first_bookings >= 1
        assert first_students >= 1

    def test_query_pattern_search_profiles_advanced(self, db: Session, test_instructors_with_profiles: List[User]):
        """Document complex search with multiple filters."""
        # Advanced search parameters
        search_params = {
            "keyword": "math",
            "min_experience": 2,
            "max_rate": 100.0,
            "areas": ["Manhattan", "Brooklyn"],
            "has_availability": True,
        }

        # Build complex query
        query = db.query(InstructorProfile).distinct()

        # Join necessary tables
        query = query.join(User).join(Service).join(ServiceCatalog, Service.service_catalog_id == ServiceCatalog.id)

        # Apply filters
        filters = [User.is_active == True, Service.is_active == True]

        # Keyword search (in bio or service skills)
        if search_params["keyword"]:
            keyword = search_params["keyword"]
            filters.append(or_(InstructorProfile.bio.ilike(f"%{keyword}%"), ServiceCatalog.name.ilike(f"%{keyword}%")))

        # Experience filter
        if search_params["min_experience"]:
            filters.append(InstructorProfile.years_experience >= search_params["min_experience"])

        # Rate filter
        if search_params["max_rate"]:
            filters.append(Service.hourly_rate <= search_params["max_rate"])

        # Area filter
        if search_params["areas"]:
            query = query.join(
                InstructorServiceArea, InstructorServiceArea.instructor_id == User.id
            ).join(RegionBoundary, InstructorServiceArea.neighborhood_id == RegionBoundary.id)
            normalized_areas = [area.lower() for area in search_params["areas"]]
            filters.append(func.lower(RegionBoundary.parent_region).in_(normalized_areas))

        query = query.filter(and_(*filters))

        # Add eager loading
        query = query.options(joinedload(InstructorProfile.user), selectinload(InstructorProfile.instructor_services))

        results = query.all()

        # Repository method:
        # def search_profiles_advanced(self, **search_params) -> List[InstructorProfile]

        assert len(results) >= 2  # At least Junior and Mid-level match
        for profile in results:
            assert profile.years_experience >= 2
            boroughs = {
                getattr(area.neighborhood, "parent_region", "")
                for area in getattr(profile.user, "service_areas", [])
            }
            assert any(b in {"Manhattan", "Brooklyn"} for b in boroughs)

    def test_query_pattern_get_featured_instructors(self, db: Session, test_instructors_with_profiles: List[User]):
        """Document query for getting featured/top instructors."""
        # Query for top instructors based on experience and number of services
        query = (
            db.query(InstructorProfile, func.count(Service.id).label("service_count"))
            .join(Service)
            .join(User)
            .filter(and_(User.is_active == True, Service.is_active == True, InstructorProfile.years_experience >= 5))
            .group_by(InstructorProfile.id)
            .having(func.count(Service.id) >= 2)
            .order_by(InstructorProfile.years_experience.desc(), func.count(Service.id).desc())
            .limit(3)
        )

        results = query.all()

        # Repository method:
        # def get_featured_instructors(self, limit: int = 5) -> List[InstructorProfile]

        assert len(results) >= 2  # Senior and Specialist qualify
        for profile, service_count in results:
            assert profile.years_experience >= 5
            assert service_count >= 2

    def test_query_pattern_update_profile_last_active(self, db: Session, test_instructors_with_profiles: List[User]):
        """Document query for updating last active timestamp."""
        instructor = test_instructors_with_profiles[0]
        user_id = instructor.id

        # Update pattern
        update_count = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == user_id)
            .update({"updated_at": func.now()}, synchronize_session=False)
        )

        # Repository method:
        # def update_last_active(self, user_id: int) -> bool

        assert update_count == 1

        # Verify update
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == user_id).first()
        assert profile.updated_at is not None

    def test_query_pattern_deactivate_inactive_profiles(self, db: Session, test_instructors_with_profiles: List[User]):
        """Document query for deactivating profiles with no recent activity."""
        # Find profiles with no bookings in last 90 days
        cutoff_date = date.today() - timedelta(days=90)

        # Subquery for instructors with recent bookings
        active_instructors = (
            db.query(Booking.instructor_id)
            .filter(
                and_(
                    Booking.booking_date >= cutoff_date,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
            )
            .distinct()
            .subquery()
        )

        # Find inactive profiles
        inactive_profiles = (
            db.query(InstructorProfile)
            .join(User)
            .filter(and_(User.is_active == True, ~InstructorProfile.user_id.in_(select(active_instructors))))
            .all()
        )

        # Repository method:
        # def get_inactive_profiles(self, days_inactive: int = 90) -> List[InstructorProfile]

        # Since we just created test data, all should be inactive
        assert len(inactive_profiles) >= 4

    def test_query_pattern_profile_exists(self, db: Session, test_instructors_with_profiles: List[User]):
        """Document query for checking if profile exists."""
        instructor = test_instructors_with_profiles[0]
        user_id = instructor.id

        # Existence check pattern
        exists = db.query(db.query(InstructorProfile).filter(InstructorProfile.user_id == user_id).exists()).scalar()

        # Repository method:
        # def profile_exists(self, user_id: int) -> bool

        assert exists == True

        # Check non-existent
        not_exists = db.query(
            db.query(InstructorProfile).filter(InstructorProfile.user_id == generate_ulid()).exists()
        ).scalar()
        assert not_exists == False
