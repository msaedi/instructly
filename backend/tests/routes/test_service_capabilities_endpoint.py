from __future__ import annotations

from app.core.ulid_helper import generate_ulid
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service


def _get_service_id(db, instructor_id: str) -> str:
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor_id).first()
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
    def test_capabilities_patch_endpoint_removed_for_existing_service(
        self, client, db, test_instructor, auth_headers_instructor
    ):
        service_id = _get_service_id(db, test_instructor.id)

        response = client.patch(
            f"/api/v1/services/{service_id}/capabilities",
            json={"offers_travel": True},
            headers=auth_headers_instructor,
        )

        assert response.status_code == 404

    def test_capabilities_patch_endpoint_removed_for_other_instructor(
        self, client, db, test_instructor, auth_headers_instructor_2
    ):
        service_id = _get_service_id(db, test_instructor.id)

        response = client.patch(
            f"/api/v1/services/{service_id}/capabilities",
            json={"offers_online": True},
            headers=auth_headers_instructor_2,
        )

        assert response.status_code == 404

    def test_capabilities_patch_endpoint_removed_for_unknown_service(
        self, client, auth_headers_instructor
    ):
        missing_id = generate_ulid()

        response = client.patch(
            f"/api/v1/services/{missing_id}/capabilities",
            json={"offers_online": True},
            headers=auth_headers_instructor,
        )

        assert response.status_code == 404
