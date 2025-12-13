import json

from httpx import MockTransport, Response
from pydantic import SecretStr
import pytest

from app.auth import get_password_hash
from app.core.config import settings
from app.core.exceptions import ServiceException
from app.integrations.checkr_client import CheckrClient
from app.models.instructor import InstructorProfile
from app.models.user import User
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.services.background_check_service import BackgroundCheckService


@pytest.fixture(autouse=True)
def configure_checkr_settings():
    original_key = settings.checkr_api_key
    original_package = settings.checkr_package
    original_base = settings.checkr_api_base
    original_env = settings.checkr_env
    original_workflow = settings.checkr_hosted_workflow

    settings.checkr_api_key = SecretStr("sk_test_key")
    settings.checkr_package = "essential"
    settings.checkr_api_base = "https://api.checkr.com/v1"
    settings.checkr_env = "sandbox"
    settings.checkr_hosted_workflow = "checkr_hosted"

    try:
        yield
    finally:
        settings.checkr_api_key = original_key
        settings.checkr_package = original_package
        settings.checkr_api_base = original_base
        settings.checkr_env = original_env
        settings.checkr_hosted_workflow = original_workflow


def _create_instructor(db, *, status: str = "pending") -> InstructorProfile:
    user = User(
        email="instructor@example.com",
        hashed_password=get_password_hash("StrongP@ssw0rd"),
        first_name="Ada",
        last_name="Lovelace",
        zip_code="10001",
        phone="5551234567",
    )
    db.add(user)
    db.flush()

    profile = InstructorProfile(user_id=user.id)
    profile.bgc_status = status
    db.add(profile)
    db.flush()
    db.refresh(profile)
    return profile


def _service_factory(db, transport: MockTransport) -> BackgroundCheckService:
    client = CheckrClient(
        api_key=settings.checkr_api_key,
        base_url=settings.checkr_api_base,
        transport=transport,
    )
    repository = InstructorProfileRepository(db)
    service = BackgroundCheckService(
        db,
        client=client,
        repository=repository,
        package=settings.checkr_package,
        env=settings.checkr_env,
    )
    service._resolve_work_location = lambda _zip: {  # type: ignore[attr-defined]
        "country": "US",
        "state": "NY",
        "city": "New York",
    }
    return service


def test_invite_returns_candidate_and_invitation_ids(db):
    captured_requests: dict[str, dict] = {}

    def handler(request):
        body = json.loads(request.content.decode())
        if request.url.path.endswith("/candidates"):
            captured_requests["candidate"] = body
            return Response(201, json={"id": "cand_123"})
        if request.url.path.endswith("/invitations"):
            captured_requests["invitation"] = body
            return Response(201, json={"id": "inv_123", "report_id": "rpt_123"})
        raise AssertionError(f"Unexpected path {request.url.path}")

    service = _service_factory(db, MockTransport(handler))
    profile = _create_instructor(db)

    result = service.invite(profile.id)

    assert result["report_id"] == "rpt_123"
    assert result["status"] == "pending"
    assert result["candidate_id"] == "cand_123"
    assert result["invitation_id"] == "inv_123"
    assert captured_requests["candidate"]["email"] == "instructor@example.com"
    assert "ssn" not in captured_requests["candidate"]
    invitation_payload = captured_requests["invitation"]
    assert invitation_payload["candidate_id"] == "cand_123"
    assert invitation_payload["package"] == settings.checkr_package
    assert invitation_payload["workflow"] == "checkr_hosted"
    assert invitation_payload["candidate"]["email"] == "instructor@example.com"
    assert invitation_payload["redirect_url"].endswith("/instructor/onboarding/status")

    db.refresh(profile)
    assert profile.bgc_status == "pending"
    assert profile.bgc_report_id == "rpt_123"
    assert profile.bgc_env == settings.checkr_env
    assert profile.checkr_candidate_id == "cand_123"
    assert profile.checkr_invitation_id == "inv_123"


def test_invite_propagates_checkr_errors_without_updates(db):
    def handler(request):
        if request.url.path.endswith("/candidates"):
            return Response(422, json={"error": "invalid"})
        raise AssertionError("Invitation endpoint should not be called on failure")

    service = _service_factory(db, MockTransport(handler))
    profile = _create_instructor(db, status="review")
    profile.bgc_report_id = None
    db.flush()

    with pytest.raises(ServiceException):
        service.invite(profile.id)

    db.refresh(profile)
    assert profile.bgc_status == "review"
    assert profile.bgc_report_id is None
    assert profile.bgc_env == "sandbox"


def test_invite_uses_service_package_from_settings(db):
    """Verify that the service uses the package configured in settings.checkr_package."""
    captured_requests: dict[str, dict] = {}

    def handler(request):
        body = json.loads(request.content.decode())
        if request.url.path.endswith("/candidates"):
            captured_requests["candidate"] = body
            return Response(201, json={"id": "cand_456"})
        if request.url.path.endswith("/invitations"):
            captured_requests["invitation"] = body
            return Response(201, json={"id": "inv_456", "report_id": "rpt_456"})
        raise AssertionError(f"Unexpected path {request.url.path}")

    # The fixture sets settings.checkr_package = "essential"
    service = _service_factory(db, MockTransport(handler))
    profile = _create_instructor(db)

    service.invite(profile.id)

    # Verify the package from settings was used
    invitation_payload = captured_requests["invitation"]
    assert invitation_payload["package"] == "essential"
    assert invitation_payload["package"] == settings.checkr_package


def test_invite_package_override_takes_precedence(db):
    """Verify that package_override parameter takes precedence over settings."""
    captured_requests: dict[str, dict] = {}

    def handler(request):
        body = json.loads(request.content.decode())
        if request.url.path.endswith("/candidates"):
            return Response(201, json={"id": "cand_789"})
        if request.url.path.endswith("/invitations"):
            captured_requests["invitation"] = body
            return Response(201, json={"id": "inv_789", "report_id": "rpt_789"})
        raise AssertionError(f"Unexpected path {request.url.path}")

    # The fixture sets settings.checkr_package = "essential"
    service = _service_factory(db, MockTransport(handler))
    profile = _create_instructor(db)

    # Override with a different package
    service.invite(profile.id, package_override="complete_criminal")

    # Verify the override was used instead of settings
    invitation_payload = captured_requests["invitation"]
    assert invitation_payload["package"] == "complete_criminal"
    assert invitation_payload["package"] != settings.checkr_package
