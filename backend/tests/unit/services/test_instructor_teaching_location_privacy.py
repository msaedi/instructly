from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.instructor import InstructorPreferredPlace
from app.schemas.instructor import InstructorProfileUpdate, PreferredTeachingLocationIn
from app.services.instructor_service import InstructorService


def test_teaching_location_sets_approx_and_neighborhood(db, test_instructor, monkeypatch) -> None:
    service = InstructorService(db)
    fake_geo = SimpleNamespace(
        latitude=40.7128,
        longitude=-74.0060,
        provider_id="place-1",
        neighborhood="Lower East Side",
        city="New York",
        state="NY",
    )

    class FakeProvider:
        async def geocode(self, _address: str):
            return fake_geo

    monkeypatch.setattr(
        "app.services.instructor_service.create_geocoding_provider", lambda *_: FakeProvider()
    )
    monkeypatch.setattr("app.services.instructor_service.anyio.run", lambda *_: fake_geo)
    monkeypatch.setattr(
        "app.services.instructor_service.jitter_coordinates",
        lambda lat, lng: (lat + 0.001, lng - 0.001),
    )
    monkeypatch.setattr(
        "app.services.instructor_service.LocationEnrichmentService.enrich",
        lambda *_: {},
    )

    update = InstructorProfileUpdate(
        preferred_teaching_locations=[
            PreferredTeachingLocationIn(address="225 Cherry St, New York, NY", label="Studio")
        ]
    )
    service.update_instructor_profile(test_instructor.id, update)

    place = (
        db.query(InstructorPreferredPlace)
        .filter(
            InstructorPreferredPlace.instructor_id == test_instructor.id,
            InstructorPreferredPlace.kind == "teaching_location",
        )
        .first()
    )
    assert place is not None
    assert place.approx_lat == pytest.approx(40.7138)
    assert place.approx_lng == pytest.approx(-74.007)
    assert place.neighborhood == "Lower East Side"


def test_teaching_location_reuses_existing_jitter_on_same_address(
    db, test_instructor, monkeypatch
) -> None:
    existing = InstructorPreferredPlace(
        instructor_id=test_instructor.id,
        kind="teaching_location",
        address="123 Main St, New York, NY",
        label="Studio",
        position=0,
        lat=40.7,
        lng=-74.0,
        approx_lat=40.71,
        approx_lng=-74.01,
        neighborhood="Chelsea",
    )
    db.add(existing)
    db.commit()

    jitter_mock = MagicMock(side_effect=AssertionError("jitter should not be called"))
    geocode_mock = MagicMock(side_effect=AssertionError("geocode should not be called"))
    monkeypatch.setattr("app.services.instructor_service.jitter_coordinates", jitter_mock)
    monkeypatch.setattr(
        "app.services.instructor_service.create_geocoding_provider", geocode_mock
    )

    update = InstructorProfileUpdate(
        preferred_teaching_locations=[
            PreferredTeachingLocationIn(address="123 Main St, New York, NY", label="Studio")
        ]
    )
    service = InstructorService(db)
    service.update_instructor_profile(test_instructor.id, update)

    assert jitter_mock.call_count == 0
    assert geocode_mock.call_count == 0

    place = (
        db.query(InstructorPreferredPlace)
        .filter(
            InstructorPreferredPlace.instructor_id == test_instructor.id,
            InstructorPreferredPlace.kind == "teaching_location",
        )
        .first()
    )
    assert place is not None
    assert place.approx_lat == pytest.approx(40.71)
    assert place.approx_lng == pytest.approx(-74.01)


def test_teaching_location_recomputes_on_address_change(db, test_instructor, monkeypatch) -> None:
    existing = InstructorPreferredPlace(
        instructor_id=test_instructor.id,
        kind="teaching_location",
        address="123 Main St, New York, NY",
        label="Studio",
        position=0,
        lat=40.7,
        lng=-74.0,
        approx_lat=40.71,
        approx_lng=-74.01,
        neighborhood="Chelsea",
    )
    db.add(existing)
    db.commit()

    fake_geo = SimpleNamespace(
        latitude=40.75,
        longitude=-73.99,
        provider_id="place-2",
        neighborhood="Midtown",
        city="New York",
        state="NY",
    )

    class FakeProvider:
        async def geocode(self, _address: str):
            return fake_geo

    jitter_mock = MagicMock(return_value=(40.76, -73.98))
    monkeypatch.setattr(
        "app.services.instructor_service.create_geocoding_provider", lambda *_: FakeProvider()
    )
    monkeypatch.setattr("app.services.instructor_service.anyio.run", lambda *_: fake_geo)
    monkeypatch.setattr("app.services.instructor_service.jitter_coordinates", jitter_mock)
    monkeypatch.setattr(
        "app.services.instructor_service.LocationEnrichmentService.enrich",
        lambda *_: {},
    )

    update = InstructorProfileUpdate(
        preferred_teaching_locations=[
            PreferredTeachingLocationIn(address="456 New St, New York, NY", label="Studio")
        ]
    )
    service = InstructorService(db)
    service.update_instructor_profile(test_instructor.id, update)

    assert jitter_mock.call_count == 1

    place = (
        db.query(InstructorPreferredPlace)
        .filter(
            InstructorPreferredPlace.instructor_id == test_instructor.id,
            InstructorPreferredPlace.kind == "teaching_location",
        )
        .first()
    )
    assert place is not None
    assert place.address == "456 New St, New York, NY"
    assert place.approx_lat == pytest.approx(40.76)
    assert place.approx_lng == pytest.approx(-73.98)
    assert place.neighborhood == "Midtown"
