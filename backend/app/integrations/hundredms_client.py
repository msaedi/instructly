"""100ms Video Platform Integration Client.

Handles room creation, management token generation for server-to-server
communication with the 100ms REST API, and per-participant auth token
generation for joining rooms.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, cast
import uuid

import httpx
import jwt
from pydantic import SecretStr

logger = logging.getLogger(__name__)


class HundredMsError(RuntimeError):
    """Raised when the 100ms API responds with an error."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        *,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


class HundredMsClient:
    """HTTP client for 100ms REST API."""

    def __init__(
        self,
        *,
        access_key: str,
        app_secret: str | SecretStr,
        base_url: str = "https://api.100ms.live/v2",
        template_id: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._access_key = access_key
        self._app_secret = (
            app_secret.get_secret_value() if isinstance(app_secret, SecretStr) else app_secret
        )
        self._base_url = base_url.rstrip("/")
        self._template_id = template_id
        self._timeout = timeout
        self._mgmt_token: str | None = None
        self._mgmt_token_refresh_at: float = 0.0

    def _generate_management_token(self) -> str:
        """Generate a management token for server-to-server API calls.

        This is a JWT signed with HS256 using our app_secret.
        Used in Authorization header for 100ms REST API requests.
        """
        now = int(time.time())
        payload = {
            "access_key": self._access_key,
            "type": "management",
            "version": 2,
            "jti": str(uuid.uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + 3600,
        }
        token: str = jwt.encode(
            payload,
            self._app_secret,
            algorithm="HS256",
            headers={"alg": "HS256", "typ": "JWT"},
        )
        return token

    def _get_management_token(self) -> str:
        """Return a cached management token, refreshing before expiry."""
        now = time.monotonic()
        if self._mgmt_token is None or now >= self._mgmt_token_refresh_at:
            self._mgmt_token = self._generate_management_token()
            # Token lifetime is 60 minutes; rotate after 50 as safety margin.
            self._mgmt_token_refresh_at = now + (50 * 60)
        return self._mgmt_token

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to the 100ms API."""
        url = f"{self._base_url}/{path.lstrip('/')}"
        token = self._get_management_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.request(
                    method,
                    url,
                    headers=headers,
                    json=json_body,
                    params=params,
                )
        except httpx.TransportError as exc:
            logger.error(
                "100ms API unreachable for %s %s: %s",
                method,
                path,
                exc,
            )
            raise HundredMsError(
                message=f"100ms API unreachable: {exc}",
                status_code=None,
            ) from exc

        if response.status_code >= 400:
            error_body: dict[str, Any] = {}
            try:
                parsed_body = response.json()
                if isinstance(parsed_body, dict):
                    error_body = parsed_body
                else:
                    error_body = {"raw": response.text[:500]}
            except Exception:
                error_body = {"raw": response.text[:500]}

            details = error_body.get("details", None)
            message = error_body.get("message") or error_body.get("description") or response.text

            logger.error(
                "100ms API error %s for %s %s: %s",
                response.status_code,
                method,
                path,
                response.text[:500],
            )
            raise HundredMsError(
                message=message,
                status_code=response.status_code,
                details=details,
            )

        return cast(dict[str, Any], response.json())

    # ── High-level API methods ──────────────────────────────────────────

    def create_room(
        self,
        *,
        name: str,
        description: str | None = None,
        template_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a 100ms room.

        If a room with the same name already exists, 100ms returns the existing
        room. We use this as idempotency — room name = f"lesson-{booking_id}".
        """
        body: dict[str, Any] = {"name": name}
        tid = template_id or self._template_id
        if tid:
            body["template_id"] = tid
        if description:
            body["description"] = description

        return self._request("POST", "rooms", json_body=body)

    def get_room(self, room_id: str) -> dict[str, Any]:
        """Get room details by 100ms room ID."""
        return self._request("GET", f"rooms/{room_id}")

    def disable_room(self, room_id: str) -> dict[str, Any]:
        """Disable a room so it cannot be joined."""
        return self._request("POST", f"rooms/{room_id}", json_body={"enabled": False})

    def get_active_session(self, room_id: str) -> dict[str, Any] | None:
        """Get the active session for a room. Returns None if no active session."""
        try:
            return self._request("GET", f"active-rooms/{room_id}")
        except HundredMsError as e:
            if e.status_code == 404:
                return None
            raise

    def generate_auth_token(
        self,
        *,
        room_id: str,
        user_id: str,
        role: str,
        validity_seconds: int = 3600,
    ) -> str:
        """Generate a per-participant auth token for joining a 100ms room.

        Unlike management tokens, auth tokens specify a room, user, and role.
        The frontend SDK uses this token to authenticate and connect.
        """
        now = int(time.time())
        payload = {
            "access_key": self._access_key,
            "room_id": room_id,
            "user_id": user_id,
            "role": role,
            "type": "app",
            "version": 2,
            "jti": str(uuid.uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + validity_seconds,
            "metadata": json.dumps({"user_id": user_id}),
        }
        token: str = jwt.encode(
            payload,
            self._app_secret,
            algorithm="HS256",
            headers={"alg": "HS256", "typ": "JWT"},
        )
        return token


class FakeHundredMsClient:
    """In-memory stub for testing/non-production environments."""

    def __init__(self, **kwargs: Any) -> None:
        self._calls: list[dict[str, Any]] = []
        self._errors: dict[str, HundredMsError] = {}

    def set_error(self, method: str, error: HundredMsError) -> None:
        """Inject a method-specific error for deterministic failure testing."""
        self._errors[method] = error

    def clear_errors(self) -> None:
        """Reset all injected fake-client errors."""
        self._errors.clear()

    def _raise_if_injected(self, method: str) -> None:
        error = self._errors.get(method)
        if error is not None:
            raise error

    def create_room(self, *, name: str, **kwargs: Any) -> dict[str, Any]:
        call: dict[str, Any] = {"method": "create_room", "name": name, **kwargs}
        self._calls.append(call)
        self._raise_if_injected("create_room")
        return {
            "id": f"fake_room_{uuid.uuid4().hex[:12]}",
            "name": name,
            "enabled": True,
            "template_id": "fake_template_id",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }

    def get_room(self, room_id: str) -> dict[str, Any]:
        self._calls.append({"method": "get_room", "room_id": room_id})
        return {"id": room_id, "name": "fake-room", "enabled": True}

    def disable_room(self, room_id: str) -> dict[str, Any]:
        self._calls.append({"method": "disable_room", "room_id": room_id})
        self._raise_if_injected("disable_room")
        return {"id": room_id, "enabled": False}

    def get_active_session(self, room_id: str) -> dict[str, Any] | None:
        self._calls.append({"method": "get_active_session", "room_id": room_id})
        self._raise_if_injected("get_active_session")
        return None

    def generate_auth_token(self, *, room_id: str, user_id: str, role: str, **kwargs: Any) -> str:
        self._calls.append(
            {"method": "generate_auth_token", "room_id": room_id, "user_id": user_id, "role": role}
        )
        self._raise_if_injected("generate_auth_token")
        return f"fake_auth_token_{room_id}_{user_id}"
