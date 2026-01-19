from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from tests.factories.booking_builders import create_booking_pg_safe

from app.models.booking import BookingStatus
from app.models.review import Review, ReviewStatus
from app.models.service_catalog import InstructorService, ServiceCatalog
from app.repositories.retriever_repository import RetrieverRepository


def _ensure_embedding(db, catalog: ServiceCatalog) -> None:
    if catalog.embedding_v2 is None:
        catalog.embedding_v2 = [0.01] * 1536
        catalog.embedding_model = "test-model"
        catalog.embedding_model_version = "test"
        catalog.embedding_updated_at = datetime.now(timezone.utc)
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
        booking_date=date.today() + timedelta(days=3),
        start_time=time(11, 0),
        end_time=time(12, 0),
        status=BookingStatus.COMPLETED,
        offset_index=10,
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
        rating=4,
        status=ReviewStatus.PUBLISHED,
        is_verified=True,
        booking_completed_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.add(review)
    db.flush()


def test_vector_search_and_embedding_counts(db, test_instructor):
    repo = RetrieverRepository(db)
    service = (
        db.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == test_instructor.instructor_profile.id)
        .first()
    )
    catalog = db.get(ServiceCatalog, service.service_catalog_id)
    _ensure_embedding(db, catalog)
    db.commit()

    assert repo.has_embeddings() is True
    assert repo.count_embeddings() >= 1

    results = repo.vector_search([0.01] * 1536, limit=5)
    assert isinstance(results, list)


def test_text_search_and_text_only(db, test_instructor):
    repo = RetrieverRepository(db)
    results = repo.text_search("piano", "piano", limit=5)
    assert isinstance(results, list)

    grouped = repo.search_text_only("piano", "piano", limit=3)
    assert isinstance(grouped, list)


def test_get_services_and_instructor_summaries(db, test_instructor):
    repo = RetrieverRepository(db)
    service = (
        db.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == test_instructor.instructor_profile.id)
        .first()
    )
    services = repo.get_services_by_ids([service.id])
    assert services

    summaries = repo.get_instructor_summaries([test_instructor.id])
    assert summaries

    cards = repo.get_instructor_cards([test_instructor.id])
    assert cards


def test_get_instructor_ratings_and_coverage_areas(db, test_instructor, test_student):
    repo = RetrieverRepository(db)
    service = (
        db.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == test_instructor.instructor_profile.id)
        .first()
    )
    _create_review(db, test_instructor.id, test_student.id, service)
    db.commit()

    ratings = repo.get_instructor_ratings([test_instructor.id])
    assert ratings

    coverage = repo.get_instructor_coverage_areas([test_instructor.id])
    assert coverage


def test_search_with_instructor_data(db, test_instructor):
    repo = RetrieverRepository(db)
    service = (
        db.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == test_instructor.instructor_profile.id)
        .first()
    )
    catalog = db.get(ServiceCatalog, service.service_catalog_id)
    _ensure_embedding(db, catalog)
    db.commit()

    results = repo.search_with_instructor_data([0.01] * 1536, limit=3)
    assert isinstance(results, list)
