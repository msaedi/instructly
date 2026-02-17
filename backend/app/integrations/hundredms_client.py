"""100ms Video Platform Integration Client.

Handles room creation, management token generation for server-to-server
communication with the 100ms REST API, and per-participant auth token
generation for joining rooms.
"""

from __future__ import annotations

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
        timeout: float = 30.0,
    ) -> None:
        self._access_key = access_key
        self._app_secret = (
            app_secret.get_secret_value() if isinstance(app_secret, SecretStr) else app_secret
        )
        self._base_url = base_url.rstrip("/")
        self._template_id = template_id
        self._timeout = timeout

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
            "iat": now,
            "nbf": now,
        }
        token: str = jwt.encode(
            payload,
            self._app_secret,
            algorithm="HS256",
            headers={"alg": "HS256", "typ": "JWT", "jti": str(uuid.uuid4())},
        )
        return token

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
        token = self._generate_management_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self._timeout) as client:
            response = client.request(
                method,
                url,
                headers=headers,
                json=json_body,
                params=params,
            )

        if response.status_code >= 400:
            error_body = None
            try:
                error_body = response.json()
            except Exception:
                pass

            message = response.text
            details = None
            if isinstance(error_body, dict):
                message = error_body.get("message", response.text)
                details = error_body.get("details")

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
        validity_seconds: int = 86400,
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
            "iat": now,
            "nbf": now,
            "exp": now + validity_seconds,
        }
        token: str = jwt.encode(
            payload,
            self._app_secret,
            algorithm="HS256",
            headers={"alg": "HS256", "typ": "JWT", "jti": str(uuid.uuid4())},
        )
        return token


class FakeHundredMsClient:
    """In-memory stub for testing/non-production environments."""

    def __init__(self, **kwargs: Any) -> None:
        self._calls: list[dict[str, Any]] = []

    def create_room(self, *, name: str, **kwargs: Any) -> dict[str, Any]:
        call: dict[str, Any] = {"method": "create_room", "name": name, **kwargs}
        self._calls.append(call)
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

    def get_active_session(self, room_id: str) -> dict[str, Any] | None:
        self._calls.append({"method": "get_active_session", "room_id": room_id})
        return None

    def generate_auth_token(self, *, room_id: str, user_id: str, role: str, **kwargs: Any) -> str:
        self._calls.append(
            {"method": "generate_auth_token", "room_id": room_id, "user_id": user_id, "role": role}
        )
        return f"fake_auth_token_{room_id}_{user_id}"
