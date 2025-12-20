"""Verify login_slot is only held during Argon2id verification in auth routes."""

from __future__ import annotations

import sys
import types
from typing import Any, Optional

import pytest
from starlette.requests import Request
from starlette.responses import Response

# --------------------------------------------------------------------------- #
# Optional argon2 stub for environments without the dependency.
# The auth routes import app.auth, which requires argon2 at import time.
# --------------------------------------------------------------------------- #

try:  # pragma: no cover - only for missing optional dep
    import argon2  # noqa: F401
except Exception:  # pragma: no cover
    argon2_stub = types.ModuleType("argon2")

    class PasswordHasher:  # minimal stub
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def verify(self, hashed: str, plain: str) -> bool:
            return True

        def hash(self, password: str) -> str:
            return "stubbed-hash"

    argon2_stub.PasswordHasher = PasswordHasher

    exc_stub = types.ModuleType("argon2.exceptions")

    class InvalidHashError(Exception):
        pass

    class VerifyMismatchError(Exception):
        pass

    exc_stub.InvalidHashError = InvalidHashError
    exc_stub.VerifyMismatchError = VerifyMismatchError

    sys.modules.setdefault("argon2", argon2_stub)
    sys.modules.setdefault("argon2.exceptions", exc_stub)


# The app.routes package imports optional SSE broadcaster dependency.
try:  # pragma: no cover
    import broadcaster  # noqa: F401
except Exception:  # pragma: no cover
    broadcaster_stub = types.ModuleType("broadcaster")

    class Broadcast:  # minimal stub matching expected API
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def connect(self) -> None:
            return None

        async def disconnect(self) -> None:
            return None

    broadcaster_stub.Broadcast = Broadcast
    sys.modules.setdefault("broadcaster", broadcaster_stub)


async def _empty_receive() -> dict[str, object]:
    return {"type": "http.request", "body": b"", "more_body": False}


def _build_request(path: str = "/login") -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "headers": [],
        "query_string": b"",
        "client": ("testclient", 1234),
        "server": ("testserver", 80),
    }
    return Request(scope, _empty_receive)


class _FakeForm:
    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password


class _FakeAuthService:
    def __init__(self, events: list[str], slot_active: dict[str, bool]) -> None:
        self._events = events
        self._slot_active = slot_active

    def fetch_user_for_auth(self, email: str) -> dict[str, Any]:
        assert self._slot_active["active"] is False
        self._events.append("fetch_user")
        return {
            "id": "user-1",
            "email": email,
            "hashed_password": "hash",
            "account_status": None,
            "totp_enabled": False,
            "_user_obj": None,
            "_beta_claims": None,
        }

    def release_connection(self) -> None:
        self._events.append("release_conn")


@pytest.mark.asyncio
async def test_login_slot_wraps_only_password_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routes.v1 import auth as auth_routes

    events: list[str] = []
    slot_active = {"active": False}

    class _FakeSlot:
        async def __aenter__(self) -> "_FakeSlot":
            slot_active["active"] = True
            events.append("slot_enter")
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            events.append("slot_exit")
            slot_active["active"] = False

    def fake_login_slot(*args: Any, **kwargs: Any) -> _FakeSlot:
        return _FakeSlot()

    async def fake_verify_password_async(plain: str, hashed: str) -> bool:
        assert slot_active["active"] is True
        events.append("verify")
        return True

    class _FakeLockout:
        async def check_lockout(self, email: str):
            events.append("check_lockout")
            return False, {"locked": False}

        async def record_failure(self, email: str):
            events.append("record_failure")
            return {}

        async def reset(self, email: str):
            events.append("lockout_reset")

    class _FakeLimiter:
        async def check(self, email: str):
            events.append("check_rate")
            return True, {}

        async def check_and_increment(self, email: str):
            events.append("check_rate")
            return True, {}

        async def record_attempt(self, email: str):
            events.append("rate_record_attempt")

        async def reset(self, email: str):
            events.append("rate_reset")

    class _FakeCaptcha:
        async def is_captcha_required(self, email: str) -> bool:
            events.append("check_captcha")
            return False

        async def verify(self, token: Optional[str], remote_ip: Optional[str] = None) -> bool:
            events.append("captcha_verify")
            return True

    monkeypatch.setattr(auth_routes, "login_slot", fake_login_slot)
    monkeypatch.setattr(auth_routes, "verify_password_async", fake_verify_password_async)
    monkeypatch.setattr(auth_routes, "account_lockout", _FakeLockout())
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _FakeLimiter())
    monkeypatch.setattr(auth_routes, "captcha_verifier", _FakeCaptcha())
    monkeypatch.setattr(auth_routes, "record_login_result", lambda res: events.append(f"record_{res}"))
    monkeypatch.setattr(auth_routes, "record_captcha_event", lambda res: events.append(f"captcha_{res}"))
    monkeypatch.setattr(auth_routes, "create_access_token", lambda *a, **k: "token")
    monkeypatch.setattr(auth_routes, "set_session_cookie", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "expire_parent_domain_cookie", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "session_cookie_base_name", lambda *a, **k: "sid")
    monkeypatch.setattr(
        auth_routes,
        "settings",
        types.SimpleNamespace(
            site_mode="local",
            access_token_expire_minutes=30,
            session_cookie_domain=None,
            preview_api_domain="preview.example.com",
            prod_api_domain="prod.example.com",
            environment="test",
        ),
    )

    request = _build_request("/login")
    response = Response()
    form = _FakeForm("user@example.com", "pw")
    auth_service = _FakeAuthService(events, slot_active)

    await auth_routes.login.__wrapped__(  # bypass rate_limit decorator
        request=request,
        response=response,
        form_data=form,  # type: ignore[arg-type]
        auth_service=auth_service,  # type: ignore[arg-type]
    )

    assert events.index("fetch_user") < events.index("slot_enter")
    assert "verify" in events


@pytest.mark.asyncio
async def test_login_with_session_slot_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routes.v1 import auth as auth_routes

    events: list[str] = []
    slot_active = {"active": False}

    class _FakeSlot:
        async def __aenter__(self) -> "_FakeSlot":
            slot_active["active"] = True
            events.append("slot_enter")
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            events.append("slot_exit")
            slot_active["active"] = False

    def fake_login_slot(*args: Any, **kwargs: Any) -> _FakeSlot:
        return _FakeSlot()

    async def fake_verify_password_async(plain: str, hashed: str) -> bool:
        assert slot_active["active"] is True
        events.append("verify")
        return True

    class _FakeLockout:
        async def check_lockout(self, email: str):
            events.append("check_lockout")
            return False, {"locked": False}

        async def record_failure(self, email: str):
            events.append("record_failure")
            return {}

        async def reset(self, email: str):
            events.append("lockout_reset")

    class _FakeLimiter:
        async def check(self, email: str):
            events.append("check_rate")
            return True, {}

        async def check_and_increment(self, email: str):
            events.append("check_rate")
            return True, {}

        async def record_attempt(self, email: str):
            events.append("rate_record_attempt")

        async def reset(self, email: str):
            events.append("rate_reset")

    class _FakeCaptcha:
        async def is_captcha_required(self, email: str) -> bool:
            events.append("check_captcha")
            return False

        async def verify(self, token: Optional[str], remote_ip: Optional[str] = None) -> bool:
            events.append("captcha_verify")
            return True

    monkeypatch.setattr(auth_routes, "login_slot", fake_login_slot)
    monkeypatch.setattr(auth_routes, "verify_password_async", fake_verify_password_async)
    monkeypatch.setattr(auth_routes, "account_lockout", _FakeLockout())
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _FakeLimiter())
    monkeypatch.setattr(auth_routes, "captcha_verifier", _FakeCaptcha())
    monkeypatch.setattr(auth_routes, "record_login_result", lambda res: events.append(f"record_{res}"))
    monkeypatch.setattr(auth_routes, "record_captcha_event", lambda res: events.append(f"captcha_{res}"))
    monkeypatch.setattr(auth_routes, "create_access_token", lambda *a, **k: "token")
    monkeypatch.setattr(auth_routes, "set_session_cookie", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "expire_parent_domain_cookie", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "session_cookie_base_name", lambda *a, **k: "sid")
    monkeypatch.setattr(
        auth_routes,
        "settings",
        types.SimpleNamespace(
            site_mode="local",
            access_token_expire_minutes=30,
            session_cookie_domain=None,
            preview_api_domain="preview.example.com",
            prod_api_domain="prod.example.com",
            environment="test",
        ),
    )

    request = _build_request("/login-with-session")
    response = Response()

    class _FakeLoginData:
        def __init__(self) -> None:
            self.email = "user@example.com"
            self.password = "pw"
            self.guest_session_id = None
            self.captcha_token = None

    login_data = _FakeLoginData()
    auth_service = _FakeAuthService(events, slot_active)

    await auth_routes.login_with_session.__wrapped__(  # bypass rate_limit decorator
        request=request,
        response=response,
        login_data=login_data,  # type: ignore[arg-type]
        auth_service=auth_service,  # type: ignore[arg-type]
        db=None,  # type: ignore[arg-type]
    )

    assert events.index("fetch_user") < events.index("slot_enter")
    assert "verify" in events
