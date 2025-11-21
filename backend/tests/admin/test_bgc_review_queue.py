from datetime import datetime, timedelta, timezone
import math

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

        detail_response = client.get(
            f"/api/admin/instructors/{profile.id}",
            headers=headers,
        )
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert detail["id"] == profile.id
        assert detail["bgc_status"] == "passed"
        assert detail["is_live"] is False

    def test_cases_endpoint_filters_and_counts(self, client, db):
        permission_service = PermissionService(db)

        admin = User(
            email="admin_counts@example.com",
            hashed_password=get_password_hash("AdminPass123!"),
            first_name="Admin",
            last_name="Counts",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(admin)
        db.flush()
        permission_service.assign_role(admin.id, RoleName.ADMIN)

        pending_user = User(
            email="pending_instructor@example.com",
            hashed_password=get_password_hash("InstructorPass123!"),
            first_name="Pending",
            last_name="Instructor",
            phone="+13475550000",
            zip_code="10002",
        )
        review_user = User(
            email="review_filter@example.com",
            hashed_password=get_password_hash("InstructorPass123!"),
            first_name="Review",
            last_name="Filter",
            phone="+13475551111",
            zip_code="10003",
        )
        newest_user = User(
            email="recent_case@example.com",
            hashed_password=get_password_hash("InstructorPass123!"),
            first_name="Recent",
            last_name="Case",
            phone="+13475552222",
            zip_code="10004",
        )
        db.add_all([pending_user, review_user, newest_user])
        db.flush()
        permission_service.assign_role(pending_user.id, RoleName.INSTRUCTOR)
        permission_service.assign_role(review_user.id, RoleName.INSTRUCTOR)
        permission_service.assign_role(newest_user.id, RoleName.INSTRUCTOR)

        base_time = datetime.now(timezone.utc)
        pending_profile = InstructorProfile(
            user_id=pending_user.id,
            bgc_status="pending",
            bgc_report_id="rpt_pending",
            bgc_env="sandbox",
            created_at=base_time - timedelta(days=2),
            updated_at=base_time - timedelta(days=2),
        )
        review_profile = InstructorProfile(
            user_id=review_user.id,
            bgc_status="review",
            bgc_report_id="rpt_review",
            bgc_env="sandbox",
            created_at=base_time - timedelta(days=1),
            updated_at=base_time - timedelta(days=1),
        )
        newest_profile = InstructorProfile(
            user_id=newest_user.id,
            bgc_status="pending",
            bgc_report_id="rpt_recent",
            bgc_env="sandbox",
            created_at=base_time,
            updated_at=base_time,
        )
        db.add_all([pending_profile, review_profile, newest_profile])
        db.commit()
        db.refresh(pending_profile)
        db.refresh(review_profile)
        db.refresh(newest_profile)

        repo = InstructorProfileRepository(db)
        repo.record_bgc_consent(pending_profile.id, consent_version="v1", ip_address=None)
        repo.record_bgc_consent(review_profile.id, consent_version="v1", ip_address=None)
        repo.record_bgc_consent(newest_profile.id, consent_version="v1", ip_address=None)
        db.commit()

        token = create_access_token(data={"sub": admin.email})
        headers = {"Authorization": f"Bearer {token}"}

        counts_response = client.get("/api/admin/bgc/counts", headers=headers)
        assert counts_response.status_code == 200
        counts = counts_response.json()
        assert counts == {"review": 1, "pending": 2}

        review_cases = client.get("/api/admin/bgc/cases?status=review", headers=headers)
        assert review_cases.status_code == 200
        review_payload = review_cases.json()
        assert review_payload["total"] == 1
        assert len(review_payload["items"]) == 1
        assert review_payload["items"][0]["instructor_id"] == review_profile.id
        assert review_payload["items"][0]["bgc_status"] == "review"
        assert review_payload["items"][0]["consent_recent"] is True

        pending_cases = client.get("/api/admin/bgc/cases?status=pending", headers=headers)
        assert pending_cases.status_code == 200
        pending_payload = pending_cases.json()
        assert pending_payload["total"] == 2
        assert pending_payload["page"] == 1
        assert pending_payload["items"][0]["instructor_id"] == newest_profile.id
        assert pending_payload["items"][0]["bgc_status"] == "pending"

        search_cases = client.get(
            "/api/admin/bgc/cases?status=all&q=pending_instructor",
            headers=headers,
        )
        assert search_cases.status_code == 200
        search_payload = search_cases.json()
        assert search_payload["total"] == 1
        assert search_payload["items"][0]["instructor_id"] == pending_profile.id

        paged_cases = client.get(
            "/api/admin/bgc/cases?status=all&page=1&page_size=1",
            headers=headers,
        )
        assert paged_cases.status_code == 200
        first_page = paged_cases.json()
        assert first_page["items"][0]["instructor_id"] == newest_profile.id
        assert first_page["has_next"] is True

        second_page = client.get(
            "/api/admin/bgc/cases?status=all&page=2&page_size=1",
            headers=headers,
        )
        assert second_page.status_code == 200
        second_payload = second_page.json()
        assert second_payload["items"][0]["instructor_id"] == review_profile.id
        assert second_payload["has_prev"] is True

        invalid_status = client.get(
            "/api/admin/bgc/cases?status=invalid",
            headers=headers,
        )
        assert invalid_status.status_code == 400

        extra_needed = 71 - 3
        extra_users: list[User] = []
        extra_profiles: list[InstructorProfile] = []
        for idx in range(extra_needed):
            extra_user = User(
                email=f"bulk_case_{idx}@example.com",
                hashed_password=get_password_hash("InstructorPass123!"),
                first_name="Bulk",
                last_name=f"Case{idx}",
                phone=f"+1347556{idx:04d}",
                zip_code="10010",
            )
            extra_users.append(extra_user)
        db.add_all(extra_users)
        db.flush()
        for idx, extra_user in enumerate(extra_users):
            permission_service.assign_role(extra_user.id, RoleName.INSTRUCTOR)
            profile = InstructorProfile(
                user_id=extra_user.id,
                bgc_status="review" if idx % 2 == 0 else "pending",
                bgc_report_id=f"rpt_bulk_{idx}",
                bgc_env="sandbox",
                created_at=base_time - timedelta(minutes=idx + 5),
                updated_at=base_time - timedelta(minutes=idx + 5),
            )
            extra_profiles.append(profile)
        db.add_all(extra_profiles)
        db.commit()

        total_expected = extra_needed + 3

        page1_response = client.get(
            "/api/admin/bgc/cases?status=all&page=1&page_size=50",
            headers=headers,
        )
        assert page1_response.status_code == 200
        page1_payload = page1_response.json()
        assert page1_payload["total"] == total_expected, f"Expected total={total_expected}, got {page1_payload['total']}"
        assert page1_payload["page"] == 1
        assert page1_payload["page_size"] == 50
        assert page1_payload["total_pages"] == math.ceil(total_expected / 50)
        assert len(page1_payload["items"]) == 50, f"Page 1 should have 50 items, got {len(page1_payload['items'])}"
        assert page1_payload["has_next"] is True
        assert page1_payload["has_prev"] is False

        page2_response = client.get(
            "/api/admin/bgc/cases?status=all&page=2&page_size=50",
            headers=headers,
        )
        assert page2_response.status_code == 200
        page2_payload = page2_response.json()
        expected_page2_items = total_expected - 50
        assert page2_payload["total"] == total_expected, f"Page 2: Expected total={total_expected}, got {page2_payload['total']}"
        assert page2_payload["page"] == 2, f"Expected page=2, got {page2_payload['page']}"
        assert page2_payload["total_pages"] == math.ceil(total_expected / 50), f"Expected total_pages=2, got {page2_payload['total_pages']}"
        assert len(page2_payload["items"]) == expected_page2_items, f"Page 2 should have {expected_page2_items} items, got {len(page2_payload['items'])}"
        assert page2_payload["has_next"] is False, "Page 2 should not have next page"
        assert page2_payload["has_prev"] is True, "Page 2 should have previous page"
