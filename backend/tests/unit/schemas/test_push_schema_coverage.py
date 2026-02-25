"""Tests for app/schemas/push.py — coverage gap L45."""
from __future__ import annotations

import pytest

from app.schemas.push import PushSubscribeRequest


@pytest.mark.unit
class TestPushSubscribeRequestCoverage:
    """Cover validate_endpoint with non-HTTPS URLs."""

    def _valid_data(self, **overrides: object) -> dict:
        data = {
            "endpoint": "https://push.example.com/abc",
            "p256dh": "key123",
            "auth": "auth123",
        }
        data.update(overrides)
        return data

    def test_valid_https_endpoint(self) -> None:
        req = PushSubscribeRequest(**self._valid_data())
        assert req.endpoint.startswith("https://")

    def test_http_endpoint_raises(self) -> None:
        """L45: non-HTTPS URL raises ValueError."""
        with pytest.raises(Exception, match="HTTPS"):
            PushSubscribeRequest(**self._valid_data(endpoint="http://push.example.com/abc"))

    def test_empty_endpoint_raises(self) -> None:
        """Empty URL doesn't start with 'https://'."""
        with pytest.raises(Exception):
            PushSubscribeRequest(**self._valid_data(endpoint=""))

    def test_ftp_endpoint_raises(self) -> None:
        with pytest.raises(Exception, match="HTTPS"):
            PushSubscribeRequest(**self._valid_data(endpoint="ftp://push.example.com"))

    def test_no_scheme_raises(self) -> None:
        with pytest.raises(Exception, match="HTTPS"):
            PushSubscribeRequest(**self._valid_data(endpoint="push.example.com"))

    def test_endpoint_with_path(self) -> None:
        req = PushSubscribeRequest(
            **self._valid_data(endpoint="https://fcm.googleapis.com/fcm/send/abc123")
        )
        assert "fcm" in req.endpoint

    def test_user_agent_optional(self) -> None:
        req = PushSubscribeRequest(**self._valid_data())
        assert req.user_agent is None

    def test_user_agent_provided(self) -> None:
        req = PushSubscribeRequest(**self._valid_data(user_agent="Chrome/120"))
        assert req.user_agent == "Chrome/120"
