from __future__ import annotations

from app.core.ulid_helper import generate_ulid
from app.models.address import InstructorServiceArea
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service

try:  # pragma: no cover - fallback for direct backend test executions
    from backend.tests.conftest import add_service_areas_for_boroughs
except ModuleNotFoundError:  # pragma: no cover
    from tests.conftest import add_service_areas_for_boroughs

def _get_service_id(db, instructor_id: str) -> str:
    profile = (
        db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor_id).first()
    )
    if not profile:
        raise RuntimeError("Instructor profile missing in fixture")
    service = (
        db.query(Service)
        .filter(Service.instructor_profile_id == profile.id)
        .order_by(Service.created_at.asc())
        .first()
    )
    if not service:
        raise RuntimeError("Instructor service missing in fixture")
    return service.id


class TestServiceCapabilitiesEndpoint:
    def test_update_capabilities_success(self, client, db, test_instructor, auth_headers_instructor):
        service_id = _get_service_id(db, test_instructor.id)
        has_service_area = (
            db.query(InstructorServiceArea)
            .filter(InstructorServiceArea.instructor_id == test_instructor.id)
            .first()
        )
        if not has_service_area:
            add_service_areas_for_boroughs(db, user=test_instructor, boroughs=["Manhattan"])
            db.commit()

        response = client.patch(
            f"/api/v1/services/{service_id}/capabilities",
            json={"offers_travel": True},
            headers=auth_headers_instructor,
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["offers_travel"] is True

    def test_update_capabilities_validates_requirements(
        self, client, db, test_instructor, auth_headers_instructor
    ):
        service_id = _get_service_id(db, test_instructor.id)

        response = client.patch(
            f"/api/v1/services/{service_id}/capabilities",
            json={"offers_at_location": True, "offers_online": True},
            headers=auth_headers_instructor,
        )

        assert response.status_code == 422
        payload = response.json()
        code = payload.get("code")
        if code is None:
            detail = payload.get("detail", {})
            if isinstance(detail, dict):
                code = detail.get("code")
        assert code == "NO_TEACHING_LOCATIONS"

    def test_update_capabilities_requires_owner(
        self, client, db, test_instructor, auth_headers_instructor_2
    ):
        service_id = _get_service_id(db, test_instructor.id)

        response = client.patch(
            f"/api/v1/services/{service_id}/capabilities",
            json={"offers_online": True},
            headers=auth_headers_instructor_2,
        )

        assert response.status_code == 403

    def test_update_capabilities_404_for_unknown_service(
        self, client, auth_headers_instructor
    ):
        missing_id = generate_ulid()

        response = client.patch(
            f"/api/v1/services/{missing_id}/capabilities",
            json={"offers_online": True},
            headers=auth_headers_instructor,
        )

        assert response.status_code == 404
