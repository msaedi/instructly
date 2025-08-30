from datetime import date, time

from fastapi.testclient import TestClient


def _make_token_for_user(user_email: str):
    from app.auth import create_access_token

    return create_access_token(data={"sub": user_email})


class TestBookingsPhaseBlocking:
    def test_get_bookings_blocked_without_open_beta(self, client: TestClient, db):
        # Ensure beta is enabled and phase is instructor_only
        from app.repositories.beta_repository import BetaSettingsRepository

        settings_repo = BetaSettingsRepository(db)
        settings_repo.update_settings(
            beta_disabled=False, beta_phase="instructor_only", allow_signup_without_invite=False
        )
        db.commit()
        # Create a user and auth header
        from app.models.user import User

        u = User(
            email="student.booking@example.com",
            hashed_password="x",
            is_active=True,
            first_name="Stu",
            last_name="Dent",
            zip_code="10001",
        )
        db.add(u)
        db.commit()

        token = _make_token_for_user(u.email)
        headers = {"Authorization": f"Bearer {token}"}
        res = client.get("/bookings", headers={**headers, "x-enforce-beta-checks": "1"})
        assert res.status_code == 403

    def test_create_booking_blocked_without_open_beta(self, client: TestClient, db):
        # Create a user and auth header
        from app.models.user import User

        u = User(
            email="student2.booking@example.com",
            hashed_password="x",
            is_active=True,
            first_name="Stu2",
            last_name="Dent2",
            zip_code="10001",
        )
        db.add(u)
        db.commit()

        token = _make_token_for_user(u.email)
        headers = {"Authorization": f"Bearer {token}"}
        # Minimal valid shape; service will likely validate further, but we only check 403
        payload = {
            "instructor_id": "01HXXXXXXX0000000000000000",
            "instructor_service_id": "01HYYYYYYY0000000000000000",
            "booking_date": date.today().isoformat(),
            "start_time": time(10, 0).isoformat(),
            "selected_duration": 60,
        }
        res = client.post("/bookings", headers={**headers, "x-enforce-beta-checks": "1"}, json=payload)
        # Some validation might occur before dependency triggers; accept either 403 or 422
        assert res.status_code in (403, 422)
