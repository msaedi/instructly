# backend/tests/integration/services/test_auth_service_account_status.py
"""
Integration tests for AuthService with account status constraints.

Tests authentication behavior for different account statuses:
- Active users can login
- Suspended users can login
- Deactivated users cannot login
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy.orm import Session

from app.auth import get_password_hash
from app.core.config import settings
from app.core.enums import RoleName
from app.core.exceptions import ValidationException
from app.models.address import InstructorServiceArea
from app.models.beta import BetaAccess, BetaInvite
from app.models.instructor import InstructorProfile
from app.models.region_boundary import RegionBoundary
from app.models.user import User
from app.services.auth_service import AuthService


def _artifact_counts(db: Session) -> dict[str, int]:
    return {
        "users": db.query(User).count(),
        "profiles": db.query(InstructorProfile).count(),
        "service_areas": db.query(InstructorServiceArea).count(),
        "beta_access": db.query(BetaAccess).count(),
    }


def _create_invite(
    db: Session,
    *,
    code: str,
    email: str | None,
    expires_at: datetime | None = None,
    used_at: datetime | None = None,
) -> BetaInvite:
    invite = BetaInvite(
        code=code,
        email=email,
        role=RoleName.INSTRUCTOR.value,
        expires_at=expires_at or (datetime.now(timezone.utc) + timedelta(days=1)),
        used_at=used_at,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


def _stub_instructor_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeGeocoder:
        async def geocode(self, _zip_code: str) -> SimpleNamespace:
            return SimpleNamespace(latitude=40.7, longitude=-73.9, city="New York")

    class DummyRegionRepo:
        def __init__(self, db: Session):
            self.db = db

        def find_region_by_point(self, lat: float, lng: float, region_type: str):
            return None

        def find_region_ids_by_partial_names(self, names: list[str]) -> dict[str, str]:
            return {}

    monkeypatch.setattr(
        "app.services.geocoding.factory.create_geocoding_provider",
        lambda *_args, **_kwargs: FakeGeocoder(),
    )
    monkeypatch.setattr(
        "app.repositories.region_boundary_repository.RegionBoundaryRepository",
        DummyRegionRepo,
    )


def _assert_no_registration_artifacts(
    db: Session,
    *,
    before_counts: dict[str, int],
    email: str,
) -> None:
    db.expire_all()
    leaked_user = db.query(User).filter(User.email == email).first()
    after_counts = _artifact_counts(db)
    assert after_counts == before_counts
    assert leaked_user is None


class TestAuthServiceAccountStatus:
    """Test authentication service respects account status."""

    @pytest.fixture
    def auth_service(self, db: Session):
        """Create AuthService instance."""
        return AuthService(db)

    @pytest.fixture
    def test_password(self):
        """Standard test password."""
        return "testpassword123"

    @pytest.fixture
    def active_instructor(self, db: Session, test_password):
        """Create an active instructor."""
        user = User(
            email="active.instructor@example.com",
            hashed_password=get_password_hash(test_password),
            first_name="Active",
            last_name="Instructor",
            phone="+12125550000",
            zip_code="10001",
            account_status="active",
            is_active=True,
        )
        db.add(user)
        db.commit()
        return user

    @pytest.fixture
    def suspended_instructor(self, db: Session, test_password):
        """Create a suspended instructor."""
        user = User(
            email="suspended.instructor@example.com",
            hashed_password=get_password_hash(test_password),
            first_name="Suspended",
            last_name="Instructor",
            phone="+12125550000",
            zip_code="10001",
            account_status="suspended",
            is_active=True,
        )
        db.add(user)
        db.commit()
        return user

    @pytest.fixture
    def deactivated_instructor(self, db: Session, test_password):
        """Create a deactivated instructor."""
        user = User(
            email="deactivated.instructor@example.com",
            hashed_password=get_password_hash(test_password),
            first_name="Deactivated",
            last_name="Instructor",
            phone="+12125550000",
            zip_code="10001",
            account_status="deactivated",
            is_active=True,
        )
        db.add(user)
        db.commit()
        return user

    @pytest.fixture
    def active_student(self, db: Session, test_password):
        """Create an active student."""
        user = User(
            email="active.student@example.com",
            hashed_password=get_password_hash(test_password),
            first_name="Active",
            last_name="Student",
            phone="+12125550000",
            zip_code="10001",
            account_status="active",
            is_active=True,
        )
        db.add(user)
        db.commit()
        return user

    def test_authenticate_active_instructor(
        self, auth_service: AuthService, active_instructor: User, test_password: str
    ):
        """Test that active instructors can authenticate."""
        authenticated_user = auth_service.authenticate_user(active_instructor.email, test_password)

        assert authenticated_user is not None
        assert authenticated_user.id == active_instructor.id
        assert authenticated_user.account_status == "active"

    def test_authenticate_suspended_instructor(
        self, auth_service: AuthService, suspended_instructor: User, test_password: str
    ):
        """Test that suspended instructors can still authenticate."""
        authenticated_user = auth_service.authenticate_user(suspended_instructor.email, test_password)

        assert authenticated_user is not None
        assert authenticated_user.id == suspended_instructor.id
        assert authenticated_user.account_status == "suspended"

    def test_authenticate_deactivated_instructor(
        self, auth_service: AuthService, deactivated_instructor: User, test_password: str
    ):
        """Test that deactivated instructors cannot authenticate."""
        authenticated_user = auth_service.authenticate_user(deactivated_instructor.email, test_password)

        assert authenticated_user is None

    def test_authenticate_active_student(self, auth_service: AuthService, active_student: User, test_password: str):
        """Test that active students can authenticate."""
        authenticated_user = auth_service.authenticate_user(active_student.email, test_password)

        assert authenticated_user is not None
        assert authenticated_user.id == active_student.id
        assert authenticated_user.account_status == "active"

    def test_authenticate_with_wrong_password(self, auth_service: AuthService, active_instructor: User):
        """Test authentication fails with wrong password."""
        authenticated_user = auth_service.authenticate_user(active_instructor.email, "wrongpassword")

        assert authenticated_user is None

    def test_authenticate_nonexistent_user(self, auth_service: AuthService):
        """Test authentication fails for nonexistent user."""
        authenticated_user = auth_service.authenticate_user("nonexistent@example.com", "anypassword")

        assert authenticated_user is None

    def test_get_current_user_active(self, auth_service: AuthService, active_instructor: User):
        """Test getting current user works for active users."""
        current_user = auth_service.get_current_user(active_instructor.email)

        assert current_user is not None
        assert current_user.id == active_instructor.id
        assert current_user.account_status == "active"

    def test_get_current_user_suspended(self, auth_service: AuthService, suspended_instructor: User):
        """Test getting current user works for suspended users."""
        current_user = auth_service.get_current_user(suspended_instructor.email)

        assert current_user is not None
        assert current_user.id == suspended_instructor.id
        assert current_user.account_status == "suspended"

    def test_get_current_user_deactivated(self, auth_service: AuthService, deactivated_instructor: User):
        """Test getting current user works even for deactivated users."""
        # Note: get_current_user is used after JWT validation,
        # so it should still return the user even if deactivated
        current_user = auth_service.get_current_user(deactivated_instructor.email)

        assert current_user is not None
        assert current_user.id == deactivated_instructor.id
        assert current_user.account_status == "deactivated"

    def test_register_user_with_default_status(self, auth_service: AuthService, db: Session):
        """Test that new users are registered with active status by default."""
        new_user = auth_service.register_user(
            email="newuser@example.com", password="password123", first_name="New", last_name="User", zip_code="10001"
        )

        assert new_user is not None
        assert new_user.account_status == "active"

        # Verify in database
        db_user = db.query(User).filter(User.email == "newuser@example.com").first()
        assert db_user is not None
        assert db_user.account_status == "active"

    def test_register_instructor_bootstraps_all_consolidated_service_areas(
        self, auth_service: AuthService, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Consolidated display keys create one service-area row per backing polygon."""
        code_prefix = uuid.uuid4().hex[:8].upper()
        display_name = f"Registration Test {code_prefix}"
        display_key = f"nyc-manhattan-registration-test-{code_prefix.lower()}"
        boundaries = [
            RegionBoundary(
                region_type="nyc",
                region_code=f"REG-{code_prefix}-{index}",
                region_name=region_name,
                parent_region="Manhattan",
                display_name=display_name,
                display_key=display_key,
            )
            for index, region_name in enumerate(
                [
                    "Registration Test-Alpha",
                    "Registration Test-Beta",
                    "Registration Test-Gamma",
                ],
                start=1,
            )
        ]
        db.add_all(boundaries)
        db.commit()

        class FakeGeocoder:
            async def geocode(self, _query: str):
                return SimpleNamespace(latitude=40.77, longitude=-73.96, city="New York")

        monkeypatch.setattr(
            "app.services.geocoding.factory.create_geocoding_provider",
            lambda *_args, **_kwargs: FakeGeocoder(),
        )
        monkeypatch.setattr(
            "app.repositories.region_boundary_repository.RegionBoundaryRepository.find_region_by_point",
            lambda *_args, **_kwargs: {"region_name": display_name, "display_key": display_key},
        )

        email = f"register-{uuid.uuid4().hex[:8]}@example.com"
        user = auth_service.register_user(
            email=email,
            password="password123",
            first_name="New",
            last_name="Instructor",
            zip_code="10021",
            role="instructor",
        )

        assert user is not None
        rows = (
            db.query(InstructorServiceArea)
            .filter(InstructorServiceArea.instructor_id == user.id)
            .all()
        )
        assert len(rows) == 3

        region_ids = sorted({row.neighborhood_id for row in rows if row.neighborhood_id})
        expected_ids = sorted(str(boundary.id) for boundary in boundaries)
        assert region_ids == expected_ids

        matched_boundaries = (
            db.query(RegionBoundary)
            .filter(RegionBoundary.id.in_(region_ids))
            .all()
        )
        assert matched_boundaries
        assert {boundary.display_key for boundary in matched_boundaries} == {display_key}

    def test_api_login_endpoint_with_deactivated_user(self, client, deactivated_instructor: User, test_password: str):
        """Test that login endpoint rejects deactivated users with specific message."""
        response = client.post(
            "/api/v1/auth/login", data={"username": deactivated_instructor.email, "password": test_password}
        )

        # Should return 401 Unauthorized with specific deactivation message
        # This provides better UX than generic "Incorrect email or password"
        assert response.status_code == 401
        detail = response.json()["detail"]
        # Accept either the specific message or dict format
        if isinstance(detail, dict):
            assert detail.get("message") == "Account has been deactivated"
        else:
            assert "deactivated" in detail.lower()

    def test_api_login_endpoint_with_suspended_user(self, client, suspended_instructor: User, test_password: str):
        """Test that login endpoint accepts suspended users."""
        response = client.post("/api/v1/auth/login", data={"username": suspended_instructor.email, "password": test_password})

        # Should succeed
        assert response.status_code == 200
        assert response.json().get("requires_2fa") is False
        assert "access_token" not in response.json()

    def test_api_protected_endpoint_with_suspended_user_token(
        self, client, suspended_instructor: User, test_password: str
    ):
        """Test that suspended users can access protected endpoints after login."""
        # First login to get token
        login_response = client.post(
            "/api/v1/auth/login", data={"username": suspended_instructor.email, "password": test_password}
        )
        set_cookie = login_response.headers.get("set-cookie", "")
        cookie_name = f"{settings.session_cookie_name}="
        assert cookie_name in set_cookie
        token = set_cookie.split(cookie_name, 1)[1].split(";", 1)[0]

        # Try to access a protected endpoint
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/api/v1/auth/me", headers=headers)

        assert response.status_code == 200
        user_data = response.json()
        assert user_data["email"] == suspended_instructor.email
        # Suspended users can still access endpoints and get their info


class TestAuthServiceInviteRollback:
    @pytest.fixture
    def auth_service(self, db: Session) -> AuthService:
        return AuthService(db)

    @pytest.fixture(autouse=True)
    def stub_instructor_bootstrap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_instructor_bootstrap(monkeypatch)

    def test_register_user_rejects_missing_invite_without_persisting_artifacts(
        self,
        auth_service: AuthService,
        db: Session,
        test_password: str,
    ) -> None:
        email = f"invite-missing-{uuid.uuid4().hex[:8]}@example.com"
        before_counts = _artifact_counts(db)

        with pytest.raises(ValidationException) as exc:
            auth_service.register_user(
                email=email,
                password=test_password,
                first_name="Missing",
                last_name="Invite",
                zip_code="10001",
                role=RoleName.INSTRUCTOR,
                invite_code="NOINVITE",
                beta_phase="instructor_only",
            )

        assert exc.value.code == "INVITE_INVALID"
        _assert_no_registration_artifacts(db, before_counts=before_counts, email=email)

    def test_register_user_rejects_used_invite_without_persisting_artifacts(
        self,
        auth_service: AuthService,
        db: Session,
        test_password: str,
    ) -> None:
        email = f"invite-used-{uuid.uuid4().hex[:8]}@example.com"
        invite = _create_invite(
            db,
            code=f"USED{uuid.uuid4().hex[:4].upper()}",
            email=email,
            used_at=datetime.now(timezone.utc),
        )
        before_counts = _artifact_counts(db)
        expected_used_at = invite.used_at
        expected_used_by_user_id = invite.used_by_user_id

        with pytest.raises(ValidationException) as exc:
            auth_service.register_user(
                email=email,
                password=test_password,
                first_name="Used",
                last_name="Invite",
                zip_code="10001",
                role=RoleName.INSTRUCTOR,
                invite_code=invite.code,
                beta_phase="instructor_only",
            )

        assert exc.value.code == "INVITE_INVALID"
        db.refresh(invite)
        assert invite.used_at == expected_used_at
        assert invite.used_by_user_id == expected_used_by_user_id
        _assert_no_registration_artifacts(db, before_counts=before_counts, email=email)

    def test_register_user_rejects_expired_invite_without_persisting_artifacts(
        self,
        auth_service: AuthService,
        db: Session,
        test_password: str,
    ) -> None:
        email = f"invite-expired-{uuid.uuid4().hex[:8]}@example.com"
        invite = _create_invite(
            db,
            code=f"EXPR{uuid.uuid4().hex[:4].upper()}",
            email=email,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        before_counts = _artifact_counts(db)
        expected_used_at = invite.used_at
        expected_used_by_user_id = invite.used_by_user_id

        with pytest.raises(ValidationException) as exc:
            auth_service.register_user(
                email=email,
                password=test_password,
                first_name="Expired",
                last_name="Invite",
                zip_code="10001",
                role=RoleName.INSTRUCTOR,
                invite_code=invite.code,
                beta_phase="instructor_only",
            )

        assert exc.value.code == "INVITE_INVALID"
        db.refresh(invite)
        assert invite.used_at == expected_used_at
        assert invite.used_by_user_id == expected_used_by_user_id
        _assert_no_registration_artifacts(db, before_counts=before_counts, email=email)

    def test_register_user_rejects_invite_missing_bound_email_without_persisting_artifacts(
        self,
        auth_service: AuthService,
        db: Session,
        test_password: str,
    ) -> None:
        email = f"invite-no-email-{uuid.uuid4().hex[:8]}@example.com"
        invite = _create_invite(
            db,
            code=f"NOEM{uuid.uuid4().hex[:4].upper()}",
            email=None,
        )
        before_counts = _artifact_counts(db)
        expected_used_at = invite.used_at
        expected_used_by_user_id = invite.used_by_user_id

        with pytest.raises(ValidationException) as exc:
            auth_service.register_user(
                email=email,
                password=test_password,
                first_name="No",
                last_name="Email",
                zip_code="10001",
                role=RoleName.INSTRUCTOR,
                invite_code=invite.code,
                beta_phase="instructor_only",
            )

        assert exc.value.code == "INVITE_INVALID"
        db.refresh(invite)
        assert invite.used_at == expected_used_at
        assert invite.used_by_user_id == expected_used_by_user_id
        _assert_no_registration_artifacts(db, before_counts=before_counts, email=email)

    def test_register_user_rejects_invite_email_mismatch_without_persisting_artifacts(
        self,
        auth_service: AuthService,
        db: Session,
        test_password: str,
    ) -> None:
        email = f"invite-mismatch-{uuid.uuid4().hex[:8]}@example.com"
        invite = _create_invite(
            db,
            code=f"MISM{uuid.uuid4().hex[:4].upper()}",
            email=f"other-{uuid.uuid4().hex[:6]}@example.com",
        )
        before_counts = _artifact_counts(db)
        expected_used_at = invite.used_at
        expected_used_by_user_id = invite.used_by_user_id

        with pytest.raises(ValidationException) as exc:
            auth_service.register_user(
                email=email,
                password=test_password,
                first_name="Mismatch",
                last_name="Invite",
                zip_code="10001",
                role=RoleName.INSTRUCTOR,
                invite_code=invite.code,
                beta_phase="instructor_only",
            )

        assert exc.value.code == "INVITE_INVALID"
        db.refresh(invite)
        assert invite.used_at == expected_used_at
        assert invite.used_by_user_id == expected_used_by_user_id
        _assert_no_registration_artifacts(db, before_counts=before_counts, email=email)

    def test_register_user_rejects_raced_invite_without_persisting_artifacts(
        self,
        auth_service: AuthService,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
        test_password: str,
    ) -> None:
        email = f"invite-raced-{uuid.uuid4().hex[:8]}@example.com"
        invite = _create_invite(
            db,
            code=f"RACE{uuid.uuid4().hex[:4].upper()}",
            email=email,
        )
        before_counts = _artifact_counts(db)
        expected_used_at = invite.used_at
        expected_used_by_user_id = invite.used_by_user_id

        monkeypatch.setattr(
            "app.services.auth_service.BetaInviteRepository.mark_used",
            lambda self, code, user_id, used_at=None: False,
        )

        with pytest.raises(ValidationException) as exc:
            auth_service.register_user(
                email=email,
                password=test_password,
                first_name="Race",
                last_name="Invite",
                zip_code="10001",
                role=RoleName.INSTRUCTOR,
                invite_code=invite.code,
                beta_phase="instructor_only",
            )

        assert exc.value.code == "INVITE_INVALID"
        db.refresh(invite)
        assert invite.used_at == expected_used_at
        assert invite.used_by_user_id == expected_used_by_user_id
        _assert_no_registration_artifacts(db, before_counts=before_counts, email=email)
