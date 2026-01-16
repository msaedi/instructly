from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.core.exceptions import ServiceException
from app.integrations.checkr_client import CheckrError
from app.routes.v1 import instructor_bgc as bgc_routes


class _CounterStub:
    def labels(self, **_kwargs):
        return self

    def inc(self):
        return None


class _RepoStub:
    def __init__(self, profile, consent=None):
        self._profile = profile
        self._consent = consent
        self.invited_at = None
        self.consent_recorded = None

    def get_by_id(self, instructor_id, load_relationships=False):
        return self._profile if instructor_id == self._profile.id else None

    def latest_consent(self, instructor_id):
        return self._consent

    def set_bgc_invited_at(self, instructor_id, invited_at):
        self.invited_at = invited_at

    def record_bgc_consent(self, instructor_id, consent_version, ip_address=None):
        self.consent_recorded = (instructor_id, consent_version, ip_address)
        return SimpleNamespace(id="consent-1")


class _BGCServiceStub:
    def __init__(self, *, config_error=None, package="pkg", invite_result=None, invite_error=None):
        self.config_error = config_error
        self.package = package
        self._invite_result = invite_result or {"status": "pending", "report_id": "rpt_1"}
        self._invite_error = invite_error

    def invite(self, *args, **kwargs):
        if self._invite_error:
            raise self._invite_error
        return self._invite_result


def _make_profile(bgc_status: str | None = None, bgc_env: str | None = "sandbox"):
    return SimpleNamespace(
        id="profile-1",
        user_id="user-1",
        bgc_status=bgc_status,
        bgc_report_id="rpt_1",
        bgc_invited_at=None,
        bgc_env=bgc_env,
        bgc_completed_at=None,
        bgc_in_dispute=False,
        bgc_dispute_note=None,
        bgc_dispute_opened_at=None,
        bgc_dispute_resolved_at=None,
    )


def _invite_payload():
    return bgc_routes.BackgroundCheckInviteRequest()


def test_helper_problem_builders():
    payload = bgc_routes._bgc_invite_problem("detail", status_code=400, checkr_error={"a": 1})
    assert payload["code"] == "bgc_invite_failed"

    rate_limited = bgc_routes._bgc_invite_rate_limited_problem()
    assert rate_limited["code"] == "bgc_invite_rate_limited"

    assert bgc_routes._checkr_auth_problem()["code"] == "checkr_auth_error"

    invalid = bgc_routes._invalid_work_location_problem(
        zip_code="12345", reason="bad", provider="mapbox", provider_status="500"
    )
    assert invalid["code"] == "invalid_work_location"
    assert invalid["debug"]["zip"] == "12345"
    assert invalid["debug"]["provider"] == "mapbox"
    assert invalid["debug"]["provider_status"] == "500"

    geocode = bgc_routes._geocoding_provider_problem({"provider": "mapbox"})
    assert geocode["code"] == "geocoding_provider_error"

    assert bgc_routes._clean_str("  ok ") == "ok"
    assert bgc_routes._clean_str(123) is None

    assert bgc_routes._checkr_work_location_problem()["code"] == "checkr_work_location_error"
    assert bgc_routes._checkr_package_problem()["code"] == "checkr_package_not_found"


def test_checkr_error_helpers():
    pkg_error = CheckrError(
        "package not found", status_code=404, error_body={"error": "Package not found"}
    )
    assert bgc_routes._is_package_not_found_error(pkg_error) is True

    pkg_error_text = CheckrError("Package not found", status_code=404, error_body="package not found")
    assert bgc_routes._is_package_not_found_error(pkg_error_text) is True

    pkg_error_message = CheckrError("Package not found", status_code=404)
    assert bgc_routes._is_package_not_found_error(pkg_error_message) is True

    wl_error = CheckrError(
        "work_location", status_code=400, error_body={"message": "work_location invalid"}
    )
    assert bgc_routes._is_work_location_error(wl_error) is True

    wl_error_text = CheckrError("work_location invalid", status_code=400, error_body="work_location invalid")
    assert bgc_routes._is_work_location_error(wl_error_text) is True

    wl_error_message = CheckrError("work_locations invalid", status_code=400)
    assert bgc_routes._is_work_location_error(wl_error_message) is True


def test_status_literal_defaults():
    assert bgc_routes._status_literal("pending") == "pending"
    assert bgc_routes._status_literal("unknown") == "failed"


def test_get_profile_and_owner_check():
    profile = _make_profile()
    repo = _RepoStub(profile)
    assert bgc_routes._get_instructor_profile(profile.id, repo) is profile

    with pytest.raises(HTTPException):
        bgc_routes._get_instructor_profile("missing", repo)

    user = SimpleNamespace(id="user-2", is_admin=False)
    with pytest.raises(HTTPException):
        bgc_routes._ensure_owner_or_admin(user, "user-1")


@pytest.mark.asyncio
async def test_invite_config_error(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile)
    service = _BGCServiceStub(config_error="missing-key")

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())
    monkeypatch.setenv("SITE_MODE", "dev")

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_invite(
            payload=_invite_payload(),
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_invite_already_in_progress(monkeypatch):
    profile = _make_profile(bgc_status="pending")
    repo = _RepoStub(profile)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    response = await bgc_routes.trigger_background_check_invite(
        payload=_invite_payload(),
        instructor_id=profile.id,
        current_user=SimpleNamespace(id="user-1", is_admin=False),
        db=None,
        background_check_service=_BGCServiceStub(),
    )
    assert response.already_in_progress is True


@pytest.mark.asyncio
async def test_invite_requires_consent(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=None)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_invite(
            payload=_invite_payload(),
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=_BGCServiceStub(),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_invite_rate_limited(monkeypatch):
    profile = _make_profile()
    profile.bgc_invited_at = datetime.now(timezone.utc)
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_invite(
            payload=_invite_payload(),
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=_BGCServiceStub(),
        )
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_invite_invalid_work_location(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    error = ServiceException(
        "invalid work location",
        code="invalid_work_location",
        details={"zip_code": "11111"},
    )
    service = _BGCServiceStub(invite_error=error)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_invite(
            payload=_invite_payload(),
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_invite_checkr_auth_error(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    root = CheckrError("unauthorized", status_code=401)
    error = ServiceException("checkr", code="checkr_error")
    error.__cause__ = root
    service = _BGCServiceStub(invite_error=error)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_invite(
            payload=_invite_payload(),
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_invite_geocoding_provider_error(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    error = ServiceException(
        "geocode",
        code="geocoding_provider_error",
        details={
            "provider": "mapbox",
            "provider_status": "502",
            "zip_code": "11111",
            "error_message": "bad gateway",
        },
    )
    service = _BGCServiceStub(invite_error=error)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_invite(
            payload=_invite_payload(),
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "geocoding_provider_error"


@pytest.mark.asyncio
async def test_invite_missing_api_key(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    root = CheckrError("api key must be provided", status_code=400)
    error = ServiceException("checkr", code="checkr_error")
    error.__cause__ = root
    service = _BGCServiceStub(invite_error=error)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())
    monkeypatch.setenv("SITE_MODE", "dev")

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_invite(
            payload=_invite_payload(),
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_invite_checkr_package_not_found(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    root = CheckrError(
        "package not found", status_code=404, error_body={"error": "Package not found"}
    )
    error = ServiceException("checkr", code="checkr_error")
    error.__cause__ = root
    service = _BGCServiceStub(invite_error=error)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_invite(
            payload=_invite_payload(),
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "checkr_package_not_found"


@pytest.mark.asyncio
async def test_invite_checkr_work_location_error(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    root = CheckrError(
        "work_location", status_code=400, error_body={"message": "work_location invalid"}
    )
    error = ServiceException("checkr", code="checkr_error")
    error.__cause__ = root
    service = _BGCServiceStub(invite_error=error)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_invite(
            payload=_invite_payload(),
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "checkr_work_location_error"


@pytest.mark.asyncio
async def test_invite_checkr_generic_error(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    root = CheckrError("bad", status_code=422, error_body={"error": "invalid"})
    error = ServiceException("checkr", code="checkr_error")
    error.__cause__ = root
    service = _BGCServiceStub(invite_error=error)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_invite(
            payload=_invite_payload(),
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "bgc_invite_failed"


@pytest.mark.asyncio
async def test_invite_unexpected_error(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))
    service = _BGCServiceStub(invite_error=ServiceException("boom", code="unexpected"))

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_invite(
            payload=_invite_payload(),
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_invite_success(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))
    service = _BGCServiceStub(invite_result={"status": "pending", "report_id": "rpt_1"})

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    response = await bgc_routes.trigger_background_check_invite(
        payload=_invite_payload(),
        instructor_id=profile.id,
        current_user=SimpleNamespace(id="user-1", is_admin=False),
        db=None,
        background_check_service=service,
    )
    assert response.status == "pending"
    assert repo.invited_at is not None


@pytest.mark.asyncio
async def test_recheck_config_error(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))
    service = _BGCServiceStub(config_error="missing-key")

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())
    monkeypatch.setenv("SITE_MODE", "dev")

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_recheck(
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_recheck_requires_consent(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=None)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_recheck(
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=_BGCServiceStub(),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_recheck_rate_limited(monkeypatch):
    profile = _make_profile()
    profile.bgc_invited_at = datetime.now(timezone.utc)
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_recheck(
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=_BGCServiceStub(),
        )
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_recheck_already_in_progress(monkeypatch):
    profile = _make_profile(bgc_status="pending")
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    response = await bgc_routes.trigger_background_check_recheck(
        instructor_id=profile.id,
        current_user=SimpleNamespace(id="user-1", is_admin=False),
        db=None,
        background_check_service=_BGCServiceStub(),
    )
    assert response.already_in_progress is True


@pytest.mark.asyncio
async def test_recheck_invalid_work_location(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    error = ServiceException(
        "invalid work location",
        code="invalid_work_location",
        details={"zip_code": "11111"},
    )
    service = _BGCServiceStub(invite_error=error)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_recheck(
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_recheck_missing_api_key(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    root = CheckrError("api key must be provided", status_code=400)
    error = ServiceException("checkr", code="checkr_error")
    error.__cause__ = root
    service = _BGCServiceStub(invite_error=error)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())
    monkeypatch.setenv("SITE_MODE", "dev")

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_recheck(
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_recheck_checkr_auth_error(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    root = CheckrError("unauthorized", status_code=401)
    error = ServiceException("checkr", code="checkr_error")
    error.__cause__ = root
    service = _BGCServiceStub(invite_error=error)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_recheck(
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "checkr_auth_error"


@pytest.mark.asyncio
async def test_recheck_checkr_package_not_found(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    root = CheckrError(
        "package not found", status_code=404, error_body={"error": "Package not found"}
    )
    error = ServiceException("checkr", code="checkr_error")
    error.__cause__ = root
    service = _BGCServiceStub(invite_error=error)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_recheck(
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "checkr_package_not_found"


@pytest.mark.asyncio
async def test_recheck_checkr_work_location_error(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    root = CheckrError(
        "work_location", status_code=400, error_body={"message": "work_location invalid"}
    )
    error = ServiceException("checkr", code="checkr_error")
    error.__cause__ = root
    service = _BGCServiceStub(invite_error=error)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_recheck(
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "checkr_work_location_error"


@pytest.mark.asyncio
async def test_recheck_checkr_generic_error(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    root = CheckrError("bad", status_code=422, error_body={"error": "invalid"})
    error = ServiceException("checkr", code="checkr_error")
    error.__cause__ = root
    service = _BGCServiceStub(invite_error=error)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_recheck(
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "bgc_invite_failed"


@pytest.mark.asyncio
async def test_recheck_geocoding_provider_error(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    error = ServiceException(
        "geocode",
        code="geocoding_provider_error",
        details={
            "provider": "mapbox",
            "provider_status": "502",
            "zip_code": "11111",
            "error_message": "bad gateway",
        },
    )
    service = _BGCServiceStub(invite_error=error)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(HTTPException) as exc:
        await bgc_routes.trigger_background_check_recheck(
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "geocoding_provider_error"


@pytest.mark.asyncio
async def test_recheck_generic_service_exception(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    error = ServiceException("boom", code="other_error")
    service = _BGCServiceStub(invite_error=error)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    with pytest.raises(ServiceException):
        await bgc_routes.trigger_background_check_recheck(
            instructor_id=profile.id,
            current_user=SimpleNamespace(id="user-1", is_admin=False),
            db=None,
            background_check_service=service,
        )


@pytest.mark.asyncio
async def test_recheck_success(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setattr(bgc_routes, "BGC_INVITES_TOTAL", _CounterStub())

    response = await bgc_routes.trigger_background_check_recheck(
        instructor_id=profile.id,
        current_user=SimpleNamespace(id="user-1", is_admin=False),
        db=None,
        background_check_service=_BGCServiceStub(),
    )
    assert response.status == "pending"

@pytest.mark.asyncio
async def test_get_status_and_consent(monkeypatch):
    profile = _make_profile(bgc_status="passed")
    repo = _RepoStub(profile, consent=SimpleNamespace(consented_at=datetime.now(timezone.utc)))

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)

    response = await bgc_routes.get_background_check_status(
        instructor_id=profile.id,
        current_user=SimpleNamespace(id="user-1", is_admin=False),
        db=None,
    )
    assert response.status == "passed"
    assert response.consent_recent is True


@pytest.mark.asyncio
async def test_record_consent(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"user-agent": "ua"},
    )

    response = await bgc_routes.record_background_check_consent(
        instructor_id=profile.id,
        payload=bgc_routes.ConsentPayload(consent_version="v1", disclosure_version="v1"),
        request=request,
        current_user=SimpleNamespace(id="user-1", is_admin=False),
        db=None,
    )
    assert response.ok is True


def test_ensure_non_production(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "prod")
    with pytest.raises(HTTPException):
        bgc_routes._ensure_non_production()


@pytest.mark.asyncio
async def test_mock_background_check_pass(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setenv("SITE_MODE", "dev")

    response = await bgc_routes.mock_background_check_pass(
        instructor_id=profile.id,
        current_user=SimpleNamespace(id="user-1", is_admin=False),
        db=None,
    )
    assert response.status == "passed"
    assert profile.bgc_status == "passed"


@pytest.mark.asyncio
async def test_mock_background_check_review(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setenv("SITE_MODE", "dev")

    response = await bgc_routes.mock_background_check_review(
        instructor_id=profile.id,
        current_user=SimpleNamespace(id="user-1", is_admin=False),
        db=None,
    )
    assert response.status == "review"
    assert profile.bgc_status == "review"


@pytest.mark.asyncio
async def test_mock_background_check_reset(monkeypatch):
    profile = _make_profile()
    repo = _RepoStub(profile)

    monkeypatch.setattr(bgc_routes, "InstructorProfileRepository", lambda _db: repo)
    monkeypatch.setenv("SITE_MODE", "dev")

    response = await bgc_routes.mock_background_check_reset(
        instructor_id=profile.id,
        current_user=SimpleNamespace(id="user-1", is_admin=False),
        db=None,
    )
    assert response.status == "failed"
    assert profile.bgc_status == "failed"
