from __future__ import annotations

import pytest
from starlette.requests import Request

import app.main as main


def _make_request(headers: dict[str, str] | None = None, client_host: str | None = None) -> Request:
    raw_headers = []
    for key, value in (headers or {}).items():
        raw_headers.append((key.encode(), value.encode()))

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": raw_headers,
        "client": (client_host, 1234) if client_host else None,
        "scheme": "http",
    }
    return Request(scope)


def test_extract_metrics_client_ip_headers() -> None:
    request = _make_request({"x-forwarded-for": "1.2.3.4, 5.6.7.8"}, client_host="9.9.9.9")
    assert main._extract_metrics_client_ip(request) == "1.2.3.4"


def test_extract_metrics_client_ip_cf_header() -> None:
    request = _make_request({"cf-connecting-ip": "2.2.2.2"}, client_host="9.9.9.9")
    assert main._extract_metrics_client_ip(request) == "2.2.2.2"


def test_extract_metrics_client_ip_fallback_client() -> None:
    request = _make_request({}, client_host="3.3.3.3")
    assert main._extract_metrics_client_ip(request) == "3.3.3.3"


def test_ip_allowed_matches() -> None:
    assert main._ip_allowed("10.0.0.1", ["10.0.0.0/24"]) is True
    assert main._ip_allowed("10.0.0.1", ["10.0.0.1"]) is True
    assert main._ip_allowed("", ["10.0.0.1"]) is False
    assert main._ip_allowed("bad", ["10.0.0.1"]) is False


def test_metrics_method_not_allowed() -> None:
    with pytest.raises(Exception) as excinfo:
        main._metrics_method_not_allowed()

    error = excinfo.value
    assert getattr(error, "status_code", None) == 405
    assert getattr(error, "headers", {}).get("Allow") == "GET"


def test_metrics_auth_failure_increments(monkeypatch) -> None:
    calls = {"count": 0}

    class DummyCounter:
        def labels(self, **_kwargs):
            return self

        def inc(self):
            calls["count"] += 1

    monkeypatch.setattr(main, "METRICS_AUTH_FAILURE_TOTAL", DummyCounter())
    main._metrics_auth_failure("unauthorized")

    assert calls["count"] == 1


def test_check_metrics_basic_auth_disabled(monkeypatch) -> None:
    dummy_settings = type(
        "Settings",
        (),
        {
            "metrics_basic_auth_enabled": False,
            "metrics_basic_auth_user": None,
            "metrics_basic_auth_pass": None,
        },
    )()
    monkeypatch.setattr("app.core.config.settings", dummy_settings)

    request = _make_request()
    main._check_metrics_basic_auth(request)


def test_check_metrics_basic_auth_invalid(monkeypatch) -> None:
    class DummySecret:
        def __init__(self, value):
            self._value = value

        def get_secret_value(self):
            return self._value

    dummy_settings = type(
        "Settings",
        (),
        {
            "metrics_basic_auth_enabled": True,
            "metrics_basic_auth_user": DummySecret("user"),
            "metrics_basic_auth_pass": DummySecret("pass"),
        },
    )()
    monkeypatch.setattr("app.core.config.settings", dummy_settings)

    request = _make_request()
    with pytest.raises(Exception) as excinfo:
        main._check_metrics_basic_auth(request)

    assert getattr(excinfo.value, "status_code", None) == 401


def test_check_metrics_basic_auth_success(monkeypatch) -> None:
    class DummySecret:
        def __init__(self, value):
            self._value = value

        def get_secret_value(self):
            return self._value

    dummy_settings = type(
        "Settings",
        (),
        {
            "metrics_basic_auth_enabled": True,
            "metrics_basic_auth_user": DummySecret("user"),
            "metrics_basic_auth_pass": DummySecret("pass"),
        },
    )()
    monkeypatch.setattr("app.core.config.settings", dummy_settings)

    import base64

    token = base64.b64encode(b"user:pass").decode()
    request = _make_request({"authorization": f"Basic {token}"})
    main._check_metrics_basic_auth(request)
