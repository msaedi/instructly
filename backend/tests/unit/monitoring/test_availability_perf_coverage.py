from __future__ import annotations

from app.monitoring import availability_perf


def test_is_perf_enabled(monkeypatch) -> None:
    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "1")
    assert availability_perf._is_perf_enabled() is True

    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "0")
    assert availability_perf._is_perf_enabled() is False


def test_serialize_value_handles_isoformat() -> None:
    class HasIso:
        def isoformat(self):
            return "iso-value"

    assert availability_perf._serialize_value(HasIso()) == "iso-value"
    assert availability_perf._serialize_value(None) is None


def test_availability_perf_span_emits_payload(monkeypatch) -> None:
    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "1")

    captured = {}

    def _emit(payload):
        captured.update(payload)

    monkeypatch.setattr(availability_perf, "_emit_payload", _emit)
    monkeypatch.setattr(availability_perf.time, "perf_counter", lambda: 1.0)

    with availability_perf.availability_perf_span("span", user_id="u1") as set_extra:
        assert set_extra is not None
        set_extra(extra="ok")
        monkeypatch.setattr(availability_perf.time, "perf_counter", lambda: 1.1)

    assert captured["span"] == "span"
    assert captured["user_id"] == "u1"
    assert captured["extra"] == "ok"


def test_availability_perf_span_disabled(monkeypatch) -> None:
    monkeypatch.delenv("AVAILABILITY_PERF_DEBUG", raising=False)

    with availability_perf.availability_perf_span("span") as set_extra:
        assert set_extra is None


def test_estimate_payload_size_bytes() -> None:
    class WithModelDump:
        def model_dump_json(self):
            return "{\"a\": 1}"

    class WithJson:
        def json(self):
            return "{\"b\": 2}"

    assert availability_perf.estimate_payload_size_bytes(WithModelDump()) > 0
    assert availability_perf.estimate_payload_size_bytes(WithJson()) > 0
    assert availability_perf.estimate_payload_size_bytes({"c": 3}) > 0
    assert availability_perf.estimate_payload_size_bytes(None) == 0
