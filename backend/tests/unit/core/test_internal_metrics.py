"""Unit tests for core/internal_metrics.py — metrics auth, IP extraction, caching."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from prometheus_client import CONTENT_TYPE_LATEST
import pytest
from starlette.requests import Request
from starlette.responses import Response

import app.core.internal_metrics as internal_metrics
from app.core.internal_metrics import (
    _check_metrics_basic_auth,
    _extract_metrics_client_ip,
    _ip_allowed,
    _load_metrics_payload,
    _metrics_auth_failure,
    _metrics_method_not_allowed,
    prewarm_metrics_cache,
)
from app.core.metrics import METRICS_AUTH_FAILURE_TOTAL
from app.monitoring.prometheus_metrics import REGISTRY


def _make_request(headers: dict[str, str] | None = None, client_host: str | None = None) -> Request:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/internal/metrics",
        "headers": raw_headers,
        "client": (client_host, 1234) if client_host else None,
        "scheme": "http",
    }
    return Request(scope)


def _sample_value(metric_name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(metric_name, labels)
    return float(value or 0.0)


def _find_sample(metric_name: str, labels: dict[str, str]):
    for metric_family in METRICS_AUTH_FAILURE_TOTAL.collect():
        for sample in metric_family.samples:
            if sample.name == metric_name and sample.labels == labels:
                return sample
    return None

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

    def test_blank_cf_connecting_ip_falls_through_to_forwarded_for(self) -> None:
        request = _make_request(
            {
                "cf-connecting-ip": " , 10.0.0.9",
                "x-forwarded-for": "10.0.0.7, 10.0.0.8",
            }
        )
        assert _extract_metrics_client_ip(request) == "10.0.0.7"

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

    def test_exact_string_match_fallback_when_ip_network_rejects_entry(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def raise_value_error(_entry: str, strict: bool = False):
            raise ValueError("bad allowlist entry")

        monkeypatch.setattr(internal_metrics, "ip_network", raise_value_error)
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

    @pytest.mark.parametrize(
        ("method_name", "handler"),
        [
            ("head", internal_metrics.internal_metrics_head),
            ("post", internal_metrics.internal_metrics_post),
            ("put", internal_metrics.internal_metrics_put),
            ("patch", internal_metrics.internal_metrics_patch),
            ("delete", internal_metrics.internal_metrics_delete),
            ("options", internal_metrics.internal_metrics_options),
        ],
    )
    def test_route_wrappers_emit_method_counter(
        self,
        method_name: str,
        handler,
    ) -> None:
        metric_name = "instainstru_metrics_auth_fail_total"
        labels = {"reason": "method"}

        assert REGISTRY._names_to_collectors[metric_name] is METRICS_AUTH_FAILURE_TOTAL
        assert METRICS_AUTH_FAILURE_TOTAL._labelnames == ("reason",)

        metric_family = list(METRICS_AUTH_FAILURE_TOTAL.collect())[0]
        assert metric_family.type == "counter"

        before = _sample_value(metric_name, labels)

        with pytest.raises(HTTPException) as first_exc:
            handler()
        assert first_exc.value.status_code == 405
        assert first_exc.value.headers["Allow"] == "GET"

        first_sample = _find_sample(metric_name, labels)
        assert first_sample is not None, f"{method_name} did not register {metric_name}"
        assert first_sample.labels == labels
        assert first_sample.value == before + 1.0

        with pytest.raises(HTTPException) as second_exc:
            handler()
        assert second_exc.value.status_code == 405
        assert second_exc.value.headers["Allow"] == "GET"

        second_sample = _find_sample(metric_name, labels)
        assert second_sample is not None, f"{method_name} lost {metric_name}"
        assert second_sample.labels == labels
        assert second_sample.value == first_sample.value + 1.0


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

    def test_stale_cache_refreshes_payload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stale_at = 50.0
        monkeypatch.setattr(internal_metrics, "_metrics_cache", (stale_at, b"stale"))
        monkeypatch.setattr(
            internal_metrics,
            "monotonic",
            lambda: stale_at + internal_metrics._METRICS_CACHE_TTL_SECONDS + 0.01,
        )
        monkeypatch.setattr(internal_metrics, "generate_latest", lambda _registry: b"fresh")

        result = _load_metrics_payload(1_000_000)

        assert result == b"fresh"


# ---------------------------------------------------------------------------
# internal_metrics_endpoint
# ---------------------------------------------------------------------------


class TestInternalMetricsEndpoint:
    def test_returns_prometheus_payload_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.core.config.settings",
            SimpleNamespace(metrics_ip_allowlist=[], metrics_max_bytes=1024),
            raising=False,
        )
        monkeypatch.setattr(internal_metrics, "_load_metrics_payload", lambda _max_bytes: b"payload")

        response = internal_metrics.internal_metrics_endpoint(_make_request(client_host="10.0.0.1"))

        assert response.status_code == 200
        assert response.body == b"payload"
        assert response.headers["content-type"] == CONTENT_TYPE_LATEST
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Pragma"] == "no-cache"

    def test_returns_payload_response_passthrough(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload_response = Response(
            content=b"metrics payload exceeds configured limit",
            status_code=503,
            media_type="text/plain; charset=utf-8",
        )
        monkeypatch.setattr(
            "app.core.config.settings",
            SimpleNamespace(metrics_ip_allowlist=[], metrics_max_bytes=8),
            raising=False,
        )
        monkeypatch.setattr(
            internal_metrics,
            "_load_metrics_payload",
            lambda _max_bytes: payload_response,
        )

        response = internal_metrics.internal_metrics_endpoint(_make_request(client_host="10.0.0.1"))

        assert response is payload_response

    def test_forbidden_ip_emits_forbidden_metric(self, monkeypatch: pytest.MonkeyPatch) -> None:
        labels = {"reason": "forbidden"}
        before = _sample_value("instainstru_metrics_auth_fail_total", labels)

        monkeypatch.setattr(
            "app.core.config.settings",
            SimpleNamespace(metrics_ip_allowlist=["10.0.0.0/24"], metrics_max_bytes=1024),
            raising=False,
        )
        monkeypatch.setattr(
            internal_metrics,
            "_load_metrics_payload",
            lambda _max_bytes: pytest.fail("_load_metrics_payload should not run"),
        )

        with pytest.raises(HTTPException) as exc_info:
            internal_metrics.internal_metrics_endpoint(_make_request(client_host="192.168.1.25"))

        assert exc_info.value.status_code == 403
        assert _sample_value("instainstru_metrics_auth_fail_total", labels) == before + 1.0


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
