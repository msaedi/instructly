from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call

import pytest
from sqlalchemy.exc import IntegrityError

from app.auth import DUMMY_HASH_FOR_TIMING_ATTACK
from app.core.enums import RoleName
from app.core.exceptions import NotFoundException, ValidationException
import app.services.auth_service as auth_module
from app.services.auth_service import AuthService, invite_required_for_registration


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.refresh = MagicMock()
    db.close = MagicMock()
    return db


@pytest.fixture
def mock_user_repo():
    return MagicMock()


@pytest.fixture
def mock_instructor_repo():
    return MagicMock()


@pytest.fixture
def mock_service_area_repo():
    return MagicMock()


@pytest.fixture
def service(mock_db, mock_user_repo, mock_instructor_repo, mock_service_area_repo, monkeypatch):
    monkeypatch.setattr(
        auth_module.RepositoryFactory,
        "create_instructor_service_area_repository",
        lambda db: mock_service_area_repo,
    )
    return AuthService(
        db=mock_db,
        user_repository=mock_user_repo,
        instructor_repository=mock_instructor_repo,
    )


def _prepare_registration_user(monkeypatch, mock_user_repo, *, user_id: str, first_name: str, email: str):
    user = SimpleNamespace(id=user_id, first_name=first_name, email=email)
    mock_user_repo.find_one_by.return_value = None
    mock_user_repo.create.return_value = user
    permission_service = Mock()
    monkeypatch.setattr(auth_module, "PermissionService", Mock(return_value=permission_service))
    monkeypatch.setattr(auth_module, "get_password_hash", lambda pw: "hashed")
    return user, permission_service


class TestAuthServiceCoverage:
    @pytest.mark.parametrize(
        ("role", "phase", "expected"),
        [
            (RoleName.STUDENT.value, "public", False),
            (RoleName.INSTRUCTOR.value, "instructor_only", True),
            (RoleName.STUDENT.value, "instructor_only", False),
        ],
    )
    def test_invite_required_for_registration_matrix(self, role, phase, expected):
        assert invite_required_for_registration(role, phase) is expected

    def test_register_user_instructor_with_region_and_service_area(
        self, service, mock_user_repo, mock_instructor_repo, mock_service_area_repo, monkeypatch
    ):
        user = SimpleNamespace(id="user-1", first_name="Riley", email="riley@example.com")
        mock_user_repo.find_one_by.return_value = None
        mock_user_repo.create.return_value = user

        permission_service = Mock()
        monkeypatch.setattr(auth_module, "PermissionService", Mock(return_value=permission_service))
        monkeypatch.setattr(auth_module, "get_password_hash", lambda pw: "hashed")

        class GeoProvider:
            async def geocode(self, zip_code):
                return SimpleNamespace(city="Brooklyn", latitude=40.7, longitude=-73.9)

        monkeypatch.setattr(
            "app.services.geocoding.factory.create_geocoding_provider",
            lambda: GeoProvider(),
        )

        class DummyRegionRepo:
            def __init__(self, db):
                self.db = db

            def find_region_by_point(self, lat, lng, region_type):
                return {"region_name": "Brooklyn"}

            def find_region_ids_by_partial_names(self, names):
                return {"Brooklyn": "rb-123"}

        monkeypatch.setattr(
            "app.repositories.region_boundary_repository.RegionBoundaryRepository",
            DummyRegionRepo,
        )

        result = service.register_user(
            email="riley@example.com",
            password="pw",
            first_name="Riley",
            last_name="Test",
            zip_code="11201",
            role=RoleName.INSTRUCTOR,
        )

        assert result is user
        permission_service.assign_role.assert_called_once_with(user.id, RoleName.INSTRUCTOR)
        mock_instructor_repo.create.assert_called_once()
        mock_service_area_repo.upsert_area.assert_called_once_with(
            instructor_id=user.id,
            neighborhood_id="rb-123",
            coverage_type="primary",
            is_active=True,
        )

    def test_register_user_instructor_geocode_failure_uses_defaults(
        self, service, mock_user_repo, mock_instructor_repo, mock_service_area_repo, monkeypatch
    ):
        user = SimpleNamespace(id="user-2", first_name="Jamie", email="jamie@example.com")
        mock_user_repo.find_one_by.return_value = None
        mock_user_repo.create.return_value = user

        permission_service = Mock()
        monkeypatch.setattr(auth_module, "PermissionService", Mock(return_value=permission_service))
        monkeypatch.setattr(auth_module, "get_password_hash", lambda pw: "hashed")

        def _boom():
            raise RuntimeError("geocode failed")

        monkeypatch.setattr(
            "app.services.geocoding.factory.create_geocoding_provider",
            _boom,
        )

        result = service.register_user(
            email="jamie@example.com",
            password="pw",
            first_name="Jamie",
            last_name="Test",
            zip_code="10001",
            role=RoleName.INSTRUCTOR,
        )

        assert result is user
        create_kwargs = mock_instructor_repo.create.call_args.kwargs
        assert create_kwargs["bio"] == "Jamie is a New York-based instructor."
        mock_service_area_repo.upsert_area.assert_not_called()

    def test_register_user_instructor_fallback_region_lookup(
        self, service, mock_user_repo, mock_instructor_repo, mock_service_area_repo, monkeypatch
    ):
        user = SimpleNamespace(id="user-6", first_name="Quinn", email="quinn@example.com")
        mock_user_repo.find_one_by.return_value = None
        mock_user_repo.create.return_value = user

        permission_service = Mock()
        monkeypatch.setattr(auth_module, "PermissionService", Mock(return_value=permission_service))
        monkeypatch.setattr(auth_module, "get_password_hash", lambda pw: "hashed")

        class GeoProvider:
            async def geocode(self, zip_code):
                return SimpleNamespace(city="Queens", latitude=40.7, longitude=-73.8)

        monkeypatch.setattr(
            "app.services.geocoding.factory.create_geocoding_provider",
            lambda: GeoProvider(),
        )

        class DummyRegionRepo:
            call_count = 0

            def __init__(self, db):
                self.db = db

            def find_region_by_point(self, lat, lng, region_type):
                return None

            def find_region_ids_by_partial_names(self, names):
                DummyRegionRepo.call_count += 1
                if DummyRegionRepo.call_count == 1:
                    return {}
                return {"Queens": "rb-456"}

        monkeypatch.setattr(
            "app.repositories.region_boundary_repository.RegionBoundaryRepository",
            DummyRegionRepo,
        )

        result = service.register_user(
            email="quinn@example.com",
            password="pw",
            first_name="Quinn",
            last_name="Test",
            zip_code="11101",
            role=RoleName.INSTRUCTOR,
        )

        assert result is user
        mock_service_area_repo.upsert_area.assert_called_once_with(
            instructor_id=user.id,
            neighborhood_id="rb-456",
            coverage_type="primary",
            is_active=True,
        )

    def test_register_user_existing_email_returns_none(self, service, monkeypatch):
        service.user_repository.find_one_by.return_value = SimpleNamespace(id="existing")
        monkeypatch.setattr(auth_module, "get_password_hash", lambda pw: "hashed")

        result = service.register_user(
            email="exists@example.com",
            password="pw",
            first_name="A",
            last_name="B",
            zip_code="10001",
        )

        assert result is None

    def test_register_user_student_skips_instructor_setup(
        self, service, mock_user_repo, mock_instructor_repo, mock_service_area_repo, monkeypatch
    ):
        user = SimpleNamespace(id="user-7", first_name="Sam", email="sam@example.com")
        mock_user_repo.find_one_by.return_value = None
        mock_user_repo.create.return_value = user

        permission_service = Mock()
        monkeypatch.setattr(auth_module, "PermissionService", Mock(return_value=permission_service))
        monkeypatch.setattr(auth_module, "get_password_hash", lambda pw: "hashed")

        result = service.register_user(
            email="sam@example.com",
            password="pw",
            first_name="Sam",
            last_name="Test",
            zip_code="10001",
            role=RoleName.STUDENT,
        )

        assert result is user
        mock_instructor_repo.create.assert_not_called()
        mock_service_area_repo.upsert_area.assert_not_called()

    def test_register_user_instructor_no_zip_uses_service_area_guess(
        self, service, mock_user_repo, mock_instructor_repo, mock_service_area_repo, monkeypatch
    ):
        user = SimpleNamespace(id="user-8", first_name="Rae", email="rae@example.com")
        mock_user_repo.find_one_by.return_value = None
        mock_user_repo.create.return_value = user

        permission_service = Mock()
        monkeypatch.setattr(auth_module, "PermissionService", Mock(return_value=permission_service))
        monkeypatch.setattr(auth_module, "get_password_hash", lambda pw: "hashed")

        class DummyRegionRepo:
            def __init__(self, db):
                self.db = db

            def find_region_ids_by_partial_names(self, names):
                return {"Manhattan": "rb-789"}

        monkeypatch.setattr(
            "app.repositories.region_boundary_repository.RegionBoundaryRepository",
            DummyRegionRepo,
        )

        result = service.register_user(
            email="rae@example.com",
            password="pw",
            first_name="Rae",
            last_name="Test",
            zip_code="",
            role=RoleName.INSTRUCTOR,
        )

        assert result is user
        mock_service_area_repo.upsert_area.assert_called_once_with(
            instructor_id=user.id,
            neighborhood_id="rb-789",
            coverage_type="primary",
            is_active=True,
        )

    def test_register_user_instructor_geocode_none_fallback(
        self, service, mock_user_repo, mock_instructor_repo, mock_service_area_repo, monkeypatch
    ):
        user = SimpleNamespace(id="user-9", first_name="Drew", email="drew@example.com")
        mock_user_repo.find_one_by.return_value = None
        mock_user_repo.create.return_value = user

        permission_service = Mock()
        monkeypatch.setattr(auth_module, "PermissionService", Mock(return_value=permission_service))
        monkeypatch.setattr(auth_module, "get_password_hash", lambda pw: "hashed")

        class GeoProvider:
            async def geocode(self, zip_code):
                return None

        monkeypatch.setattr(
            "app.services.geocoding.factory.create_geocoding_provider",
            lambda: GeoProvider(),
        )

        class DummyRegionRepo:
            def __init__(self, db):
                self.db = db

            def find_region_by_point(self, lat, lng, region_type):
                return None

            def find_region_ids_by_partial_names(self, names):
                return {"Manhattan": "rb-101"}

        monkeypatch.setattr(
            "app.repositories.region_boundary_repository.RegionBoundaryRepository",
            DummyRegionRepo,
        )

        result = service.register_user(
            email="drew@example.com",
            password="pw",
            first_name="Drew",
            last_name="Test",
            zip_code="10001",
            role=RoleName.INSTRUCTOR,
        )

        assert result is user
        mock_service_area_repo.upsert_area.assert_called_once()

    def test_register_user_instructor_uses_display_key_resolution(
        self, service, mock_user_repo, mock_instructor_repo, mock_service_area_repo, monkeypatch
    ):
        user, permission_service = _prepare_registration_user(
            monkeypatch,
            mock_user_repo,
            user_id="user-display",
            first_name="Casey",
            email="casey@example.com",
        )

        class GeoProvider:
            async def geocode(self, zip_code):
                return SimpleNamespace(city="Queens", latitude=40.75, longitude=-73.94)

        monkeypatch.setattr(
            "app.services.geocoding.factory.create_geocoding_provider",
            lambda: GeoProvider(),
        )

        class DummyRegionRepo:
            def __init__(self, db):
                self.db = db

            def find_region_by_point(self, lat, lng, region_type):
                return {"region_name": "Astoria", "display_key": "nyc-queens-astoria"}

            def resolve_display_keys_to_ids(self, display_keys):
                assert display_keys == ["nyc-queens-astoria"]
                return {"nyc-queens-astoria": ["rb-1", "rb-2"]}

            def find_region_ids_by_partial_names(self, names):
                return {}

        monkeypatch.setattr(
            "app.repositories.region_boundary_repository.RegionBoundaryRepository",
            DummyRegionRepo,
        )

        result = service.register_user(
            email="casey@example.com",
            password="pw",
            first_name="Casey",
            last_name="Test",
            zip_code="11101",
            role=RoleName.INSTRUCTOR,
        )

        assert result is user
        permission_service.assign_role.assert_called_once_with(user.id, RoleName.INSTRUCTOR)
        assert mock_service_area_repo.upsert_area.call_args_list == [
            call(
                instructor_id=user.id,
                neighborhood_id="rb-1",
                coverage_type="primary",
                is_active=True,
            ),
            call(
                instructor_id=user.id,
                neighborhood_id="rb-2",
                coverage_type="primary",
                is_active=True,
            ),
        ]

    def test_register_user_instructor_region_lookup_miss_skips_service_areas(
        self, service, mock_user_repo, mock_instructor_repo, mock_service_area_repo, monkeypatch
    ):
        user, _permission_service = _prepare_registration_user(
            monkeypatch,
            mock_user_repo,
            user_id="user-region-miss",
            first_name="Jordan",
            email="jordan@example.com",
        )

        class GeoProvider:
            async def geocode(self, zip_code):
                return SimpleNamespace(city="Queens", latitude=40.74, longitude=-73.86)

        monkeypatch.setattr(
            "app.services.geocoding.factory.create_geocoding_provider",
            lambda: GeoProvider(),
        )

        class DummyRegionRepo:
            def __init__(self, db):
                self.db = db

            def find_region_by_point(self, lat, lng, region_type):
                return {"region_name": "Queens", "display_key": "nyc-queens"}

            def resolve_display_keys_to_ids(self, display_keys):
                return {"nyc-queens": []}

            def find_region_ids_by_partial_names(self, names):
                return {}

        monkeypatch.setattr(
            "app.repositories.region_boundary_repository.RegionBoundaryRepository",
            DummyRegionRepo,
        )

        result = service.register_user(
            email="jordan@example.com",
            password="pw",
            first_name="Jordan",
            last_name="Test",
            zip_code="11368",
            role=RoleName.INSTRUCTOR,
        )

        assert result is user
        mock_service_area_repo.upsert_area.assert_not_called()

    def test_register_user_instructor_city_missing_keeps_default_bio(
        self, service, mock_user_repo, mock_instructor_repo, mock_service_area_repo, monkeypatch
    ):
        user, _permission_service = _prepare_registration_user(
            monkeypatch,
            mock_user_repo,
            user_id="user-default-city",
            first_name="Taylor",
            email="taylor@example.com",
        )

        class GeoProvider:
            async def geocode(self, zip_code):
                return SimpleNamespace(city=None, latitude=40.7, longitude=-73.9)

        monkeypatch.setattr(
            "app.services.geocoding.factory.create_geocoding_provider",
            lambda: GeoProvider(),
        )

        class DummyRegionRepo:
            def __init__(self, db):
                self.db = db

            def find_region_by_point(self, lat, lng, region_type):
                return None

            def find_region_ids_by_partial_names(self, names):
                return {}

        monkeypatch.setattr(
            "app.repositories.region_boundary_repository.RegionBoundaryRepository",
            DummyRegionRepo,
        )

        result = service.register_user(
            email="taylor@example.com",
            password="pw",
            first_name="Taylor",
            last_name="Test",
            zip_code="10001",
            role=RoleName.INSTRUCTOR,
        )

        assert result is user
        create_kwargs = mock_instructor_repo.create.call_args.kwargs
        assert create_kwargs["bio"] == "Taylor is a New York-based instructor."
        mock_service_area_repo.upsert_area.assert_not_called()

    def test_register_user_instructor_city_fallback_hit_uses_city_region_id(
        self, service, mock_user_repo, mock_instructor_repo, mock_service_area_repo, monkeypatch
    ):
        user, _permission_service = _prepare_registration_user(
            monkeypatch,
            mock_user_repo,
            user_id="user-city-hit",
            first_name="Morgan",
            email="morgan@example.com",
        )

        class GeoProvider:
            async def geocode(self, zip_code):
                return SimpleNamespace(city="Bronx", latitude=40.85, longitude=-73.89)

        monkeypatch.setattr(
            "app.services.geocoding.factory.create_geocoding_provider",
            lambda: GeoProvider(),
        )

        class DummyRegionRepo:
            def __init__(self, db):
                self.db = db

            def find_region_by_point(self, lat, lng, region_type):
                return None

            def find_region_ids_by_partial_names(self, names):
                return {"Bronx": "rb-bronx"}

        monkeypatch.setattr(
            "app.repositories.region_boundary_repository.RegionBoundaryRepository",
            DummyRegionRepo,
        )

        result = service.register_user(
            email="morgan@example.com",
            password="pw",
            first_name="Morgan",
            last_name="Test",
            zip_code="10451",
            role=RoleName.INSTRUCTOR,
        )

        assert result is user
        mock_service_area_repo.upsert_area.assert_called_once_with(
            instructor_id=user.id,
            neighborhood_id="rb-bronx",
            coverage_type="primary",
            is_active=True,
        )

    def test_register_user_with_valid_invite_grants_access_and_founding_status(
        self, service, mock_user_repo, mock_instructor_repo, mock_service_area_repo, monkeypatch
    ):
        user, _permission_service = _prepare_registration_user(
            monkeypatch,
            mock_user_repo,
            user_id="user-invite-success",
            first_name="Avery",
            email="avery@example.com",
        )
        mock_instructor_repo.create.return_value = SimpleNamespace(id="profile-1")

        class DummyRegionRepo:
            def __init__(self, db):
                self.db = db

            def find_region_ids_by_partial_names(self, names):
                return {}

        invite_repo = Mock()
        invite_repo.get_by_code.return_value = SimpleNamespace(
            email="avery@example.com",
            used_at=None,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            grant_founding_status=True,
        )
        invite_repo.mark_used.return_value = True
        access_repo = Mock()
        invalidate_cache = Mock()
        beta_service = Mock()
        beta_service.try_grant_founding_status.return_value = (True, "granted")
        lifecycle_service = Mock()

        monkeypatch.setattr(
            "app.repositories.region_boundary_repository.RegionBoundaryRepository",
            DummyRegionRepo,
        )
        monkeypatch.setattr(auth_module, "BetaInviteRepository", Mock(return_value=invite_repo))
        monkeypatch.setattr(auth_module, "BetaAccessRepository", Mock(return_value=access_repo))
        monkeypatch.setattr(auth_module, "invalidate_cached_user_by_id_sync", invalidate_cache)
        monkeypatch.setattr(
            "app.services.beta_service.BetaService",
            Mock(return_value=beta_service),
        )
        monkeypatch.setattr(
            "app.services.instructor_lifecycle_service.InstructorLifecycleService",
            Mock(return_value=lifecycle_service),
        )

        result = service.register_user(
            email="avery@example.com",
            password="pw",
            first_name="Avery",
            last_name="Invite",
            zip_code="",
            role=RoleName.INSTRUCTOR,
            invite_code="VALID123",
            beta_phase="instructor_only",
        )

        assert result is user
        invite_repo.mark_used.assert_called_once()
        access_repo.grant_access.assert_called_once_with(
            user_id=user.id,
            role="instructor",
            phase="instructor_only",
            invited_by_code="VALID123",
        )
        invalidate_cache.assert_called_once_with(user.id, service.db)
        beta_service.try_grant_founding_status.assert_called_once_with("profile-1")
        lifecycle_service.record_registration.assert_called_once_with(
            user.id,
            is_founding=True,
        )

    def test_register_user_integrity_error_returns_none(self, service, monkeypatch):
        service.user_repository.find_one_by.return_value = None
        monkeypatch.setattr(auth_module, "get_password_hash", lambda pw: "hashed")

        @contextmanager
        def _raise_integrity():
            raise IntegrityError("stmt", "params", Exception("boom"))
            yield

        monkeypatch.setattr(service, "transaction", _raise_integrity)

        result = service.register_user(
            email="conflict@example.com",
            password="pw",
            first_name="A",
            last_name="B",
            zip_code="10001",
        )

        assert result is None

    def test_register_user_unexpected_error_raises_validation(self, service, monkeypatch):
        service.user_repository.find_one_by.return_value = None

        @contextmanager
        def _raise_error():
            raise RuntimeError("unexpected")
            yield

        monkeypatch.setattr(service, "transaction", _raise_error)

        with pytest.raises(ValidationException):
            service.register_user(
                email="bad@example.com",
                password="pw",
                first_name="A",
                last_name="B",
                zip_code="10001",
            )

    def test_fetch_user_for_auth_includes_beta_claims(self, service, monkeypatch):
        user = SimpleNamespace(
            id="user-3",
            email="beta@example.com",
            hashed_password="hash",
            account_status="active",
            totp_enabled=False,
            first_name="Beta",
            last_name="User",
            is_active=True,
        )
        monkeypatch.setattr(service, "get_user_by_email", lambda email: user)

        class DummyBetaRepo:
            def __init__(self, db):
                self.db = db

            def get_latest_for_user(self, user_id):
                return SimpleNamespace(role="student", phase="open", invited_by_code="CODE")

        monkeypatch.setattr(
            "app.repositories.beta_repository.BetaAccessRepository",
            DummyBetaRepo,
        )

        result = service.fetch_user_for_auth("beta@example.com")

        assert result["_beta_claims"] == {
            "beta_access": True,
            "beta_role": "student",
            "beta_phase": "open",
            "beta_invited_by": "CODE",
        }
        assert "_user_obj" not in result

    def test_fetch_user_for_auth_missing_user(self, service, monkeypatch):
        monkeypatch.setattr(service, "get_user_by_email", lambda email: None)

        assert service.fetch_user_for_auth("missing@example.com") is None

    def test_fetch_user_for_auth_no_beta_claims(self, service, monkeypatch):
        user = SimpleNamespace(id="user-10", email="nobeta@example.com", hashed_password="hash")
        monkeypatch.setattr(service, "get_user_by_email", lambda email: user)

        class DummyBetaRepo:
            def __init__(self, db):
                self.db = db

            def get_latest_for_user(self, user_id):
                return None

        monkeypatch.setattr(
            "app.repositories.beta_repository.BetaAccessRepository",
            DummyBetaRepo,
        )

        result = service.fetch_user_for_auth("nobeta@example.com")

        assert "_beta_claims" not in result
        assert "_user_obj" not in result

    def test_fetch_user_for_auth_handles_beta_repo_error(self, service, monkeypatch):
        user = SimpleNamespace(id="user-4", email="beta2@example.com", hashed_password="hash")
        monkeypatch.setattr(service, "get_user_by_email", lambda email: user)

        class DummyBetaRepo:
            def __init__(self, db):
                raise RuntimeError("beta down")

        monkeypatch.setattr(
            "app.repositories.beta_repository.BetaAccessRepository",
            DummyBetaRepo,
        )

        result = service.fetch_user_for_auth("beta2@example.com")

        assert "_beta_claims" not in result

    @pytest.mark.asyncio
    async def test_authenticate_user_async_user_not_found_uses_dummy_hash(self, service, monkeypatch):
        monkeypatch.setattr(service, "get_user_by_email", lambda email: None)

        verify_mock = MagicMock()
        verify_mock.return_value = None

        async def _verify(password, hashed):
            return verify_mock(password, hashed)

        monkeypatch.setattr("app.auth.verify_password_async", _verify)

        result = await service.authenticate_user_async("missing@example.com", "pw")

        assert result is None
        verify_mock.assert_called_once_with("pw", DUMMY_HASH_FOR_TIMING_ATTACK)

    @pytest.mark.asyncio
    async def test_authenticate_user_async_deactivated_user(self, service, monkeypatch):
        user = SimpleNamespace(
            id="user-5",
            email="inactive@example.com",
            hashed_password="hash",
            account_status="deactivated",
        )
        monkeypatch.setattr(service, "get_user_by_email", lambda email: user)

        async def _verify(password, hashed):
            return True

        monkeypatch.setattr("app.auth.verify_password_async", _verify)

        result = await service.authenticate_user_async("inactive@example.com", "pw")

        assert result is None

    def test_authenticate_user_wrong_password(self, service, monkeypatch):
        user = SimpleNamespace(
            id="user-11",
            email="user@example.com",
            hashed_password="hash",
            account_status="active",
        )
        monkeypatch.setattr(service, "get_user_by_email", lambda email: user)
        monkeypatch.setattr(auth_module, "verify_password", lambda pw, hashed: False)

        assert service.authenticate_user("user@example.com", "bad") is None

    def test_authenticate_user_returns_none_when_user_missing(self, service, monkeypatch):
        monkeypatch.setattr(service, "get_user_by_email", lambda email: None)

        assert service.authenticate_user("missing@example.com", "pw") is None

    def test_authenticate_user_success(self, service, monkeypatch):
        user = SimpleNamespace(
            id="user-12",
            email="user@example.com",
            hashed_password="hash",
            account_status="active",
        )
        monkeypatch.setattr(service, "get_user_by_email", lambda email: user)
        monkeypatch.setattr(auth_module, "verify_password", lambda pw, hashed: True)

        assert service.authenticate_user("user@example.com", "pw") is user

    def test_authenticate_user_deactivated(self, service, monkeypatch):
        user = SimpleNamespace(
            id="user-13",
            email="user@example.com",
            hashed_password="hash",
            account_status="deactivated",
        )
        monkeypatch.setattr(service, "get_user_by_email", lambda email: user)
        monkeypatch.setattr(auth_module, "verify_password", lambda pw, hashed: True)

        assert service.authenticate_user("user@example.com", "pw") is None

    @pytest.mark.asyncio
    async def test_authenticate_user_async_wrong_password(self, service, monkeypatch):
        user = SimpleNamespace(
            id="user-14",
            email="user@example.com",
            hashed_password="hash",
            account_status="active",
        )
        monkeypatch.setattr(service, "get_user_by_email", lambda email: user)

        async def _verify(password, hashed):
            return False

        monkeypatch.setattr("app.auth.verify_password_async", _verify)

        assert await service.authenticate_user_async("user@example.com", "pw") is None

    @pytest.mark.asyncio
    async def test_authenticate_user_async_success(self, service, monkeypatch):
        user = SimpleNamespace(
            id="user-15",
            email="user@example.com",
            hashed_password="hash",
            account_status="active",
        )
        monkeypatch.setattr(service, "get_user_by_email", lambda email: user)

        async def _verify(password, hashed):
            return True

        monkeypatch.setattr("app.auth.verify_password_async", _verify)

        assert await service.authenticate_user_async("user@example.com", "pw") is user

    def test_get_user_by_email_handles_exception(self, service, mock_user_repo):
        mock_user_repo.find_one_by.side_effect = Exception("db error")
        assert service.get_user_by_email("user@example.com") is None

    def test_get_user_by_email_blank_identifier_returns_none(self, service, mock_user_repo):
        assert service.get_user_by_email("") is None
        mock_user_repo.find_one_by.assert_not_called()

    def test_get_user_by_email_valid_ulid_falls_back_to_get_by_id(self, service, mock_user_repo, monkeypatch):
        sentinel_user = SimpleNamespace(id="user-ulid", email="ulid@example.com")
        lookup = Mock(return_value=sentinel_user)
        mock_user_repo.find_one_by.return_value = None
        monkeypatch.setattr(service, "get_user_by_id", lookup)

        identifier = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        assert service.get_user_by_email(identifier) is sentinel_user
        lookup.assert_called_once_with(identifier)

    def test_get_user_by_id_handles_exception(self, service, mock_user_repo):
        mock_user_repo.get_by_id.side_effect = Exception("db error")
        assert service.get_user_by_id("user-1") is None

    def test_get_current_user_raises_not_found(self, service, monkeypatch):
        monkeypatch.setattr(service, "get_user_by_email", lambda email: None)

        with pytest.raises(NotFoundException):
            service.get_current_user("missing@example.com")

    def test_get_current_user_success(self, service, monkeypatch):
        user = SimpleNamespace(id="user-16", email="ok@example.com")
        monkeypatch.setattr(service, "get_user_by_email", lambda email: user)

        assert service.get_current_user("ok@example.com") is user

    def test_release_connection_ignores_close_error(self, service, mock_db):
        mock_db.close.side_effect = RuntimeError("close failed")
        service.release_connection()
