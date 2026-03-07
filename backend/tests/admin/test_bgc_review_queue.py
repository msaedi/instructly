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

        count_response = client.get("/api/v1/admin/background-checks/review/count", headers=headers)
        assert count_response.status_code == 200
        assert count_response.json()["count"] == 1

        list_response = client.get("/api/v1/admin/background-checks/review?limit=10", headers=headers)
        assert list_response.status_code == 200
        payload = list_response.json()
        assert payload["next_cursor"] is None
        item = payload["items"][0]
        assert item["instructor_id"] == profile.id
        assert item["bgc_status"] == "review"
        assert item["consented_at_recent"] is True
        assert str(profile.bgc_report_id) in (item.get("checkr_report_url") or "")

        approve_response = client.post(
            f"/api/v1/admin/background-checks/{profile.id}/override",
            json={"action": "approve"},
            headers=headers,
        )
        assert approve_response.status_code == 200
        assert approve_response.json()["new_status"] == "passed"

        db.refresh(profile)
        assert profile.bgc_status == "passed"
        assert profile.bgc_completed_at is not None

        count_after = client.get("/api/v1/admin/background-checks/review/count", headers=headers)
        assert count_after.status_code == 200
        assert count_after.json()["count"] == 0

        latest_consent = client.get(
            f"/api/v1/admin/background-checks/consent/{profile.id}/latest",
            headers=headers,
        )
        assert latest_consent.status_code == 200
        payload = latest_consent.json()
        assert payload["instructor_id"] == profile.id
        assert payload["consent_version"] == "v1"

        detail_response = client.get(
            f"/api/v1/admin/instructors/{profile.id}",
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

        counts_response = client.get("/api/v1/admin/background-checks/counts", headers=headers)
        assert counts_response.status_code == 200
        counts = counts_response.json()
        assert counts == {"all": 3, "review": 1, "pending": 2}

        review_cases = client.get("/api/v1/admin/background-checks/cases?status=review", headers=headers)
        assert review_cases.status_code == 200
        review_payload = review_cases.json()
        assert review_payload["total"] == 1
        assert len(review_payload["items"]) == 1
        assert review_payload["items"][0]["instructor_id"] == review_profile.id
        assert review_payload["items"][0]["bgc_status"] == "review"
        assert review_payload["items"][0]["consent_recent"] is True

        pending_cases = client.get("/api/v1/admin/background-checks/cases?status=pending", headers=headers)
        assert pending_cases.status_code == 200
        pending_payload = pending_cases.json()
        assert pending_payload["total"] == 2
        assert pending_payload["page"] == 1
        assert pending_payload["items"][0]["instructor_id"] == newest_profile.id
        assert pending_payload["items"][0]["bgc_status"] == "pending"

        search_cases = client.get(
            "/api/v1/admin/background-checks/cases?status=all&q=pending_instructor",
            headers=headers,
        )
        assert search_cases.status_code == 200
        search_payload = search_cases.json()
        assert search_payload["total"] == 1
        assert search_payload["items"][0]["instructor_id"] == pending_profile.id

        paged_cases = client.get(
            "/api/v1/admin/background-checks/cases?status=all&page=1&page_size=1",
            headers=headers,
        )
        assert paged_cases.status_code == 200
        first_page = paged_cases.json()
        assert first_page["items"][0]["instructor_id"] == newest_profile.id
        assert first_page["has_next"] is True

        second_page = client.get(
            "/api/v1/admin/background-checks/cases?status=all&page=2&page_size=1",
            headers=headers,
        )
        assert second_page.status_code == 200
        second_payload = second_page.json()
        assert second_payload["items"][0]["instructor_id"] == review_profile.id
        assert second_payload["has_prev"] is True

        invalid_status = client.get(
            "/api/v1/admin/background-checks/cases?status=invalid",
            headers=headers,
        )
        assert invalid_status.status_code == 400

        # Optimized: Create bulk user/profile data in fewer DB operations
        # Reduced from 71 to 25 records - still tests pagination (>1 page at page_size=20)
        extra_needed = 25 - 3
        extra_users: list[User] = []
        extra_profiles: list[InstructorProfile] = []

        # Pre-hash password once instead of per-user
        hashed_pw = get_password_hash("InstructorPass123!")

        for idx in range(extra_needed):
            extra_user = User(
                email=f"bulk_case_{idx}@example.com",
                hashed_password=hashed_pw,
                first_name="Bulk",
                last_name=f"Case{idx}",
                phone=f"+1347556{idx:04d}",
                zip_code="10010",
            )
            extra_users.append(extra_user)
        db.add_all(extra_users)
        db.flush()

        # Batch role assignments and profile creation
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

        # Test pagination with page_size=20 (25 total = 2 pages)
        page1_response = client.get(
            "/api/v1/admin/background-checks/cases?status=all&page=1&page_size=20",
            headers=headers,
        )
        assert page1_response.status_code == 200
        page1_payload = page1_response.json()
        assert page1_payload["total"] == total_expected, f"Expected total={total_expected}, got {page1_payload['total']}"
        assert page1_payload["page"] == 1
        assert page1_payload["page_size"] == 20
        assert page1_payload["total_pages"] == math.ceil(total_expected / 20)
        assert len(page1_payload["items"]) == 20, f"Page 1 should have 20 items, got {len(page1_payload['items'])}"
        assert page1_payload["has_next"] is True
        assert page1_payload["has_prev"] is False

        page2_response = client.get(
            "/api/v1/admin/background-checks/cases?status=all&page=2&page_size=20",
            headers=headers,
        )
        assert page2_response.status_code == 200
        page2_payload = page2_response.json()
        expected_page2_items = total_expected - 20
        assert page2_payload["total"] == total_expected, f"Page 2: Expected total={total_expected}, got {page2_payload['total']}"
        assert page2_payload["page"] == 2, f"Expected page=2, got {page2_payload['page']}"
        assert page2_payload["total_pages"] == math.ceil(total_expected / 20), f"Expected total_pages=2, got {page2_payload['total_pages']}"
        assert len(page2_payload["items"]) == expected_page2_items, f"Page 2 should have {expected_page2_items} items, got {len(page2_payload['items'])}"
        assert page2_payload["has_next"] is False, "Page 2 should not have next page"
        assert page2_payload["has_prev"] is True, "Page 2 should have previous page"

    def test_clear_bgc_mismatch_and_reset_bgc(self, client, db):
        permission_service = PermissionService(db)

        admin = User(
            email="admin_reset_bgc@example.com",
            hashed_password=get_password_hash("AdminPass123!"),
            first_name="Admin",
            last_name="Reset",
            phone="+12125557777",
            zip_code="10001",
        )
        db.add(admin)
        db.flush()
        permission_service.assign_role(admin.id, RoleName.ADMIN)

        instructor_user = User(
            email="reset_bgc_instructor@example.com",
            hashed_password=get_password_hash("InstructorPass123!"),
            first_name="Reset",
            last_name="Instructor",
            phone="+13475557777",
            zip_code="10002",
        )
        db.add(instructor_user)
        db.flush()
        permission_service.assign_role(instructor_user.id, RoleName.INSTRUCTOR)

        profile = InstructorProfile(
            user_id=instructor_user.id,
            bgc_name_mismatch=True,
            bgc_status="passed",
            bgc_report_id="rpt_reset123",
            bgc_report_result="clear",
            bgc_env="sandbox",
            bgc_completed_at=datetime.now(timezone.utc),
            bgc_valid_until=datetime.now(timezone.utc) + timedelta(days=30),
            bgc_eta=datetime.now(timezone.utc) + timedelta(days=2),
            bgc_invited_at=datetime.now(timezone.utc) - timedelta(days=3),
            bgc_includes_canceled=True,
            bgc_in_dispute=True,
            bgc_dispute_note="Need rerun",
            bgc_dispute_opened_at=datetime.now(timezone.utc) - timedelta(days=1),
            bgc_pre_adverse_notice_id="pre_123",
            bgc_pre_adverse_sent_at=datetime.now(timezone.utc) - timedelta(days=1),
            bgc_final_adverse_sent_at=datetime.now(timezone.utc) - timedelta(hours=12),
            bgc_review_email_sent_at=datetime.now(timezone.utc) - timedelta(hours=6),
            checkr_candidate_id="cand_123",
            checkr_invitation_id="inv_123",
            bgc_note="review",
            verified_first_name="Reset",
            verified_last_name="Instructor",
            verified_dob=datetime.now(timezone.utc).date(),
            bgc_submitted_first_name="Reset",
            bgc_submitted_last_name="Mismatch",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        token = create_access_token(data={"sub": admin.email})
        headers = {"Authorization": f"Bearer {token}"}

        clear_response = client.post(
            f"/api/v1/admin/instructors/{profile.id}/clear-bgc-mismatch",
            headers=headers,
        )
        assert clear_response.status_code == 200
        assert clear_response.json()["bgc_name_mismatch"] is False

        db.refresh(profile)
        assert profile.bgc_name_mismatch is False
        assert profile.bgc_status == "passed"

        reset_response = client.post(
            f"/api/v1/admin/instructors/{profile.id}/reset-bgc",
            headers=headers,
        )
        assert reset_response.status_code == 200
        reset_payload = reset_response.json()
        assert reset_payload["bgc_name_mismatch"] is False
        assert reset_payload["bgc_status"] is None

        db.refresh(profile)
        assert profile.bgc_name_mismatch is False
        assert profile.bgc_status is None
        assert profile.bgc_report_id is None
        assert profile.bgc_report_result is None
        assert profile.bgc_completed_at is None
        assert profile.bgc_valid_until is None
        assert profile.bgc_eta is None
        assert profile.bgc_invited_at is None
        assert profile.bgc_includes_canceled is False
        assert profile.bgc_in_dispute is False
        assert profile.bgc_dispute_note is None
        assert profile.bgc_pre_adverse_notice_id is None
        assert profile.bgc_pre_adverse_sent_at is None
        assert profile.bgc_final_adverse_sent_at is None
        assert profile.bgc_review_email_sent_at is None
        assert profile.checkr_candidate_id is None
        assert profile.checkr_invitation_id is None
        assert profile.bgc_note is None
        assert profile.bgc_submitted_first_name is None
        assert profile.bgc_submitted_last_name is None
        assert profile.verified_first_name == "Reset"
        assert profile.verified_last_name == "Instructor"
        assert profile.verified_dob is not None

    def test_reset_bgc_requires_admin_and_blocks_live_instructor(self, client, db):
        permission_service = PermissionService(db)

        admin = User(
            email="admin_live_block@example.com",
            hashed_password=get_password_hash("AdminPass123!"),
            first_name="Admin",
            last_name="Live",
            phone="+12125558888",
            zip_code="10001",
        )
        student = User(
            email="student_live_block@example.com",
            hashed_password=get_password_hash("StudentPass123!"),
            first_name="Student",
            last_name="Viewer",
            phone="+13475558888",
            zip_code="10002",
        )
        instructor_user = User(
            email="live_reset_instructor@example.com",
            hashed_password=get_password_hash("InstructorPass123!"),
            first_name="Live",
            last_name="Instructor",
            phone="+13475559999",
            zip_code="10003",
        )
        db.add_all([admin, student, instructor_user])
        db.flush()
        permission_service.assign_role(admin.id, RoleName.ADMIN)
        permission_service.assign_role(instructor_user.id, RoleName.INSTRUCTOR)

        profile = InstructorProfile(
            user_id=instructor_user.id,
            is_live=True,
            bgc_name_mismatch=True,
            bgc_status="passed",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        student_token = create_access_token(data={"sub": student.email})
        student_headers = {"Authorization": f"Bearer {student_token}"}
        forbidden_response = client.post(
            f"/api/v1/admin/instructors/{profile.id}/reset-bgc",
            headers=student_headers,
        )
        assert forbidden_response.status_code == 403

        admin_token = create_access_token(data={"sub": admin.email})
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        live_response = client.post(
            f"/api/v1/admin/instructors/{profile.id}/reset-bgc",
            headers=admin_headers,
        )
        assert live_response.status_code == 400
        assert live_response.json()["code"] == "bgc_reset_live_block"
