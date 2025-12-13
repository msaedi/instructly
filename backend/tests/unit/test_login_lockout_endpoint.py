"""Endpoint-level lockout behavior.

Ensures that after 5 invalid credential attempts, the next login attempt is
blocked by AccountLockout with a 429 response.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
import pytest
from starlette.requests import Request
from starlette.responses import Response

# --------------------------------------------------------------------------- #
# Optional argon2 stub for environments without the dependency.
# The auth routes import app.auth, which requires argon2 at import time.
# --------------------------------------------------------------------------- #

try:  # pragma: no cover
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


def _build_request(path: str) -> Request:
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


class FakePipeline:
    def __init__(self, backend: "FakeRedis") -> None:
        self.backend = backend
        self.ops: List[Any] = []

    def get(self, key: str) -> "FakePipeline":
        self.ops.append(lambda: self.backend.store.get(key))
        return self

    def incr(self, key: str) -> "FakePipeline":
        self.ops.append(lambda: self.backend._incr_sync(key))
        return self

    def expire(self, key: str, seconds: int) -> "FakePipeline":
        self.ops.append(lambda: self.backend._expire(key, seconds))
        return self

    def setex(self, key: str, seconds: int, value: Any) -> "FakePipeline":
        self.ops.append(lambda: self.backend._setex(key, seconds, value))
        return self

    async def execute(self) -> List[Any]:
        results: List[Any] = []
        for op in self.ops:
            results.append(op())
        self.ops = []
        return results


class FakeRedis:
    def __init__(self) -> None:
        self.store: Dict[str, Any] = {}
        self.expire_times: Dict[str, int] = {}

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)

    async def get(self, key: str) -> Any:
        return self.store.get(key)

    async def ttl(self, key: str) -> int:
        return int(self.expire_times.get(key, -1))

    def _incr_sync(self, key: str) -> int:
        current = int(self.store.get(key, 0) or 0)
        new_val = current + 1
        self.store[key] = new_val
        return new_val

    async def incr(self, key: str) -> int:
        return self._incr_sync(key)

    def _expire(self, key: str, seconds: int) -> None:
        self.expire_times[key] = seconds

    async def expire(self, key: str, seconds: int) -> None:
        self._expire(key, seconds)

    def _setex(self, key: str, seconds: int, value: Any) -> None:
        self.store[key] = value
        self.expire_times[key] = seconds

    async def setex(self, key: str, seconds: int, value: Any) -> None:
        self._setex(key, seconds, value)

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.store.pop(key, None)
            self.expire_times.pop(key, None)


class _FakeAuthService:
    def fetch_user_for_auth(self, email: str) -> Dict[str, Any]:
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
        return None


@pytest.mark.asyncio
async def test_login_with_session_lockout_after_five_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """5 invalid attempts return 401; 6th returns 429 locked out."""

    from app.core import login_protection as lp
    from app.routes.v1 import auth as auth_routes

    fake_redis = FakeRedis()
    lockout = lp.AccountLockout(redis=fake_redis)  # type: ignore[arg-type]

    class _AllowAllLimiter:
        async def check(self, email: str):
            return True, {}

        async def check_and_increment(self, email: str):
            return True, {}

        async def record_attempt(self, email: str):
            pass

        async def reset(self, email: str):
            return None

    class _NoCaptcha:
        async def is_captcha_required(self, email: str) -> bool:
            return False

        async def verify(self, token: Optional[str], remote_ip: Optional[str] = None) -> bool:
            return True

    class _DummySlot:
        async def __aenter__(self) -> "_DummySlot":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

    async def fake_verify_password_async(*args: Any, **kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(auth_routes, "account_lockout", lockout)
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _AllowAllLimiter())
    monkeypatch.setattr(auth_routes, "captcha_verifier", _NoCaptcha())
    monkeypatch.setattr(auth_routes, "login_slot", lambda *a, **k: _DummySlot())
    monkeypatch.setattr(auth_routes, "verify_password_async", fake_verify_password_async)

    request = _build_request("/login-with-session")
    response = Response()
    login_data = SimpleNamespace(
        email="lockout@example.com",
        password="wrong",
        guest_session_id=None,
        captcha_token=None,
    )
    auth_service = _FakeAuthService()

    # First 5 attempts: 401
    for _ in range(5):
        with pytest.raises(HTTPException) as exc:
            await auth_routes.login_with_session.__wrapped__(  # bypass IP rate-limit decorator
                request=request,
                response=response,
                login_data=login_data,  # type: ignore[arg-type]
                auth_service=auth_service,  # type: ignore[arg-type]
                db=None,  # type: ignore[arg-type]
            )
        assert exc.value.status_code == 401

    # 6th attempt: locked out 429
    with pytest.raises(HTTPException) as exc:
        await auth_routes.login_with_session.__wrapped__(
            request=request,
            response=response,
            login_data=login_data,  # type: ignore[arg-type]
            auth_service=auth_service,  # type: ignore[arg-type]
            db=None,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 429
    assert exc.value.headers and int(exc.value.headers.get("Retry-After", "0")) >= 1
