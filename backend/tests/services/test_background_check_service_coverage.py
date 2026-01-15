
import pytest

from app.core.exceptions import NotFoundException, ServiceException
from app.integrations.checkr_client import CheckrError
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.services.background_check_service import BackgroundCheckService


class _StubCheckrClient:
    def __init__(self, *, candidate_id="cand_123", report_id="rep_123", invitation_id="inv_123"):
        self._candidate_id = candidate_id
        self._report_id = report_id
        self._invitation_id = invitation_id

    def create_candidate(self, **_kwargs):
        return {"id": self._candidate_id}

    def create_invitation(self, **_kwargs):
        return {"id": self._invitation_id, "report_id": self._report_id}


class _FailingCheckrClient(_StubCheckrClient):
    def create_invitation(self, **_kwargs):
        raise CheckrError("boom", status_code=500)


class _StubResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("bad response")

    def json(self):
        return self._json_data


@pytest.fixture
def bgc_service(db):
    repo = InstructorProfileRepository(db)
    return BackgroundCheckService(
        db,
        client=_StubCheckrClient(),
        repository=repo,
        package="pkg_basic",
        env="sandbox",
    )


def test_invite_success_updates_profile(db, bgc_service, test_instructor, monkeypatch):
    test_instructor.instructor_profile.is_live = False
    db.commit()

    monkeypatch.setattr(
        bgc_service,
        "_resolve_work_location",
        lambda _zip: {"country": "US", "state": "NY", "city": "New York"},
    )

    result = bgc_service.invite(test_instructor.instructor_profile.id)
    assert result["status"] == "pending"

    profile = bgc_service.repository.get_by_id(test_instructor.instructor_profile.id)
    assert profile.bgc_status == "pending"
    assert profile.bgc_env == "sandbox"


def test_invite_missing_profile_raises(db, bgc_service):
    with pytest.raises(NotFoundException):
        bgc_service.invite("missing_profile")


def test_invite_missing_user_raises(monkeypatch, db):
    repo = InstructorProfileRepository(db)
    service = BackgroundCheckService(
        db,
        client=_StubCheckrClient(),
        repository=repo,
        package="pkg_basic",
        env="sandbox",
    )

    monkeypatch.setattr(
        service.repository,
        "get_by_id",
        lambda *_args, **_kwargs: type("Profile", (), {"user": None, "id": "profile"})(),
    )

    with pytest.raises(ServiceException):
        service.invite("profile")


def test_invite_missing_zip_raises(db, bgc_service, test_instructor):
    test_instructor.zip_code = ""
    db.commit()

    with pytest.raises(ServiceException):
        bgc_service.invite(test_instructor.instructor_profile.id)


def test_invite_missing_package_raises(db, test_instructor):
    repo = InstructorProfileRepository(db)
    service = BackgroundCheckService(
        db,
        client=_StubCheckrClient(),
        repository=repo,
        package="",
        env="sandbox",
    )
    with pytest.raises(ServiceException):
        service.invite(test_instructor.instructor_profile.id)


def test_invite_checkr_error(db, test_instructor, monkeypatch):
    repo = InstructorProfileRepository(db)
    service = BackgroundCheckService(
        db,
        client=_FailingCheckrClient(),
        repository=repo,
        package="pkg_basic",
        env="sandbox",
    )
    monkeypatch.setattr(
        service,
        "_resolve_work_location",
        lambda _zip: {"country": "US", "state": "NY", "city": "New York"},
    )

    with pytest.raises(ServiceException):
        service.invite(test_instructor.instructor_profile.id)


def test_invite_missing_candidate_id(db, test_instructor, monkeypatch):
    repo = InstructorProfileRepository(db)

    class _NoCandidateClient(_StubCheckrClient):
        def create_candidate(self, **_kwargs):
            return {}

    service = BackgroundCheckService(
        db,
        client=_NoCandidateClient(),
        repository=repo,
        package="pkg_basic",
        env="sandbox",
    )
    monkeypatch.setattr(
        service,
        "_resolve_work_location",
        lambda _zip: {"country": "US", "state": "NY", "city": "New York"},
    )

    with pytest.raises(ServiceException):
        service.invite(test_instructor.instructor_profile.id)


def test_update_status_from_report(db, bgc_service, test_instructor):
    profile = bgc_service.repository.get_by_id(test_instructor.instructor_profile.id)
    profile.bgc_report_id = "rep_123"
    db.commit()

    updated = bgc_service.update_status_from_report(
        "rep_123", status="passed", completed=True, result="clear"
    )
    assert updated is True

    missing = bgc_service.update_status_from_report(
        "missing", status="passed", completed=True, result="clear"
    )
    assert missing is False


def test_normalize_zip_and_state():
    assert BackgroundCheckService._normalize_zip("12345-6789") == "12345"
    with pytest.raises(ServiceException):
        BackgroundCheckService._normalize_zip("bad")

    assert BackgroundCheckService._normalize_state("ny") == "NY"
    assert BackgroundCheckService._normalize_state("New York") == "NY"
    assert BackgroundCheckService._normalize_state("") == ""


def test_resolve_work_location_missing_token(db, bgc_service, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "mapbox_access_token", None, raising=False)
    with pytest.raises(ServiceException):
        bgc_service._resolve_work_location("10001")


def test_resolve_work_location_provider_error(db, bgc_service, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "mapbox_access_token", "token", raising=False)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("app.services.background_check_service.httpx.get", _boom)

    with pytest.raises(ServiceException):
        bgc_service._resolve_work_location("10001")


def test_resolve_work_location_zero_results(db, bgc_service, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "mapbox_access_token", "token", raising=False)

    monkeypatch.setattr(
        "app.services.background_check_service.httpx.get",
        lambda *_args, **_kwargs: _StubResponse({"features": []}),
    )

    with pytest.raises(ServiceException):
        bgc_service._resolve_work_location("10001")


def test_resolve_work_location_missing_components(db, bgc_service, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "mapbox_access_token", "token", raising=False)

    data = {"features": [{"text": "", "context": []}]}
    monkeypatch.setattr(
        "app.services.background_check_service.httpx.get",
        lambda *_args, **_kwargs: _StubResponse(data),
    )

    with pytest.raises(ServiceException):
        bgc_service._resolve_work_location("10001")


def test_resolve_work_location_success(db, bgc_service, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "mapbox_access_token", "token", raising=False)

    data = {
        "features": [
            {
                "text": "New York",
                "context": [
                    {"id": "place.1", "text": "New York"},
                    {"id": "region.1", "text": "New York"},
                    {"id": "country.1", "short_code": "us"},
                ],
            }
        ]
    }

    monkeypatch.setattr(
        "app.services.background_check_service.httpx.get",
        lambda *_args, **_kwargs: _StubResponse(data),
    )

    result = bgc_service._resolve_work_location("10001")
    assert result == {"country": "US", "state": "NY", "city": "New York"}
