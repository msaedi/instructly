from datetime import datetime, timezone

from app.auth import create_access_token, get_password_hash
from app.core.enums import RoleName
from app.models.instructor import InstructorProfile
from app.models.user import User
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.services.permission_service import PermissionService


class TestAdminBGCReviewQueue:
    def test_list_and_approve(self, client, db):
        permission_service = PermissionService(db)

        admin = User(
            email="admin_bgc@example.com",
            hashed_password=get_password_hash("AdminPass123!"),
            first_name="Admin",
            last_name="Checker",
            phone="+12125551234",
            zip_code="10001",
        )
        db.add(admin)
        db.flush()
        permission_service.assign_role(admin.id, RoleName.ADMIN)

        instructor_user = User(
            email="review_instructor@example.com",
            hashed_password=get_password_hash("InstructorPass123!"),
            first_name="Review",
            last_name="Instructor",
            phone="+13475551234",
            zip_code="10002",
        )
        db.add(instructor_user)
        db.flush()
        permission_service.assign_role(instructor_user.id, RoleName.INSTRUCTOR)

        profile = InstructorProfile(
            user_id=instructor_user.id,
            bgc_status="review",
            bgc_report_id="rpt_test123",
            bgc_env="sandbox",
            created_at=datetime.now(timezone.utc),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        repo = InstructorProfileRepository(db)
        repo.record_bgc_consent(profile.id, consent_version="v1", ip_address=None)
        db.commit()

        token = create_access_token(data={"sub": admin.email})
        headers = {"Authorization": f"Bearer {token}"}

        count_response = client.get("/api/admin/bgc/review/count", headers=headers)
        assert count_response.status_code == 200
        assert count_response.json()["count"] == 1

        list_response = client.get("/api/admin/bgc/review?limit=10", headers=headers)
        assert list_response.status_code == 200
        payload = list_response.json()
        assert payload["next_cursor"] is None
        item = payload["items"][0]
        assert item["instructor_id"] == profile.id
        assert item["bgc_status"] == "review"
        assert item["consented_at_recent"] is True
        assert str(profile.bgc_report_id) in (item.get("checkr_report_url") or "")

        approve_response = client.post(
            f"/api/admin/bgc/{profile.id}/override",
            json={"action": "approve"},
            headers=headers,
        )
        assert approve_response.status_code == 200
        assert approve_response.json()["new_status"] == "passed"

        db.refresh(profile)
        assert profile.bgc_status == "passed"
        assert profile.bgc_completed_at is not None

        count_after = client.get("/api/admin/bgc/review/count", headers=headers)
        assert count_after.status_code == 200
        assert count_after.json()["count"] == 0

        latest_consent = client.get(
            f"/api/admin/bgc/consent/{profile.id}/latest",
            headers=headers,
        )
        assert latest_consent.status_code == 200
        payload = latest_consent.json()
        assert payload["instructor_id"] == profile.id
        assert payload["consent_version"] == "v1"
