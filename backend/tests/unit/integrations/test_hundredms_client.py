"""Tests for the 100ms integration client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import jwt
from pydantic import SecretStr
import pytest

from app.integrations.hundredms_client import (
    FakeHundredMsClient,
    HundredMsClient,
    HundredMsError,
)

# ── Management token tests ─────────────────────────────────────────────


class TestManagementToken:
    def _make_client(self, **overrides):
        defaults = {
            "access_key": "test_access_key",
            "app_secret": "test_secret_value_for_hmac_256bit",
        }
        defaults.update(overrides)
        return HundredMsClient(**defaults)

    def test_management_token_is_valid_jwt(self):
        client = self._make_client()
        token = client._generate_management_token()
        payload = jwt.decode(token, "test_secret_value_for_hmac_256bit", algorithms=["HS256"])
        assert isinstance(payload, dict)

    def test_management_token_has_correct_payload(self):
        client = self._make_client()
        token = client._generate_management_token()
        payload = jwt.decode(token, "test_secret_value_for_hmac_256bit", algorithms=["HS256"])
        assert payload["access_key"] == "test_access_key"
        assert payload["type"] == "management"
        assert payload["version"] == 2
        assert "iat" in payload
        assert "nbf" in payload

    def test_management_token_expiry_is_one_hour(self):
        client = self._make_client()
        token = client._generate_management_token()
        payload = jwt.decode(token, "test_secret_value_for_hmac_256bit", algorithms=["HS256"])
        assert payload["exp"] - payload["iat"] == 3600

    def test_management_token_header_uses_standard_fields(self):
        client = self._make_client()
        token = client._generate_management_token()
        headers = jwt.get_unverified_header(token)
        assert "jti" not in headers
        assert headers["alg"] == "HS256"
        assert headers["typ"] == "JWT"

    def test_secret_str_unwrapped(self):
        secret = SecretStr("my_secret_value_for_hmac_256bits")
        client = HundredMsClient(access_key="key123", app_secret=secret)
        token = client._generate_management_token()
        payload = jwt.decode(token, "my_secret_value_for_hmac_256bits", algorithms=["HS256"])
        assert payload["access_key"] == "key123"


# ── HTTP request tests (mocked) ────────────────────────────────────────


class TestCreateRoom:
    def _make_client(self, **overrides):
        defaults = {
            "access_key": "test_access_key",
            "app_secret": "test_secret_value_for_hmac_256bit",
            "template_id": "tmpl_default",
        }
        defaults.update(overrides)
        return HundredMsClient(**defaults)

    @patch("app.integrations.hundredms_client.httpx.Client")
    def test_create_room_sends_correct_body(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "room_123",
            "name": "lesson-abc",
            "enabled": True,
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = self._make_client()
        result = client.create_room(name="lesson-abc")

        call_args = mock_client.request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "https://api.100ms.live/v2/rooms"
        body = call_args[1]["json"]
        assert body["name"] == "lesson-abc"
        assert body["template_id"] == "tmpl_default"
        assert result["id"] == "room_123"

    @patch("app.integrations.hundredms_client.httpx.Client")
    def test_create_room_with_template_override(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "room_456", "name": "lesson-xyz"}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = self._make_client()
        client.create_room(name="lesson-xyz", template_id="tmpl_override")

        body = mock_client.request.call_args[1]["json"]
        assert body["template_id"] == "tmpl_override"

    @patch("app.integrations.hundredms_client.httpx.Client")
    def test_create_room_handles_4xx_error(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.json.return_value = {
            "message": "Invalid room name",
            "details": {"field": "name"},
        }
        mock_response.text = "Invalid room name"
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = self._make_client()
        with pytest.raises(HundredMsError) as exc_info:
            client.create_room(name="bad-room")

        assert exc_info.value.status_code == 422
        assert "Invalid room name" in exc_info.value.message
        assert exc_info.value.details == {"field": "name"}

    @patch("app.integrations.hundredms_client.httpx.Client")
    def test_create_room_handles_5xx_error(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = ValueError("no json")
        mock_response.text = "Internal Server Error"
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = self._make_client()
        with pytest.raises(HundredMsError) as exc_info:
            client.create_room(name="some-room")

        assert exc_info.value.status_code == 500
        assert exc_info.value.message == "Internal Server Error"

    @patch("app.integrations.hundredms_client.httpx.Client")
    def test_create_room_wraps_transport_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.side_effect = httpx.TransportError("connection failed")
        mock_client_cls.return_value = mock_client

        client = self._make_client()
        with pytest.raises(HundredMsError) as exc_info:
            client.create_room(name="lesson-net")

        assert exc_info.value.status_code is None
        assert "unreachable" in exc_info.value.message


class TestDisableRoom:
    @patch("app.integrations.hundredms_client.httpx.Client")
    def test_disable_room_sends_enabled_false(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "room_123", "enabled": False}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = HundredMsClient(access_key="k", app_secret="test_secret_value_for_hmac_256bit")
        result = client.disable_room("room_123")

        call_args = mock_client.request.call_args
        assert call_args[0][0] == "POST"
        assert "rooms/room_123" in call_args[0][1]
        assert call_args[1]["json"] == {"enabled": False}
        assert result["enabled"] is False


class TestGetRoom:
    @patch("app.integrations.hundredms_client.httpx.Client")
    def test_get_room_returns_dict(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "room_789",
            "name": "lesson-abc",
            "enabled": True,
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = HundredMsClient(access_key="k", app_secret="test_secret_value_for_hmac_256bit")
        result = client.get_room("room_789")

        assert result["id"] == "room_789"
        call_args = mock_client.request.call_args
        assert call_args[0][0] == "GET"
        assert "rooms/room_789" in call_args[0][1]


class TestCreateRoomWithDescription:
    @patch("app.integrations.hundredms_client.httpx.Client")
    def test_create_room_includes_description_in_body(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "room_999", "name": "lesson-desc"}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = HundredMsClient(
            access_key="test_access_key",
            app_secret="test_secret_value_for_hmac_256bit",
            template_id="tmpl_default",
        )
        result = client.create_room(name="lesson-desc", description="Piano lesson at 3pm")

        body = mock_client.request.call_args[1]["json"]
        assert body["name"] == "lesson-desc"
        assert body["description"] == "Piano lesson at 3pm"
        assert result["id"] == "room_999"


class TestGetActiveSession:
    @patch("app.integrations.hundredms_client.httpx.Client")
    def test_returns_none_on_404(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"message": "Not found"}
        mock_response.text = "Not found"
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = HundredMsClient(access_key="k", app_secret="test_secret_value_for_hmac_256bit")
        result = client.get_active_session("room_abc")

        assert result is None

    @patch("app.integrations.hundredms_client.httpx.Client")
    def test_reraises_non_404_error(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"message": "Internal Server Error"}
        mock_response.text = "Internal Server Error"
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = HundredMsClient(access_key="k", app_secret="test_secret_value_for_hmac_256bit")
        with pytest.raises(HundredMsError) as exc_info:
            client.get_active_session("room_abc")

        assert exc_info.value.status_code == 500


# ── FakeHundredMsClient tests ──────────────────────────────────────────


class TestFakeHundredMsClient:
    def test_create_room_returns_valid_structure(self):
        client = FakeHundredMsClient()
        result = client.create_room(name="lesson-abc")

        assert "id" in result
        assert result["name"] == "lesson-abc"
        assert result["enabled"] is True
        assert "template_id" in result

    def test_tracks_calls(self):
        client = FakeHundredMsClient()
        client.create_room(name="lesson-1")
        client.get_room("room_id")
        client.get_active_session("room_id")

        assert len(client._calls) == 3
        assert client._calls[0]["method"] == "create_room"
        assert client._calls[0]["name"] == "lesson-1"
        assert client._calls[1]["method"] == "get_room"
        assert client._calls[2]["method"] == "get_active_session"

    def test_get_room_returns_dict(self):
        client = FakeHundredMsClient()
        result = client.get_room("room_xyz")
        assert result["id"] == "room_xyz"

    def test_get_active_session_returns_none(self):
        client = FakeHundredMsClient()
        assert client.get_active_session("room_xyz") is None

    def test_disable_room_returns_disabled(self):
        client = FakeHundredMsClient()
        result = client.disable_room("room_xyz")
        assert result["id"] == "room_xyz"
        assert result["enabled"] is False

    def test_generate_auth_token_returns_fake_string(self):
        client = FakeHundredMsClient()
        token = client.generate_auth_token(room_id="room_abc", user_id="user_123", role="guest")
        assert token == "fake_auth_token_room_abc_user_123"

    def test_generate_auth_token_tracks_call(self):
        client = FakeHundredMsClient()
        client.disable_room("room_abc")
        client.generate_auth_token(room_id="room_abc", user_id="user_123", role="host")
        assert len(client._calls) == 2
        assert client._calls[0]["method"] == "disable_room"
        assert client._calls[1]["method"] == "generate_auth_token"
        assert client._calls[1]["room_id"] == "room_abc"
        assert client._calls[1]["user_id"] == "user_123"
        assert client._calls[1]["role"] == "host"

    def test_create_room_raises_injected_error(self):
        client = FakeHundredMsClient()
        client.set_error("create_room", HundredMsError("boom", status_code=500))

        with pytest.raises(HundredMsError, match="boom"):
            client.create_room(name="lesson-err")

    def test_disable_room_raises_injected_error(self):
        client = FakeHundredMsClient()
        client.set_error("disable_room", HundredMsError("disable failed", status_code=500))

        with pytest.raises(HundredMsError, match="disable failed"):
            client.disable_room("room_err")

    def test_generate_auth_token_raises_injected_error(self):
        client = FakeHundredMsClient()
        client.set_error("generate_auth_token", HundredMsError("token failed", status_code=500))

        with pytest.raises(HundredMsError, match="token failed"):
            client.generate_auth_token(room_id="room_abc", user_id="user_123", role="guest")

    def test_get_active_session_raises_injected_error(self):
        client = FakeHundredMsClient()
        client.set_error("get_active_session", HundredMsError("session failed", status_code=503))

        with pytest.raises(HundredMsError, match="session failed"):
            client.get_active_session("room_abc")

    def test_clear_errors_allows_followup_calls(self):
        client = FakeHundredMsClient()
        client.set_error("create_room", HundredMsError("temporary", status_code=500))

        with pytest.raises(HundredMsError):
            client.create_room(name="lesson-1")

        client.clear_errors()
        result = client.create_room(name="lesson-2")
        assert result["name"] == "lesson-2"


# ── Auth token tests ──────────────────────────────────────────────────


class TestAuthToken:
    def _make_client(self, **overrides):
        defaults = {
            "access_key": "test_access_key",
            "app_secret": "test_secret_value_for_hmac_256bit",
        }
        defaults.update(overrides)
        return HundredMsClient(**defaults)

    def test_auth_token_is_valid_jwt(self):
        client = self._make_client()
        token = client.generate_auth_token(
            room_id="room_abc", user_id="user_123", role="guest"
        )
        payload = jwt.decode(token, "test_secret_value_for_hmac_256bit", algorithms=["HS256"])
        assert isinstance(payload, dict)

    def test_auth_token_has_correct_payload(self):
        client = self._make_client()
        token = client.generate_auth_token(
            room_id="room_abc", user_id="user_123", role="guest"
        )
        payload = jwt.decode(token, "test_secret_value_for_hmac_256bit", algorithms=["HS256"])
        assert payload["access_key"] == "test_access_key"
        assert payload["room_id"] == "room_abc"
        assert payload["user_id"] == "user_123"
        assert payload["role"] == "guest"
        assert payload["type"] == "app"
        assert payload["version"] == 2
        assert "iat" in payload
        assert "nbf" in payload
        assert "exp" in payload

    def test_auth_token_has_correct_expiry(self):
        client = self._make_client()
        token = client.generate_auth_token(
            room_id="room_abc", user_id="user_123", role="host", validity_seconds=3600
        )
        payload = jwt.decode(token, "test_secret_value_for_hmac_256bit", algorithms=["HS256"])
        assert payload["exp"] == payload["iat"] + 3600

    def test_auth_token_header_uses_standard_fields(self):
        client = self._make_client()
        token = client.generate_auth_token(
            room_id="room_abc", user_id="user_123", role="guest"
        )
        headers = jwt.get_unverified_header(token)
        assert "jti" not in headers
        assert headers["alg"] == "HS256"
        assert headers["typ"] == "JWT"
