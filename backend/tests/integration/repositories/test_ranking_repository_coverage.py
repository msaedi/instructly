from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import json

import pytest
from sqlalchemy import text
from tests.factories.booking_builders import create_booking_pg_safe

from app.models.address import InstructorServiceArea
from app.models.booking import BookingStatus
from app.models.review import Review, ReviewStatus
from app.models.service_catalog import InstructorService, ServiceCatalog
from app.repositories.ranking_repository import RankingRepository


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


def _create_review(db, instructor_id: str, student_id: str, service: InstructorService) -> None:
    catalog = db.get(ServiceCatalog, service.service_catalog_id)
    duration = (service.duration_options or [60])[0]
    hourly_rate = float(service.hourly_rate)
    total_price = hourly_rate * (duration / 60)
    booking = create_booking_pg_safe(
        db,
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=service.id,
        booking_date=date.today() + timedelta(days=2),
        start_time=time(9, 0),
        end_time=time(10, 0),
        status=BookingStatus.COMPLETED,
        offset_index=5,
        service_name=catalog.name if catalog else "Lesson",
        hourly_rate=hourly_rate,
        total_price=total_price,
        duration_minutes=duration,
    )
    review = Review(
        booking_id=booking.id,
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=service.id,
        rating=5,
        status=ReviewStatus.PUBLISHED,
        is_verified=True,
        booking_completed_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db.add(review)
    db.flush()


def test_get_instructor_metrics_and_tenure(db, test_instructor, test_student):
    repo = RankingRepository(db)
    service = (
        db.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == test_instructor.instructor_profile.id)
        .first()
    )
    _create_review(db, test_instructor.id, test_student.id, service)

    test_instructor.instructor_profile.bio = "x" * 120
    db.flush()

    metrics = repo.get_instructor_metrics([test_instructor.id])
    assert test_instructor.id in metrics
    assert metrics[test_instructor.id]["review_count"] >= 1
    assert metrics[test_instructor.id]["has_bio"] is True

    tenure = repo.get_instructor_tenure_date([test_instructor.id])
    assert tenure[test_instructor.id] is not None


def test_get_instructor_metrics_empty(db):
    repo = RankingRepository(db)
    assert repo.get_instructor_metrics([]) == {}


def test_global_average_rating_cache(db, test_instructor, test_student, monkeypatch):
    repo = RankingRepository(db)
    service = (
        db.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == test_instructor.instructor_profile.id)
        .first()
    )
    _create_review(db, test_instructor.id, test_student.id, service)

    monkeypatch.setattr(
        "app.repositories.ranking_repository._GLOBAL_AVG_RATING_CACHE",
        None,
    )
    monkeypatch.setattr(
        "app.repositories.ranking_repository._GLOBAL_AVG_RATING_CACHED_AT",
        0.0,
    )

    first = repo.get_global_average_rating()
    second = repo.get_global_average_rating()
    assert first == second


def test_service_audience_and_skills(db, test_instructor):
    repo = RankingRepository(db)
    services = (
        db.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == test_instructor.instructor_profile.id)
        .order_by(InstructorService.id)
        .all()
    )
    services[0].age_groups = ["kids", "teens"]
    services[0].filter_selections = {}
    services[1].age_groups = ["adults"]
    services[1].filter_selections = {"skill_level": ["beginner"]}
    db.flush()

    audiences = repo.get_service_audience([s.id for s in services])
    assert audiences[services[0].id] == "kids"
    assert audiences[services[1].id] == "adults"
    assert repo._classify_audience(["kids", "adults"]) == "both"

    skills = repo.get_service_skill_levels([s.id for s in services])
    assert skills[services[0].id] == ["all"]
    assert "beginner" in skills[services[1].id]


def test_get_instructor_distances(db, test_instructor):
    if not db.bind or db.bind.dialect.name != "postgresql":
        pytest.skip("PostGIS required")

    repo = RankingRepository(db)
    region_ids = [
        row.neighborhood_id
        for row in db.query(InstructorServiceArea)
        .filter(InstructorServiceArea.instructor_id == test_instructor.id)
        .all()
        if row.neighborhood_id
    ]
    assert region_ids

    _set_region_geometry(db, region_ids[0], lon=-73.985, lat=40.758)
    db.commit()

    distances = repo.get_instructor_distances(
        [test_instructor.id],
        user_lng=-73.985,
        user_lat=40.758,
    )
    assert test_instructor.id in distances
    assert distances[test_instructor.id] >= 0
