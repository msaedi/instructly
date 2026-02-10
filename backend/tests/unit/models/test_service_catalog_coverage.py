from __future__ import annotations

from datetime import datetime, timezone

from app.models.instructor import InstructorProfile
from app.models.service_catalog import (
    InstructorService,
    ServiceAnalytics,
    ServiceCatalog,
    ServiceCategory,
)
from app.models.subcategory import ServiceSubcategory
from app.models.user import User


def _make_user(
    *,
    user_id: str = "user-1",
    first_name: str = "Ada",
    last_name: str = "Lovelace",
) -> User:
    return User(
        id=user_id,
        email="ada@example.com",
        hashed_password="hashed",
        first_name=first_name,
        last_name=last_name,
        zip_code="10001",
    )


def _make_instructor_profile(user_id: str = "u1") -> InstructorProfile:
    user = _make_user(user_id=user_id)
    profile = InstructorProfile(id=user_id, user_id=user_id)
    profile.user = user
    return profile


def _make_subcategory(
    *,
    sub_id: str = "sub",
    category_id: str = "cat",
    name: str = "General",
) -> ServiceSubcategory:
    return ServiceSubcategory(id=sub_id, category_id=category_id, name=name, display_order=0)


def test_service_category_counts_and_dict() -> None:
    category = ServiceCategory(id="cat", name="Music")
    subcategory = _make_subcategory(category_id="cat")

    active_catalog = ServiceCatalog(
        id="svc1",
        subcategory_id="sub",
        name="Piano Lessons",
        slug="piano-lessons",
        description="Learn piano",
        is_active=True,
    )
    inactive_catalog = ServiceCatalog(
        id="svc2",
        subcategory_id="sub",
        name="Inactive",
        slug="inactive",
        is_active=False,
    )

    instructor_active = InstructorService(
        id="is1",
        instructor_profile_id="ip1",
        service_catalog_id="svc1",
        hourly_rate=100.0,
        is_active=True,
    )
    instructor_active.instructor_profile = _make_instructor_profile("ip1")
    instructor_active.catalog_entry = active_catalog

    instructor_inactive = InstructorService(
        id="is2",
        instructor_profile_id="ip1",
        service_catalog_id="svc1",
        hourly_rate=80.0,
        is_active=False,
    )
    instructor_inactive.catalog_entry = active_catalog

    active_catalog.subcategory = subcategory
    active_catalog.instructor_services = [instructor_active, instructor_inactive]
    inactive_catalog.subcategory = subcategory
    inactive_catalog.instructor_services = []

    subcategory.category = category
    subcategory.services = [active_catalog, inactive_catalog]
    category.subcategories = [subcategory]

    assert "Music" in repr(category)
    assert category.active_services_count == 1
    assert category.instructor_count == 1

    payload = category.to_dict(include_subcategories=True, include_counts=True)
    assert len(payload["subcategories"]) == 1
    assert payload["active_services_count"] == 1


def test_service_catalog_properties_and_match() -> None:
    category = ServiceCategory(id="cat", name="Music")
    subcategory = _make_subcategory(category_id="cat")
    subcategory.category = category

    catalog = ServiceCatalog(
        id="svc1",
        subcategory_id="sub",
        name="Piano Lessons",
        slug="piano-lessons",
        description="Learn piano basics",
        search_terms=["keys", "music"],
        is_active=True,
    )
    catalog.subcategory = subcategory

    active_service = InstructorService(
        id="is1",
        instructor_profile_id="ip1",
        service_catalog_id="svc1",
        hourly_rate=120.0,
        is_active=True,
    )
    inactive_service = InstructorService(
        id="is2",
        instructor_profile_id="ip2",
        service_catalog_id="svc1",
        hourly_rate=80.0,
        is_active=False,
    )
    active_service.catalog_entry = catalog
    inactive_service.catalog_entry = catalog
    catalog.instructor_services = [active_service, inactive_service]

    assert "Piano" in repr(catalog)
    assert catalog.is_offered is True
    assert catalog.instructor_count == 1
    assert catalog.price_range == (120.0, 120.0)
    assert catalog.matches_search("piano") is True
    assert catalog.matches_search("basics") is True
    assert catalog.matches_search("music") is True
    assert catalog.matches_search("guitar") is False


def test_service_catalog_to_dict_includes_instructors() -> None:
    category = ServiceCategory(id="cat", name="Music")
    subcategory = _make_subcategory(category_id="cat")
    subcategory.category = category

    catalog = ServiceCatalog(
        id="svc1",
        subcategory_id="sub",
        name="Piano Lessons",
        slug="piano-lessons",
        description="Learn piano",
        is_active=True,
    )
    catalog.subcategory = subcategory

    instructor_profile = _make_instructor_profile("ip1")
    instructor_profile.user.first_name = "Ada"
    instructor_profile.user.last_name = "Lovelace"

    active_service = InstructorService(
        id="is1",
        instructor_profile_id="ip1",
        service_catalog_id="svc1",
        hourly_rate=100.0,
        is_active=True,
    )
    active_service.catalog_entry = catalog
    active_service.instructor_profile = instructor_profile

    catalog.instructor_services = [active_service]

    payload = catalog.to_dict(include_instructors=True)
    assert payload["category_name"] == "Music"
    assert payload["instructors"][0]["first_name"] == "Ada"


def test_instructor_service_helpers() -> None:
    category = ServiceCategory(id="cat", slug="music", name="Music")
    subcategory = _make_subcategory(category_id="cat")
    subcategory.category = category

    catalog = ServiceCatalog(
        id="svc1",
        subcategory_id="sub",
        name="Piano Lessons",
        slug="piano-lessons",
        description="Learn piano",
        is_active=True,
    )
    catalog.subcategory = subcategory

    service = InstructorService(
        id="is1",
        instructor_profile_id="ip1",
        service_catalog_id="svc1",
        hourly_rate=120.0,
        is_active=True,
    )
    service.catalog_entry = catalog

    assert service.name == "Piano Lessons"
    assert service.category == "Music"
    assert service.category_slug == "music"
    assert service.session_price(90) == 180.0

    service.deactivate()
    assert service.is_active is False
    service.activate()
    assert service.is_active is True

    service.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    payload = service.to_dict()
    assert payload["name"] == "Piano Lessons"


def test_instructor_service_fallbacks() -> None:
    service = InstructorService(
        id="is2",
        instructor_profile_id="ip2",
        service_catalog_id="svc2",
        hourly_rate=100.0,
        is_active=True,
    )
    assert service.name == "Unknown Service"
    assert service.category == "Unknown"
    assert service.category_slug == "unknown"


def test_service_analytics_scores() -> None:
    analytics = ServiceAnalytics(
        service_catalog_id="svc",
        search_count_7d=14,
        search_count_30d=30,
        booking_count_30d=10,
        view_to_booking_rate=0.5,
    )

    assert analytics.demand_score > 0
    assert analytics.is_trending is True
    payload = analytics.to_dict()
    assert payload["is_trending"] is True

    analytics.search_count_30d = 0
    assert analytics.demand_score == 0.0
