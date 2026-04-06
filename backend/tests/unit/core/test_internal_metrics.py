"""Unit tests for core/internal_metrics.py — metrics auth, IP extraction, caching."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import HTTPException
import pytest

from app.core.internal_metrics import (
    _check_metrics_basic_auth,
    _extract_metrics_client_ip,
    _ip_allowed,
    _load_metrics_payload,
    _metrics_auth_failure,
    _metrics_method_not_allowed,
    prewarm_metrics_cache,
)

# ---------------------------------------------------------------------------
# _metrics_auth_failure
# ---------------------------------------------------------------------------


class TestMetricsAuthFailure:
    @patch("app.core.internal_metrics.METRICS_AUTH_FAILURE_TOTAL")
    def test_increments_counter(self, mock_counter: MagicMock) -> None:
        _metrics_auth_failure("test_reason")
        mock_counter.labels.assert_called_once_with(reason="test_reason")

    @patch("app.core.internal_metrics.METRICS_AUTH_FAILURE_TOTAL")
    def test_counter_exception_caught(self, mock_counter: MagicMock) -> None:
        mock_counter.labels.side_effect = Exception("prometheus crash")
        _metrics_auth_failure("test_reason")  # should not raise


# ---------------------------------------------------------------------------
# _extract_metrics_client_ip
# ---------------------------------------------------------------------------


class TestExtractMetricsClientIP:
    def test_cf_connecting_ip(self) -> None:
        request = MagicMock()
        request.headers = {"cf-connecting-ip": "1.2.3.4"}
        assert _extract_metrics_client_ip(request) == "1.2.3.4"

    def test_x_forwarded_for_first_ip(self) -> None:
        request = MagicMock()
        request.headers = {"x-forwarded-for": "10.0.0.1, 10.0.0.2"}
        assert _extract_metrics_client_ip(request) == "10.0.0.1"

    def test_client_host_fallback(self) -> None:
        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        assert _extract_metrics_client_ip(request) == "127.0.0.1"

    def test_no_client_returns_empty(self) -> None:
        request = MagicMock()
        request.headers = {}
        request.client = None
        assert _extract_metrics_client_ip(request) == ""


# ---------------------------------------------------------------------------
# _ip_allowed
# ---------------------------------------------------------------------------


class TestIpAllowed:
    def test_empty_string_not_allowed(self) -> None:
        assert _ip_allowed("", ["10.0.0.0/8"]) is False

    def test_valid_ip_in_network(self) -> None:
        assert _ip_allowed("10.0.0.5", ["10.0.0.0/8"]) is True

    def test_valid_ip_not_in_network(self) -> None:
        assert _ip_allowed("192.168.1.1", ["10.0.0.0/8"]) is False

    def test_invalid_ip_string(self) -> None:
        assert _ip_allowed("not-an-ip", ["10.0.0.0/8"]) is False

    def test_exact_string_match_fallback(self) -> None:
        """Valid IP, invalid network entry → falls back to exact string match."""
        assert _ip_allowed("10.0.0.1", ["10.0.0.1"]) is True

    def test_invalid_network_no_match(self) -> None:
        """Valid IP, invalid network entry, no exact match → False."""
        assert _ip_allowed("10.0.0.1", ["bad-network"]) is False


# ---------------------------------------------------------------------------
# _metrics_method_not_allowed
# ---------------------------------------------------------------------------


class TestMetricsMethodNotAllowed:
    @patch("app.core.internal_metrics.METRICS_AUTH_FAILURE_TOTAL")
    def test_raises_405(self, mock_counter: MagicMock) -> None:
        with pytest.raises(HTTPException) as exc_info:
            _metrics_method_not_allowed()
        assert exc_info.value.status_code == 405


# ---------------------------------------------------------------------------
# _check_metrics_basic_auth
# ---------------------------------------------------------------------------


class TestCheckMetricsBasicAuth:
    @patch("app.core.config.settings")
    def test_disabled_returns_immediately(self, mock_settings: MagicMock) -> None:
        mock_settings.metrics_basic_auth_enabled = False
        request = MagicMock()
        _check_metrics_basic_auth(request)

    @patch("app.core.internal_metrics.METRICS_AUTH_FAILURE_TOTAL")
    @patch("app.core.config.settings")
    def test_missing_auth_header_raises_401(self, mock_settings: MagicMock, mock_counter: MagicMock) -> None:
        mock_settings.metrics_basic_auth_enabled = True
        request = MagicMock()
        request.headers = {}

        with pytest.raises(HTTPException) as exc_info:
            _check_metrics_basic_auth(request)
        assert exc_info.value.status_code == 401

    @patch("app.core.internal_metrics.METRICS_AUTH_FAILURE_TOTAL")
    @patch("app.core.config.settings")
    def test_invalid_base64_raises_401(self, mock_settings: MagicMock, mock_counter: MagicMock) -> None:
        mock_settings.metrics_basic_auth_enabled = True
        request = MagicMock()
        request.headers = {"authorization": "Basic !!!invalid!!!"}

        with pytest.raises(HTTPException) as exc_info:
            _check_metrics_basic_auth(request)
        assert exc_info.value.status_code == 401

    @patch("app.core.internal_metrics.METRICS_AUTH_FAILURE_TOTAL")
    @patch("app.core.config.settings")
    def test_wrong_credentials_raises_401(self, mock_settings: MagicMock, mock_counter: MagicMock) -> None:
        import base64

        mock_settings.metrics_basic_auth_enabled = True
        mock_settings.metrics_basic_auth_user = MagicMock()
        mock_settings.metrics_basic_auth_user.get_secret_value.return_value = "admin"
        mock_settings.metrics_basic_auth_pass = MagicMock()
        mock_settings.metrics_basic_auth_pass.get_secret_value.return_value = "secret"

        request = MagicMock()
        creds = base64.b64encode(b"wrong:wrong").decode()
        request.headers = {"authorization": f"Basic {creds}"}

        with pytest.raises(HTTPException) as exc_info:
            _check_metrics_basic_auth(request)
        assert exc_info.value.status_code == 401

    @patch("app.core.config.settings")
    def test_correct_credentials_passes(self, mock_settings: MagicMock) -> None:
        import base64

        mock_settings.metrics_basic_auth_enabled = True
        mock_settings.metrics_basic_auth_user = MagicMock()
        mock_settings.metrics_basic_auth_user.get_secret_value.return_value = "admin"
        mock_settings.metrics_basic_auth_pass = MagicMock()
        mock_settings.metrics_basic_auth_pass.get_secret_value.return_value = "secret"

        request = MagicMock()
        creds = base64.b64encode(b"admin:secret").decode()
        request.headers = {"authorization": f"Basic {creds}"}

        _check_metrics_basic_auth(request)  # should not raise


# ---------------------------------------------------------------------------
# _load_metrics_payload
# ---------------------------------------------------------------------------


class TestLoadMetricsPayload:
    @patch("app.core.internal_metrics.generate_latest", return_value=b"metrics data")
    def test_fresh_load(self, mock_gen: MagicMock) -> None:
        import app.core.internal_metrics as mod

        mod._metrics_cache = None
        result = _load_metrics_payload(1_000_000)
        assert result == b"metrics data"

    @patch("app.core.internal_metrics.generate_latest", return_value=b"x" * 100)
    def test_exceeds_max_bytes(self, mock_gen: MagicMock) -> None:
        import app.core.internal_metrics as mod

        mod._metrics_cache = None
        result = _load_metrics_payload(10)  # max 10 bytes, payload is 100
        from starlette.responses import Response

        assert isinstance(result, Response)
        assert result.status_code == 503

    def test_cache_hit(self) -> None:
        from time import monotonic

        import app.core.internal_metrics as mod

        mod._metrics_cache = (monotonic(), b"cached data")
        result = _load_metrics_payload(1_000_000)
        assert result == b"cached data"
        mod._metrics_cache = None  # cleanup


# ---------------------------------------------------------------------------
# prewarm_metrics_cache
# ---------------------------------------------------------------------------


class TestPrewarmMetricsCache:
    @patch("app.core.internal_metrics.prometheus_metrics")
    def test_prewarm_success(self, mock_prom: MagicMock) -> None:
        with patch("app.routes.v1.prometheus.warm_prometheus_metrics_response_cache"):
            prewarm_metrics_cache()
        mock_prom.prewarm.assert_called_once()

    @patch("app.core.internal_metrics.prometheus_metrics")
    def test_prewarm_exception_caught(self, mock_prom: MagicMock) -> None:
        with patch(
            "app.routes.v1.prometheus.warm_prometheus_metrics_response_cache",
            side_effect=Exception("fail"),
        ):
            prewarm_metrics_cache()  # should not raise
