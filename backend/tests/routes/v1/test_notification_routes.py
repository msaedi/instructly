"""Tests for notification inbox routes."""

from app.models.user import User
from app.repositories.notification_repository import NotificationRepository


def _ensure_users(db, *users) -> None:
    for user in users:
        if db.get(User, user.id) is None:
            db.merge(user)
    db.flush()


def test_list_notifications(client, auth_headers_instructor, db, test_instructor, test_student):
    _ensure_users(db, test_instructor, test_student)
    repo = NotificationRepository(db)
    repo.create_notification(
        user_id=test_instructor.id,
        category="lesson_updates",
        type="booking_confirmed",
        title="Instructor notice",
        body="Body",
    )
    repo.create_notification(
        user_id=test_student.id,
        category="lesson_updates",
        type="booking_confirmed",
        title="Student notice",
        body="Body",
    )
    db.commit()

    response = client.get("/api/v1/notifications", headers=auth_headers_instructor)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["unread_count"] == 1
    assert len(payload["notifications"]) == 1
    assert payload["notifications"][0]["title"] == "Instructor notice"


def test_list_notifications_unread_only(client, auth_headers_instructor, db, test_instructor):
    _ensure_users(db, test_instructor)
    repo = NotificationRepository(db)
    first = repo.create_notification(
        user_id=test_instructor.id,
        category="lesson_updates",
        type="booking_confirmed",
        title="Unread",
        body="Body",
    )
    repo.create_notification(
        user_id=test_instructor.id,
        category="messages",
        type="new_message",
        title="Read",
        body="Body",
    )
    db.commit()

    repo.mark_as_read(first.id)
    db.commit()

    response = client.get(
        "/api/v1/notifications",
        headers=auth_headers_instructor,
        params={"unread_only": "true"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["notifications"][0]["title"] == "Read"


def test_get_unread_count(client, auth_headers_instructor, db, test_instructor):
    _ensure_users(db, test_instructor)
    repo = NotificationRepository(db)
    repo.create_notification(
        user_id=test_instructor.id,
        category="lesson_updates",
        type="booking_confirmed",
        title="Unread",
        body="Body",
    )
    db.commit()

    response = client.get("/api/v1/notifications/unread-count", headers=auth_headers_instructor)

    assert response.status_code == 200
    assert response.json()["unread_count"] == 1


def test_mark_notification_read(client, auth_headers_instructor, db, test_instructor):
    _ensure_users(db, test_instructor)
    repo = NotificationRepository(db)
    notification = repo.create_notification(
        user_id=test_instructor.id,
        category="lesson_updates",
        type="booking_confirmed",
        title="Unread",
        body="Body",
    )
    db.commit()

    response = client.post(
        f"/api/v1/notifications/{notification.id}/read",
        headers=auth_headers_instructor,
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_mark_all_notifications_read(client, auth_headers_instructor, db, test_instructor):
    _ensure_users(db, test_instructor)
    repo = NotificationRepository(db)
    for idx in range(2):
        repo.create_notification(
            user_id=test_instructor.id,
            category="lesson_updates",
            type=f"type_{idx}",
            title=f"Title {idx}",
            body="Body",
        )
    db.commit()

    response = client.post("/api/v1/notifications/read-all", headers=auth_headers_instructor)

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_delete_notification(client, auth_headers_instructor, db, test_instructor):
    _ensure_users(db, test_instructor)
    repo = NotificationRepository(db)
    notification = repo.create_notification(
        user_id=test_instructor.id,
        category="lesson_updates",
        type="booking_confirmed",
        title="Delete",
        body="Body",
    )
    db.commit()

    response = client.delete(
        f"/api/v1/notifications/{notification.id}",
        headers=auth_headers_instructor,
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_delete_all_notifications(client, auth_headers_instructor, db, test_instructor):
    _ensure_users(db, test_instructor)
    repo = NotificationRepository(db)
    for idx in range(2):
        repo.create_notification(
            user_id=test_instructor.id,
            category="lesson_updates",
            type=f"type_{idx}",
            title=f"Title {idx}",
            body="Body",
        )
    db.commit()

    response = client.delete("/api/v1/notifications", headers=auth_headers_instructor)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert repo.get_user_notification_count(test_instructor.id) == 0


def test_mark_notification_read_requires_ownership(
    client, auth_headers_instructor, db, test_student
):
    _ensure_users(db, test_student)
    repo = NotificationRepository(db)
    notification = repo.create_notification(
        user_id=test_student.id,
        category="lesson_updates",
        type="booking_confirmed",
        title="Other user",
        body="Body",
    )
    db.commit()

    response = client.post(
        f"/api/v1/notifications/{notification.id}/read",
        headers=auth_headers_instructor,
    )

    assert response.status_code == 404
