from datetime import datetime, timedelta, timezone

import pytest


class FakeInvite:
    def __init__(self, code: str = "ABCDEF12", expires_at: datetime | None = None, used_at: datetime | None = None):
        self.code = code
        self.email = None
        self.role = "instructor_beta"
        self.expires_at = expires_at
        self.used_at = used_at
        self.grant_founding_status = True


class FakeGrant:
    def __init__(self, user_id: str, role: str, phase: str, invited_by_code: str):
        self.id = "GRANT1"
        self.user_id = user_id
        self.role = role
        self.phase = phase
        self.invited_by_code = invited_by_code


class FakeInviteRepo:
    def __init__(self):
        self.created_payload: list[dict] = []
        self._invite: FakeInvite | None = None
        self.mark_used_calls: list[tuple[str, str]] = []

    def set_invite(self, invite: FakeInvite | None):
        self._invite = invite

    def get_by_code(self, code: str):
        return self._invite

    def bulk_create_invites(self, records: list[dict]):
        self.created_payload = records
        # Return simple objects with the same fields we care about
        result = []
        for r in records:
            obj = type("InviteObj", (), {})()
            obj.id = r.get("id") or "INVITE1"
            obj.code = r["code"]
            obj.email = r.get("email")
            obj.role = r["role"]
            obj.expires_at = r["expires_at"]
            result.append(obj)
        return result

    def mark_used(self, code: str, user_id: str, used_at: datetime | None = None) -> bool:
        self.mark_used_calls.append((code, user_id))
        if self._invite is None or self._invite.used_at is not None:
            return False
        self._invite.used_at = used_at or datetime.now(timezone.utc)
        return True


class FakeAccessRepo:
    def __init__(self):
        self.grants: list[tuple[str, str, str, str | None]] = []

    def grant_access(self, user_id: str, role: str, phase: str, invited_by_code: str | None):
        self.grants.append((user_id, role, phase, invited_by_code))
        return FakeGrant(user_id=user_id, role=role, phase=phase, invited_by_code=invited_by_code or "")


@pytest.fixture()
def service(monkeypatch):
    from app.services import beta_service as module

    fake_invites = FakeInviteRepo()
    fake_access = FakeAccessRepo()

    # Patch repositories constructed inside BetaService
    monkeypatch.setattr(module, "BetaInviteRepository", lambda db: fake_invites)
    monkeypatch.setattr(module, "BetaAccessRepository", lambda db: fake_access)

    svc = module.BetaService(db=None)
    # Attach for inspection
    svc._fake_invites = fake_invites
    svc._fake_access = fake_access
    return svc


def test_validate_invite_not_found(service):
    ok, reason, invite = service.validate_invite("MISSING")
    assert ok is False
    assert reason == "not_found"
    assert invite is None


def test_validate_invite_expired(service):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    service._fake_invites.set_invite(FakeInvite(code="EXPIRED01", expires_at=past, used_at=None))
    ok, reason, invite = service.validate_invite("EXPIRED01")
    assert ok is False
    assert reason == "expired"
    assert invite.code == "EXPIRED01"


def test_validate_invite_used(service):
    now = datetime.now(timezone.utc)
    service._fake_invites.set_invite(FakeInvite(code="USED0001", expires_at=now + timedelta(days=2), used_at=now))
    ok, reason, invite = service.validate_invite("USED0001")
    assert ok is False
    assert reason == "used"
    assert invite.code == "USED0001"


def test_bulk_generate_creates_expected_records(service):
    result = service.bulk_generate(
        count=3, role="instructor_beta", expires_in_days=10, source="seed", emails=["a@x.com"]
    )
    # Should return 3 invite-like objects
    assert len(result) == 3
    # Ensure repository received 3 records and codes of length 8
    assert len(service._fake_invites.created_payload) == 3
    for r in service._fake_invites.created_payload:
        assert isinstance(r["code"], str) and len(r["code"]) == 8
        assert r["role"] == "instructor_beta"
        assert r.get("metadata_json") == {"source": "seed"}
    # First email should be applied; others may be None
    emails = [r.get("email") for r in service._fake_invites.created_payload]
    assert emails[0] == "a@x.com"


def test_consume_and_grant_success(service):
    future = datetime.now(timezone.utc) + timedelta(days=2)
    service._fake_invites.set_invite(FakeInvite(code="OKOK0001", expires_at=future, used_at=None))
    grant, reason, invite = service.consume_and_grant(
        code="OKOK0001", user_id="U123", role="instructor_beta", phase="instructor_only"
    )
    assert reason is None
    assert grant is not None
    assert invite is not None
    assert grant.user_id == "U123"
    assert service._fake_invites.mark_used_calls == [("OKOK0001", "U123")]
    assert service._fake_access.grants == [("U123", "instructor_beta", "instructor_only", "OKOK0001")]


def test_consume_and_grant_failure(service):
    # No invite set → validate_invite will fail
    grant, reason, invite = service.consume_and_grant(
        code="BADCODE", user_id="U1", role="instructor_beta", phase="instructor_only"
    )
    assert grant is None
    assert reason in {"not_found", "expired", "used"}
    assert invite is None


def test_build_join_url_local(monkeypatch):
    from app.services import beta_service as module

    monkeypatch.setenv("SITE_MODE", "local")
    url = module.build_join_url("CODE1234", "user@example.com")
    expected_base = module.settings.local_beta_frontend_origin.rstrip("/")
    assert (
        url
        == f"{expected_base}/invite/claim?token=CODE1234&utm_source=email&utm_medium=invite&utm_campaign=founding_instructor"
    )


def test_build_join_url_hosted(monkeypatch):
    from app.services import beta_service as module

    monkeypatch.setenv("SITE_MODE", "preview")
    url = module.build_join_url("CODE1234", None, "https://preview.example.com")
    assert (
        url
        == "https://preview.example.com/invite/claim?token=CODE1234&utm_source=email&utm_medium=invite&utm_campaign=founding_instructor"
    )


def test_resolve_invite_claim_origin_with_explicit_env_var(monkeypatch):
    """Test that INVITE_CLAIM_BASE_URL env var is preferred over frontend_url."""
    from app.services import beta_service as module

    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.setenv("INVITE_CLAIM_BASE_URL", "https://custom.example.com")
    # Also patch settings to reflect the env var (since settings are loaded at import)
    monkeypatch.setattr(module.settings, "invite_claim_base_url", "https://custom.example.com")
    result = module._resolve_invite_claim_origin(None)
    assert result == "https://custom.example.com"


def test_resolve_invite_claim_origin_fallback_to_frontend_url(monkeypatch):
    """Test that frontend_url is used when INVITE_CLAIM_BASE_URL is not set."""
    from app.services import beta_service as module

    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.delenv("INVITE_CLAIM_BASE_URL", raising=False)
    monkeypatch.setattr(module.settings, "frontend_url", "https://beta.example.com")
    # frontend_url should be used as fallback
    result = module._resolve_invite_claim_origin(None)
    assert result == "https://beta.example.com"


def test_resolve_invite_claim_origin_override_takes_precedence(monkeypatch):
    """Test that base_override parameter takes precedence over everything."""
    from app.services import beta_service as module

    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.setenv("INVITE_CLAIM_BASE_URL", "https://should-not-use.com")
    result = module._resolve_invite_claim_origin("https://override.example.com")
    assert result == "https://override.example.com"
