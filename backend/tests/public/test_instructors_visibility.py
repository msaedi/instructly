from datetime import datetime, timezone

import pytest
import ulid

from app.models.instructor import InstructorProfile
from app.models.service_catalog import (
    InstructorService,
    ServiceCatalog,
    ServiceCategory,
)
from app.models.subcategory import ServiceSubcategory
from app.models.user import User


def _catalog_setup(db):
    category = ServiceCategory(
        name="Music",
        description="Music lessons",
    )
    db.add(category)
    db.flush()

    subcategory = ServiceSubcategory(
        name="Piano",
        category_id=category.id,
        display_order=1,
    )
    db.add(subcategory)
    db.flush()

    catalog_slug = f"piano-{ulid.ULID()}"
    catalog = ServiceCatalog(
        subcategory_id=subcategory.id,
        name="Piano",
        slug=catalog_slug,
        description="Piano lessons",
    )
    db.add(catalog)
    db.flush()

    return catalog


def _create_profile(db, *, email: str, is_live: bool, bgc_status: str) -> InstructorProfile:
    user = User(
        email=email,
        hashed_password="hashed",
        first_name="Public",
        last_name="Check",
        zip_code="10001",
        is_active=True,
    )
    db.add(user)
    db.flush()

    profile = InstructorProfile(
        user_id=user.id,
        is_live=is_live,
        bgc_status=bgc_status,
        bio="Experienced instructor",
        years_experience=5,
        bgc_completed_at=datetime.now(timezone.utc) if bgc_status == "passed" else None,
    )
    db.add(profile)
    db.flush()

    return profile


@pytest.fixture
def catalog_entry(db):
    return _catalog_setup(db)


def test_public_visibility_rules(client, db, catalog_entry):
    visible = _create_profile(
        db,
        email="visible@example.com",
        is_live=True,
        bgc_status="passed",
    )
    pending = _create_profile(
        db,
        email="pending@example.com",
        is_live=False,
        bgc_status="pending",
    )
    offline = _create_profile(
        db,
        email="offline@example.com",
        is_live=False,
        bgc_status="passed",
    )

    for profile in (visible, pending, offline):
        service = InstructorService(
            instructor_profile_id=profile.id,
            service_catalog_id=catalog_entry.id,
            hourly_rate=75.0,
            duration_options=[60],
            offers_online=True,
            offers_travel=False,
            offers_at_location=False,
            is_active=True,
        )
        db.add(service)

    db.commit()

    list_response = client.get(
        "/api/v1/instructors",
        params={"service_catalog_id": catalog_entry.id, "per_page": 10},
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == visible.id

    detail_ok = client.get(f"/api/v1/instructors/{visible.user_id}")
    assert detail_ok.status_code == 200

    for hidden in (pending, offline):
        detail_response = client.get(f"/api/v1/instructors/{hidden.id}")
        assert detail_response.status_code == 404
