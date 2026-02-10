from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from backend.tests.factories.booking_builders import create_booking_pg_safe

from app.models.address import InstructorServiceArea
from app.models.event_outbox import NotificationDelivery
from app.models.notification import PushSubscription
from app.models.service_catalog import InstructorService
from app.repositories.communication_repository import CommunicationRepository
from app.repositories.notification_delivery_repository import NotificationDeliveryRepository


def test_communication_repository_queries(db, test_student, test_instructor):
    repo = CommunicationRepository(db)

    assert repo.list_users_by_ids([]) == []
    assert test_student.id in repo.list_user_ids_by_role("student")
    assert test_instructor.id in repo.list_user_ids_by_role("instructor")

    profile = test_instructor.instructor_profile
    instructor_service = (
        db.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == profile.id)
        .order_by(InstructorService.id)
        .first()
    )
    if instructor_service is None:
        raise AssertionError("Missing instructor service")

    create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=instructor_service.id,
        booking_date=date.today() + timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(10, 0),
        service_name="Test",
        hourly_rate=50,
        total_price=50,
        duration_minutes=60,
        status="confirmed",
        meeting_location="Test",
        offset_index=8,
        max_shifts=120,
    )

    since = datetime.now(timezone.utc) - timedelta(days=7)
    assert test_student.id in repo.list_active_user_ids(since, "student")
    assert test_instructor.id in repo.list_active_user_ids(since, "instructor")

    profile.is_founding_instructor = True
    db.flush()
    assert test_instructor.id in repo.list_founding_instructor_ids()

    subscription = PushSubscription(
        user_id=test_student.id,
        endpoint="https://push.test/123",
        p256dh_key="p256",
        auth_key="auth",
    )
    db.add(subscription)
    db.flush()
    assert test_student.id in repo.list_push_subscription_user_ids([test_student.id])

    catalog_entry = instructor_service.catalog_entry
    category = catalog_entry.category
    assert category is not None
    category_ids = repo.resolve_category_ids([category.id, category.name])
    assert category.id in category_ids

    service_area = (
        db.query(InstructorServiceArea)
        .filter(InstructorServiceArea.instructor_id == test_instructor.id)
        .first()
    )
    if service_area is None:
        raise AssertionError("Missing service area")
    region = service_area.neighborhood
    region_ids = repo.resolve_region_ids([region.id, region.region_name, region.region_code])
    assert region.id in region_ids

    assert test_instructor.id in repo.list_instructor_ids_by_categories([category.id])
    assert test_student.id in repo.list_student_ids_by_categories([category.id])

    assert test_instructor.id in repo.list_instructor_ids_by_regions([region.id])
    assert test_student.id in repo.list_student_ids_by_zip([test_student.zip_code])

    delivery_repo = NotificationDeliveryRepository(db)
    delivery_repo.record_delivery(
        event_type="admin.communication.announcement",
        idempotency_key="batch-1",
        payload={"channels": ["email"]},
    )
    records = repo.list_notification_deliveries(
        event_types=["admin.communication.announcement"],
        start=None,
        end=None,
        limit=10,
    )
    assert any(isinstance(record, NotificationDelivery) for record in records)
    assert repo.count_notification_deliveries("admin.communication.announcement") >= 1


def test_communication_repository_empty_input_guards(db):
    repo = CommunicationRepository(db)

    assert repo.list_push_subscription_user_ids([]) == set()
    assert repo.resolve_category_ids(["", None]) == []  # type: ignore[list-item]
    assert repo.resolve_region_ids(["", None]) == []  # type: ignore[list-item]
    assert repo.list_instructor_ids_by_categories([]) == []
    assert repo.list_student_ids_by_categories([]) == []
    assert repo.list_instructor_ids_by_regions([]) == []
    assert repo.list_student_ids_by_zip([]) == []


def test_communication_repository_list_users_by_ids_non_empty(db, test_student):
    repo = CommunicationRepository(db)
    users = repo.list_users_by_ids([test_student.id])
    assert [user.id for user in users] == [test_student.id]


def test_communication_repository_notification_delivery_filters(
    db,
    test_student,
    test_instructor,
):
    repo = CommunicationRepository(db)
    delivery_repo = NotificationDeliveryRepository(db)

    delivery_repo.record_delivery(
        event_type="admin.communication.weekly_digest",
        idempotency_key="digest-1",
        payload={"channels": ["email"]},
    )
    delivery_repo.record_delivery(
        event_type="admin.communication.weekly_digest",
        idempotency_key="digest-2",
        payload={"channels": ["push"]},
    )
    db.commit()

    now = datetime.now(timezone.utc)
    deliveries = repo.list_notification_deliveries(
        event_types=["admin.communication.weekly_digest"],
        start=now - timedelta(days=1),
        end=now + timedelta(days=1),
        limit=0,
    )

    assert len(deliveries) >= 2
