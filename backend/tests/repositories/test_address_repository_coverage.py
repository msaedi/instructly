from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from app.models.address import InstructorServiceArea, NYCNeighborhood, UserAddress
from app.repositories.address_repository import (
    InstructorServiceAreaRepository,
    NYCNeighborhoodRepository,
    UserAddressRepository,
)
from tests.conftest import _ensure_region_boundary, add_service_area


def _create_address(db, *, user_id: str, is_default: bool = False, is_active: bool = True):
    address = UserAddress(
        user_id=user_id,
        street_line1="123 Test St",
        locality="Brooklyn",
        administrative_area="NY",
        postal_code="11201",
        country_code="US",
        latitude=Decimal("40.6892"),
        longitude=Decimal("-74.0445"),
        is_default=is_default,
        is_active=is_active,
    )
    db.add(address)
    db.flush()
    return address


def test_user_address_list_and_default(db, test_student):
    repo = UserAddressRepository(db)
    default_addr = _create_address(db, user_id=test_student.id, is_default=True)
    _create_address(db, user_id=test_student.id, is_default=False)
    inactive_addr = _create_address(db, user_id=test_student.id, is_default=False, is_active=False)

    active_addresses = repo.list_for_user(test_student.id)
    assert default_addr in active_addresses
    assert inactive_addr not in active_addresses
    assert active_addresses[0].is_default is True

    all_addresses = repo.list_for_user(test_student.id, active_only=False)
    assert inactive_addr in all_addresses

    default = repo.get_default_address(test_student.id)
    assert default is not None
    assert default.is_default is True


def test_get_default_address_falls_back_to_latest(db, test_student):
    repo = UserAddressRepository(db)
    first = _create_address(db, user_id=test_student.id, is_default=False)
    first.created_at = datetime.now(timezone.utc) - timedelta(days=1)
    second = _create_address(db, user_id=test_student.id, is_default=False)
    second.created_at = datetime.now(timezone.utc)
    db.flush()

    default = repo.get_default_address(test_student.id)
    assert default is not None
    assert default.id == second.id


def test_unset_default_updates_rows(db, test_student):
    repo = UserAddressRepository(db)
    _create_address(db, user_id=test_student.id, is_default=True)

    updated = repo.unset_default(test_student.id)
    assert updated == 1

    updated_again = repo.unset_default(test_student.id)
    assert updated_again == 0


def test_nyc_neighborhood_get_by_ntacode(db):
    repo = NYCNeighborhoodRepository(db)
    neighborhood = NYCNeighborhood(ntacode="MN-TEST", ntaname="Test", borough="Manhattan")
    db.add(neighborhood)
    db.flush()

    found = repo.get_by_ntacode("MN-TEST")
    assert found is not None
    assert found.id == neighborhood.id


def test_service_area_list_helpers(db, test_instructor):
    repo = InstructorServiceAreaRepository(db)
    assert repo.list_for_instructors([]) == {}
    assert repo.list_neighborhoods_for_instructors([]) == []


def test_service_area_list_filters_active(db, test_instructor):
    repo = InstructorServiceAreaRepository(db)
    active_boundary = _ensure_region_boundary(db, "Astoria")
    inactive_boundary = _ensure_region_boundary(db, "Jackson Heights")

    db.query(InstructorServiceArea).filter(
        InstructorServiceArea.instructor_id == test_instructor.id
    ).delete()
    db.flush()

    active_area = add_service_area(db, test_instructor, active_boundary.id)
    active_area.is_active = True
    inactive_area = add_service_area(db, test_instructor, inactive_boundary.id)
    inactive_area.is_active = False
    db.flush()

    active_only = repo.list_for_instructor(test_instructor.id, active_only=True)
    assert {area.neighborhood_id for area in active_only} == {active_boundary.id}

    all_areas = repo.list_for_instructor(test_instructor.id, active_only=False)
    assert {area.neighborhood_id for area in all_areas} == {
        active_boundary.id,
        inactive_boundary.id,
    }


def test_list_for_instructors_groups_results(db, test_instructor, test_student):
    repo = InstructorServiceAreaRepository(db)
    manhattan = _ensure_region_boundary(db, "Manhattan")
    brooklyn = _ensure_region_boundary(db, "Brooklyn")

    db.query(InstructorServiceArea).filter(
        InstructorServiceArea.instructor_id.in_([test_instructor.id, test_student.id])
    ).delete()
    db.flush()

    instructor_area = add_service_area(db, test_instructor, manhattan.id)
    instructor_area.is_active = True
    student_active = add_service_area(db, test_student, brooklyn.id)
    student_active.is_active = True
    student_inactive = add_service_area(db, test_student, manhattan.id)
    student_inactive.is_active = False
    db.flush()

    grouped = repo.list_for_instructors([test_instructor.id, test_student.id], active_only=True)
    assert grouped[test_instructor.id][0].neighborhood_id == manhattan.id
    assert {area.neighborhood_id for area in grouped[test_student.id]} == {brooklyn.id}


def test_replace_and_upsert_service_areas(db, test_student):
    repo = InstructorServiceAreaRepository(db)
    first_boundary = _ensure_region_boundary(db, "Manhattan")
    second_boundary = _ensure_region_boundary(db, "Brooklyn")

    existing = add_service_area(db, test_student, first_boundary.id)
    existing.is_active = True
    db.flush()

    updated_count = repo.replace_areas(test_student.id, [second_boundary.id])
    assert updated_count == 1

    refreshed_existing = (
        db.query(InstructorServiceArea)
        .filter(
            InstructorServiceArea.instructor_id == test_student.id,
            InstructorServiceArea.neighborhood_id == first_boundary.id,
        )
        .first()
    )
    assert refreshed_existing is not None
    assert refreshed_existing.is_active is False

    created = (
        db.query(InstructorServiceArea)
        .filter(
            InstructorServiceArea.instructor_id == test_student.id,
            InstructorServiceArea.neighborhood_id == second_boundary.id,
        )
        .first()
    )
    assert created is not None
    assert created.is_active is True

    updated = repo.upsert_area(
        test_student.id,
        second_boundary.id,
        coverage_type="radius",
        max_distance_miles=10.0,
        is_active=False,
    )
    assert updated.coverage_type == "radius"
    assert float(updated.max_distance_miles) == 10.0
    assert updated.is_active is False

    created = repo.upsert_area(test_student.id, first_boundary.id, is_active=True)
    assert created.neighborhood_id == first_boundary.id
    assert created.is_active is True


def test_list_neighborhoods_excludes_inactive(db, test_student):
    repo = InstructorServiceAreaRepository(db)
    manhattan = _ensure_region_boundary(db, "Manhattan")
    brooklyn = _ensure_region_boundary(db, "Brooklyn")

    db.query(InstructorServiceArea).filter(
        InstructorServiceArea.instructor_id == test_student.id
    ).delete()
    db.flush()

    active_area = add_service_area(db, test_student, manhattan.id)
    active_area.is_active = True
    inactive_area = add_service_area(db, test_student, brooklyn.id)
    inactive_area.is_active = False
    db.flush()

    results = repo.list_neighborhoods_for_instructors([test_student.id])
    assert {area.neighborhood_id for area in results} == {manhattan.id}


def test_get_primary_active_neighborhood_id(db, test_student, monkeypatch):
    repo = InstructorServiceAreaRepository(db)
    boundary = _ensure_region_boundary(db, "Queens")
    db.query(InstructorServiceArea).filter(
        InstructorServiceArea.instructor_id == test_student.id
    ).delete()
    repo.create(instructor_id=test_student.id, neighborhood_id=boundary.id, is_active=True)

    found = repo.get_primary_active_neighborhood_id(test_student.id)
    assert found == boundary.id

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo.db, "query", _boom)
    repo.db.rollback = MagicMock()
    assert repo.get_primary_active_neighborhood_id(test_student.id) is None
    repo.db.rollback.assert_called()
