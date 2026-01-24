from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.enums import RoleName
from app.models.service_catalog import ServiceCatalog
from app.schemas.instructor import (
    InstructorProfileCreate,
    InstructorProfileUpdate,
    PreferredPublicSpaceIn,
    PreferredTeachingLocationIn,
    ServiceCreate,
)
from app.services.instructor_service import InstructorService


def test_instructor_service_filters_and_public_profile(
    db, test_instructor, mock_cache_service
):
    service = InstructorService(db, cache_service=mock_cache_service)

    profile = service.profile_repository.find_one_by(user_id=test_instructor.id)
    assert profile is not None
    services = service.service_repository.find_by(instructor_profile_id=profile.id)
    assert services
    services[0].age_groups = ["kids"]
    db.commit()

    results = service.get_instructors_filtered(
        search="Test Instructor",
        service_catalog_id=services[0].service_catalog_id,
        min_price=40.0,
        max_price=80.0,
        age_group="kids",
        service_area_boroughs=["Manhattan"],
        skip=0,
        limit=10,
    )
    assert results["instructors"]

    mock_cache_service.get.return_value = None
    public = service.get_public_instructor_profile(test_instructor.id)
    assert public is not None
    assert mock_cache_service.set.called

    mock_cache_service.get.return_value = {"cached": True}
    cached = service.get_public_instructor_profile("cached-id")
    assert cached == {"cached": True}

    mock_cache_service.get.return_value = None
    available = service.get_available_catalog_services()
    assert available
    mock_cache_service.get.return_value = [{"id": "cached-service"}]
    assert service.get_available_catalog_services() == [{"id": "cached-service"}]

    mock_cache_service.get.return_value = None
    categories = service.get_service_categories()
    assert categories
    mock_cache_service.get.return_value = [{"id": "cached-category"}]
    assert service.get_service_categories() == [{"id": "cached-category"}]


def test_create_and_update_instructor_profile(db, test_student, monkeypatch):
    service = InstructorService(db)
    catalog_services = (
        db.query(ServiceCatalog).order_by(ServiceCatalog.slug).limit(2).all()
    )
    if not catalog_services:
        pytest.skip("No catalog services available for profile creation")

    profile_data = InstructorProfileCreate(
        bio="New instructor bio",
        years_experience=3,
        min_advance_booking_hours=2,
        buffer_time_minutes=0,
        services=[
            ServiceCreate(
                offers_travel=False,
                offers_at_location=False,
                offers_online=True,
                service_catalog_id=catalog_services[0].id,
                hourly_rate=50.0,
                description="Lessons",
                duration_options=[60],
            )
        ],
    )

    created = service.create_instructor_profile(test_student, profile_data)
    assert created["user"]["id"] == test_student.id
    refreshed_user = service.user_repository.get_by_id(test_student.id)
    assert refreshed_user is not None
    assert any(role.name == RoleName.INSTRUCTOR for role in refreshed_user.roles)

    profile = service.profile_repository.find_one_by(user_id=test_student.id)
    assert profile is not None
    profile.bio = ""
    db.commit()

    class FakeGeo:
        async def geocode(self, _query: str):
            return SimpleNamespace(city="New York")

    monkeypatch.setattr(
        "app.services.instructor_service.create_geocoding_provider",
        lambda *_: FakeGeo(),
    )

    update_services = [
        ServiceCreate(
            offers_travel=False,
            offers_at_location=False,
            offers_online=True,
            service_catalog_id=catalog_services[0].id,
            hourly_rate=55.0,
            description="Updated",
            duration_options=[60],
        )
    ]
    if len(catalog_services) > 1:
        update_services.append(
            ServiceCreate(
                offers_travel=False,
                offers_at_location=False,
                offers_online=True,
                service_catalog_id=catalog_services[1].id,
                hourly_rate=60.0,
                description="Second",
                duration_options=[60],
            )
        )

    update_data = InstructorProfileUpdate(
        services=update_services,
        preferred_teaching_locations=[
            PreferredTeachingLocationIn(address="123 Main St", label="Home")
        ],
        preferred_public_spaces=[PreferredPublicSpaceIn(address="Central Park", label="Park")],
    )

    updated = service.update_instructor_profile(test_student.id, update_data)
    assert updated["services"]


def test_create_instructor_service_from_catalog(db, test_instructor):
    service = InstructorService(db)

    profile = service.profile_repository.find_one_by(user_id=test_instructor.id)
    assert profile is not None

    existing_ids = {svc.service_catalog_id for svc in profile.instructor_services}
    catalog = (
        db.query(ServiceCatalog)
        .filter(~ServiceCatalog.id.in_(existing_ids))
        .order_by(ServiceCatalog.slug)
        .first()
    )
    if not catalog:
        pytest.skip("No unused catalog service found to create")

    created = service.create_instructor_service_from_catalog(
        test_instructor.id,
        catalog_service_id=catalog.id,
        hourly_rate=70.0,
        custom_description="Custom",
        duration_options=[60, 90],
    )
    assert created["catalog_service_id"] == catalog.id


def test_get_top_services_per_category_cache(db, mock_cache_service):
    service = InstructorService(db, cache_service=mock_cache_service)
    mock_cache_service.get.return_value = None

    categories = service.category_repository.get_all()
    if not categories:
        pytest.skip("No service categories available")

    top_services = service.catalog_repository.get_active_services_with_categories(
        category_id=categories[0].id, limit=1
    )
    if not top_services:
        pytest.skip("No active services available")

    analytics = service.analytics_repository.get_or_create(top_services[0].id)
    analytics.active_instructors = 1
    db.commit()

    result = service.get_top_services_per_category(limit=1)
    assert "categories" in result
    assert mock_cache_service.set.called

    mock_cache_service.get.return_value = {"cached": True}
    assert service.get_top_services_per_category(limit=1) == {"cached": True}


def test_get_instructor_profile_and_user(db, test_instructor):
    service = InstructorService(db)

    profile_data = service.get_instructor_profile(test_instructor.id)
    assert profile_data["user"]["id"] == test_instructor.id

    user = service.get_instructor_user(test_instructor.id)
    assert user.id == test_instructor.id

    profile = service.profile_repository.get_by_user_id(test_instructor.id)
    assert profile is not None
    resolved = service.get_instructor_user(profile.id)
    assert resolved.id == test_instructor.id
