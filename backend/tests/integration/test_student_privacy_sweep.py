"""End-to-end privacy sweep for participant identity exposure."""

from __future__ import annotations

from datetime import date, timedelta

from backend.tests._utils.bitmap_avail import seed_day
import pytest

from app.models.booking import Booking, BookingStatus
from app.models.conversation import Conversation


def _student_initial(last_name: str) -> str:
    return f"{last_name[0]}."


def _assert_public_student_identity(student: dict, *, expected_first_name: str, expected_last_initial: str) -> None:
    assert student["first_name"] == expected_first_name
    assert student["last_initial"] == expected_last_initial
    assert "last_name" not in student
    assert "email" not in student
    assert "phone" not in student


def _assert_public_other_user(other_user: dict, *, expected_first_name: str, expected_last_initial: str) -> None:
    assert other_user["first_name"] == expected_first_name
    assert other_user["last_initial"] == expected_last_initial
    assert "last_name" not in other_user
    assert "email" not in other_user
    assert "phone" not in other_user


@pytest.fixture(autouse=True)
def _seed_availability_for_privacy_sweep(db, test_instructor):
    tomorrow = date.today() + timedelta(days=1)
    seed_day(db, test_instructor.id, tomorrow, [("09:00:00", "17:00:00")])


@pytest.fixture(autouse=True)
def _reset_instructor_privacy_records(db, test_instructor, test_student):
    db.query(Booking).filter(Booking.instructor_id == test_instructor.id).delete()
    db.query(Conversation).filter(
        Conversation.instructor_id == test_instructor.id,
        Conversation.student_id == test_student.id,
    ).delete()


def _get_service(db, test_instructor):
    from app.models.instructor import InstructorProfile
    from app.models.service_catalog import InstructorService as Service

    profile = (
        db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()
    )
    assert profile is not None, "Test instructor must have a profile"

    service = (
        db.query(Service)
        .filter(Service.instructor_profile_id == profile.id, Service.is_active == True)
        .first()
    )
    assert service is not None, "Test instructor must have an active service"
    return service


def _create_booking(client, *, service_id: str, instructor_id: str, headers: dict[str, str]):
    tomorrow = date.today() + timedelta(days=1)
    response = client.post(
        "/api/v1/bookings",
        json={
            "instructor_id": instructor_id,
            "instructor_service_id": service_id,
            "booking_date": tomorrow.isoformat(),
            "start_time": "10:00",
            "selected_duration": 60,
            "student_note": "Privacy sweep booking",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _confirm_booking(db, booking_id: str) -> None:
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    assert booking is not None, "Created booking should exist"
    booking.status = BookingStatus.CONFIRMED
    db.add(booking)
    db.commit()


def test_instructor_booking_endpoints_hide_student_pii(
    client,
    db,
    test_student,
    test_instructor,
    auth_headers_student,
    auth_headers_instructor,
):
    service = _get_service(db, test_instructor)
    created = _create_booking(
        client,
        service_id=service.id,
        instructor_id=test_instructor.id,
        headers=auth_headers_student,
    )
    booking_id = created["id"]
    _confirm_booking(db, booking_id)

    # Self-view still includes the student's own full identity.
    assert created["student"]["last_name"] == test_student.last_name
    assert created["student"]["email"] == test_student.email

    list_response = client.get("/api/v1/bookings", headers=auth_headers_instructor)
    assert list_response.status_code == 200, list_response.text
    list_item = next(item for item in list_response.json()["items"] if item["id"] == booking_id)
    _assert_public_student_identity(
        list_item["student"],
        expected_first_name=test_student.first_name,
        expected_last_initial=test_student.last_name[0],
    )

    detail_response = client.get(f"/api/v1/bookings/{booking_id}", headers=auth_headers_instructor)
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    _assert_public_student_identity(
        detail["student"],
        expected_first_name=test_student.first_name,
        expected_last_initial=test_student.last_name[0],
    )

    upcoming_response = client.get("/api/v1/bookings/upcoming", headers=auth_headers_instructor)
    assert upcoming_response.status_code == 200, upcoming_response.text
    upcoming = next(item for item in upcoming_response.json()["items"] if item["id"] == booking_id)
    assert upcoming["student_first_name"] == test_student.first_name
    assert upcoming["student_last_initial"] == _student_initial(test_student.last_name)
    assert "student_last_name" not in upcoming
    assert "student_email" not in upcoming
    assert "student_phone" not in upcoming
    assert upcoming["instructor_last_name"] == test_instructor.last_name

    preview_response = client.get(
        f"/api/v1/bookings/{booking_id}/preview", headers=auth_headers_instructor
    )
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    assert preview["student_first_name"] == test_student.first_name
    assert preview["student_last_initial"] == _student_initial(test_student.last_name)
    assert "student_last_name" not in preview
    assert "student_email" not in preview
    assert "student_phone" not in preview
    assert preview["instructor_last_name"] == test_instructor.last_name

    instructor_list = client.get("/api/v1/instructor-bookings", headers=auth_headers_instructor)
    assert instructor_list.status_code == 200, instructor_list.text
    instructor_item = next(item for item in instructor_list.json()["items"] if item["id"] == booking_id)
    _assert_public_student_identity(
        instructor_item["student"],
        expected_first_name=test_student.first_name,
        expected_last_initial=test_student.last_name[0],
    )

    instructor_upcoming = client.get(
        "/api/v1/instructor-bookings/upcoming", headers=auth_headers_instructor
    )
    assert instructor_upcoming.status_code == 200, instructor_upcoming.text
    instructor_upcoming_item = next(
        item for item in instructor_upcoming.json()["items"] if item["id"] == booking_id
    )
    _assert_public_student_identity(
        instructor_upcoming_item["student"],
        expected_first_name=test_student.first_name,
        expected_last_initial=test_student.last_name[0],
    )


def test_student_facing_instructor_surfaces_show_last_initial_only(
    client,
    db,
    test_student,
    test_instructor,
    auth_headers_student,
):
    service = _get_service(db, test_instructor)
    booking = _create_booking(
        client,
        service_id=service.id,
        instructor_id=test_instructor.id,
        headers=auth_headers_student,
    )
    booking_id = booking["id"]
    _confirm_booking(db, booking_id)

    bookings_response = client.get("/api/v1/bookings", headers=auth_headers_student)
    assert bookings_response.status_code == 200, bookings_response.text
    bookings_item = next(item for item in bookings_response.json()["items"] if item["id"] == booking_id)
    instructor = bookings_item["instructor"]
    assert instructor["first_name"] == test_instructor.first_name
    assert instructor["last_initial"] == test_instructor.last_name[0]
    assert "last_name" not in instructor
    assert "email" not in instructor

    detail_response = client.get(f"/api/v1/bookings/{booking_id}", headers=auth_headers_student)
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["instructor"]["last_initial"] == test_instructor.last_name[0]
    assert "last_name" not in detail["instructor"]
    assert "email" not in detail["instructor"]

    upcoming_response = client.get("/api/v1/bookings/upcoming", headers=auth_headers_student)
    assert upcoming_response.status_code == 200, upcoming_response.text
    upcoming = next(item for item in upcoming_response.json()["items"] if item["id"] == booking_id)
    assert upcoming["instructor_first_name"] == test_instructor.first_name
    assert upcoming["instructor_last_name"] == test_instructor.last_name[0]

    preview_response = client.get(f"/api/v1/bookings/{booking_id}/preview", headers=auth_headers_student)
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    assert preview["instructor_first_name"] == test_instructor.first_name
    assert preview["instructor_last_name"] == test_instructor.last_name[0]

    favorite_add = client.post(
        f"/api/v1/favorites/{test_instructor.id}", headers=auth_headers_student
    )
    assert favorite_add.status_code == 200, favorite_add.text

    favorites_response = client.get("/api/v1/favorites", headers=auth_headers_student)
    assert favorites_response.status_code == 200, favorites_response.text
    favorite = favorites_response.json()["favorites"][0]
    assert favorite["first_name"] == test_instructor.first_name
    assert favorite["last_initial"] == test_instructor.last_name[0]
    assert "email" not in favorite
    assert "last_name" not in favorite
    assert favorite["profile"]["user"]["last_initial"] == test_instructor.last_name[0]
    assert "last_name" not in favorite["profile"]["user"]
    assert "email" not in favorite["profile"]["user"]

    instructors_response = client.get(
        f"/api/v1/instructors?service_catalog_id={service.service_catalog_id}",
        headers=auth_headers_student,
    )
    assert instructors_response.status_code == 200, instructors_response.text
    instructor_item = next(
        item for item in instructors_response.json()["items"] if item["user_id"] == test_instructor.id
    )
    assert instructor_item["user"]["first_name"] == test_instructor.first_name
    assert instructor_item["user"]["last_initial"] == test_instructor.last_name[0]
    assert "last_name" not in instructor_item["user"]
    assert "email" not in instructor_item["user"]

    profile_response = client.get(
        f"/api/v1/instructors/{test_instructor.id}",
        headers=auth_headers_student,
    )
    assert profile_response.status_code == 200, profile_response.text
    profile = profile_response.json()
    assert profile["user"]["first_name"] == test_instructor.first_name
    assert profile["user"]["last_initial"] == test_instructor.last_name[0]
    assert "last_name" not in profile["user"]
    assert "email" not in profile["user"]


def test_conversation_headers_are_redacted_but_admin_booking_detail_keeps_full_identity(
    client,
    db,
    test_student,
    test_instructor,
    auth_headers_student,
    auth_headers_instructor,
    auth_headers_admin,
):
    service = _get_service(db, test_instructor)
    booking = _create_booking(
        client,
        service_id=service.id,
        instructor_id=test_instructor.id,
        headers=auth_headers_student,
    )
    booking_id = booking["id"]
    _confirm_booking(db, booking_id)

    create_conversation = client.post(
        "/api/v1/conversations",
        json={
            "instructor_id": test_instructor.id,
            "initial_message": "Hello there",
        },
        headers=auth_headers_student,
    )
    assert create_conversation.status_code == 200, create_conversation.text
    conversation_id = create_conversation.json()["id"]

    instructor_conversations = client.get(
        "/api/v1/conversations", headers=auth_headers_instructor
    )
    assert instructor_conversations.status_code == 200, instructor_conversations.text
    instructor_list_item = next(
        item
        for item in instructor_conversations.json()["conversations"]
        if item["id"] == conversation_id
    )
    _assert_public_other_user(
        instructor_list_item["other_user"],
        expected_first_name=test_student.first_name,
        expected_last_initial=test_student.last_name[0],
    )

    instructor_detail = client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=auth_headers_instructor,
    )
    assert instructor_detail.status_code == 200, instructor_detail.text
    _assert_public_other_user(
        instructor_detail.json()["other_user"],
        expected_first_name=test_student.first_name,
        expected_last_initial=test_student.last_name[0],
    )

    student_conversations = client.get("/api/v1/conversations", headers=auth_headers_student)
    assert student_conversations.status_code == 200, student_conversations.text
    student_list_item = next(
        item for item in student_conversations.json()["conversations"] if item["id"] == conversation_id
    )
    _assert_public_other_user(
        student_list_item["other_user"],
        expected_first_name=test_instructor.first_name,
        expected_last_initial=test_instructor.last_name[0],
    )

    student_detail = client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=auth_headers_student,
    )
    assert student_detail.status_code == 200, student_detail.text
    _assert_public_other_user(
        student_detail.json()["other_user"],
        expected_first_name=test_instructor.first_name,
        expected_last_initial=test_instructor.last_name[0],
    )

    admin_detail = client.get(
        f"/api/v1/admin/bookings/{booking_id}",
        headers=auth_headers_admin,
    )
    assert admin_detail.status_code == 200, admin_detail.text
    admin_payload = admin_detail.json()
    assert admin_payload["student"]["name"] == f"{test_student.first_name} {test_student.last_name}"
    assert admin_payload["student"]["email"] == test_student.email
    assert admin_payload["instructor"]["name"] == f"{test_instructor.first_name} {test_instructor.last_name}"
    assert admin_payload["instructor"]["email"] == test_instructor.email
