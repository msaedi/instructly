from __future__ import annotations

from datetime import date, time, timedelta
import json

import pytest
from sqlalchemy import text
from tests._utils.bitmap_avail import seed_day
from tests.conftest import _ensure_region_boundary, add_service_area

from app.models.service_catalog import InstructorService
from app.repositories.filter_repository import FilterRepository, _get_today_nyc


def _boundary_expects_multipolygon(db) -> bool:
    try:
        row = db.execute(
            text(
                """
                SELECT type
                FROM geometry_columns
                WHERE f_table_schema = 'public'
                  AND f_table_name = 'region_boundaries'
                  AND f_geometry_column = 'boundary'
                """
            )
        ).first()
        if row and row[0]:
            return "MULTIPOLYGON" in str(row[0]).upper()
    except Exception:
        pass

    try:
        row = db.execute(
            text(
                """
                SELECT postgis_typmod_type(a.atttypmod)
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname = 'region_boundaries'
                  AND a.attname = 'boundary'
                """
            )
        ).first()
        if row and row[0]:
            return "MULTIPOLYGON" in str(row[0]).upper()
    except Exception:
        pass

    return False


def _set_region_geometry(db, region_id: str, lon: float, lat: float) -> None:
    geom = {
        "type": "Polygon",
        "coordinates": [
            [
                [lon - 0.01, lat - 0.01],
                [lon + 0.01, lat - 0.01],
                [lon + 0.01, lat + 0.01],
                [lon - 0.01, lat + 0.01],
                [lon - 0.01, lat - 0.01],
            ]
        ],
    }
    geom_expr = "ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326)"
    if _boundary_expects_multipolygon(db):
        geom_expr = f"ST_Multi({geom_expr})"
    db.execute(
        text(
            f"""
            UPDATE region_boundaries
            SET boundary = {geom_expr},
                centroid = ST_Centroid({geom_expr})
            WHERE id = :id
            """
        ),
        {"geom": json.dumps(geom), "id": region_id},
    )
    db.flush()


def test_location_filters_cover_regions(db, test_instructor):
    repo = FilterRepository(db)
    region = _ensure_region_boundary(db, "Manhattan")
    add_service_area(db, user=test_instructor, neighborhood_id=region.id)
    db.commit()

    results = repo.filter_by_region_coverage([test_instructor.id], region.id)
    assert test_instructor.id in results

    any_results = repo.filter_by_any_region_coverage([test_instructor.id], [region.id])
    assert test_instructor.id in any_results

    by_parent = repo.filter_by_parent_region([test_instructor.id], "Manhattan")
    assert test_instructor.id in by_parent


def test_location_filters_empty_inputs(db):
    repo = FilterRepository(db)
    assert repo.filter_by_region_coverage([], "region") == []
    assert repo.filter_by_any_region_coverage(["id"], []) == []
    assert repo.filter_by_parent_region([], "Manhattan") == []
    assert repo.filter_by_location([], user_lng=0.0, user_lat=0.0) == []


def test_location_distance_filters(db, test_instructor):
    if not db.bind or db.bind.dialect.name != "postgresql":
        pytest.skip("PostGIS required")

    repo = FilterRepository(db)
    region = _ensure_region_boundary(db, "Manhattan")
    add_service_area(db, user=test_instructor, neighborhood_id=region.id)
    _set_region_geometry(db, region.id, lon=-73.985, lat=40.758)
    db.commit()

    hard = repo.filter_by_location(
        [test_instructor.id],
        user_lng=-73.985,
        user_lat=40.758,
        max_distance_meters=5000,
    )
    assert test_instructor.id in hard

    soft = repo.filter_by_location_soft(
        [test_instructor.id],
        user_lng=-73.985,
        user_lat=40.758,
        max_distance_meters=10000,
    )
    assert test_instructor.id in soft

    distances = repo.get_instructor_min_distance_to_region([test_instructor.id], region.id)
    assert test_instructor.id in distances


def test_availability_filters(db, test_instructor):
    repo = FilterRepository(db)
    target_date = date.today() + timedelta(days=2)
    seed_day(db, test_instructor.id, target_date, [("09:00", "12:00")])
    db.commit()

    assert repo.check_availability_single_date(
        test_instructor.id,
        target_date,
        time_after=time(9, 0),
        time_before=time(12, 0),
        duration_minutes=60,
    )

    filtered = repo.filter_by_availability(
        [test_instructor.id],
        target_date=target_date,
        time_after=time(9, 0),
        time_before=time(12, 0),
        duration_minutes=60,
    )
    assert test_instructor.id in filtered

    batch = repo.batch_check_availability(
        [test_instructor.id],
        target_date=target_date,
        time_after=time(9, 0),
        time_before=time(12, 0),
        duration_minutes=60,
    )
    assert test_instructor.id in batch

    weekend = repo.check_weekend_availability(
        [test_instructor.id],
        saturday=target_date,
        sunday=target_date + timedelta(days=1),
        time_after=time(9, 0),
        time_before=time(12, 0),
        duration_minutes=60,
    )
    assert weekend[test_instructor.id]


def test_availability_default_dates_and_empty_inputs(db, test_instructor):
    repo = FilterRepository(db)
    today = _get_today_nyc()
    seed_day(db, test_instructor.id, today, [("08:00", "09:00")])
    db.commit()

    default_dates = repo.filter_by_availability([test_instructor.id])
    assert test_instructor.id in default_dates

    assert repo.filter_by_availability([]) == {}
    assert repo.batch_check_availability([], today) == []
    assert repo.check_weekend_availability([], today, today + timedelta(days=1)) == {}


def test_filter_by_lesson_type(db, test_instructor):
    repo = FilterRepository(db)
    service = (
        db.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == test_instructor.instructor_profile.id)
        .first()
    )

    service.location_types = ["online"]
    db.flush()
    online = repo.filter_by_lesson_type([service.id], "online")
    assert service.id in online

    service.location_types = None
    db.flush()
    fallback = repo.filter_by_lesson_type([service.id], "online")
    assert service.id in fallback

    service.location_types = ["in_person"]
    db.flush()
    in_person = repo.filter_by_lesson_type([service.id], "in_person")
    assert service.id in in_person

    any_results = repo.filter_by_lesson_type([service.id], "any")
    assert any_results == [service.id]

    unknown = repo.filter_by_lesson_type([service.id], "unknown")
    assert unknown == [service.id]


def test_filter_by_lesson_type_empty_inputs(db):
    repo = FilterRepository(db)
    assert repo.filter_by_lesson_type([], "online") == []
