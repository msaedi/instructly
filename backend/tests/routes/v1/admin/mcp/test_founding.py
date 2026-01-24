from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.repositories.instructor_lifecycle_repository import InstructorLifecycleRepository


def test_funnel_returns_structure(client: TestClient, db, test_instructor, auth_headers_admin):
    repo = InstructorLifecycleRepository(db)
    repo.record_event(user_id=test_instructor.id, event_type="registered")
    db.flush()

    res = client.get("/api/v1/admin/mcp/founding/funnel", headers=auth_headers_admin)
    assert res.status_code == 200

    data = res.json()
    assert "meta" in data
    assert "stages" in data
    assert "conversion_rates" in data
    assert "founding_cap" in data
    assert "time_window" in data

    stages = {stage["stage"]: stage["count"] for stage in data["stages"]}
    assert stages.get("registered", 0) >= 1


def test_funnel_respects_date_filters(
    client: TestClient, db, test_instructor, test_instructor_2, auth_headers_admin
):
    repo = InstructorLifecycleRepository(db)
    now = datetime.now(timezone.utc)

    old_event = repo.record_event(user_id=test_instructor.id, event_type="registered")
    old_event.occurred_at = now - timedelta(days=10)

    new_event = repo.record_event(user_id=test_instructor_2.id, event_type="registered")
    new_event.occurred_at = now - timedelta(days=1)

    db.flush()

    start_date = (now - timedelta(days=5)).date().isoformat()
    res = client.get(
        "/api/v1/admin/mcp/founding/funnel",
        headers=auth_headers_admin,
        params={"start_date": start_date},
    )
    assert res.status_code == 200
    data = res.json()
    stages = {stage["stage"]: stage["count"] for stage in data["stages"]}
    assert stages.get("registered") == 1


def test_stuck_returns_structure(client: TestClient, db, test_instructor, test_instructor_2, auth_headers_admin):
    repo = InstructorLifecycleRepository(db)
    now = datetime.now(timezone.utc)

    old_event = repo.record_event(user_id=test_instructor.id, event_type="profile_submitted")
    old_event.occurred_at = now - timedelta(days=10)

    new_event = repo.record_event(user_id=test_instructor_2.id, event_type="profile_submitted")
    new_event.occurred_at = now - timedelta(days=1)

    db.flush()

    res = client.get(
        "/api/v1/admin/mcp/founding/stuck",
        headers=auth_headers_admin,
        params={"stuck_days": 7},
    )
    assert res.status_code == 200
    data = res.json()

    assert "meta" in data
    assert "summary" in data
    assert "instructors" in data
    assert "total_stuck" in data
    assert data["total_stuck"] == 1


def test_stuck_respects_stage_filter(
    client: TestClient, db, test_instructor, auth_headers_admin
):
    repo = InstructorLifecycleRepository(db)
    now = datetime.now(timezone.utc)

    old_event = repo.record_event(user_id=test_instructor.id, event_type="profile_submitted")
    old_event.occurred_at = now - timedelta(days=10)
    db.flush()

    res = client.get(
        "/api/v1/admin/mcp/founding/stuck",
        headers=auth_headers_admin,
        params={"stuck_days": 7, "stage": "registered"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_stuck"] == 0


def test_funnel_requires_authentication(client: TestClient):
    res = client.get("/api/v1/admin/mcp/founding/funnel")
    assert res.status_code == 401


def test_funnel_requires_permissions(client: TestClient, auth_headers):
    res = client.get("/api/v1/admin/mcp/founding/funnel", headers=auth_headers)
    assert res.status_code == 403
