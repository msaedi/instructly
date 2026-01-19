from __future__ import annotations

from collections import defaultdict

import pytest

from app.metrics import retention_metrics as metrics


def _reset_metrics(monkeypatch):
    monkeypatch.setattr(metrics, "_PROM_AVAILABLE", False)
    monkeypatch.setattr(metrics, "_totals", defaultdict(int))
    monkeypatch.setattr(metrics, "_errors", defaultdict(int))
    monkeypatch.setattr(metrics, "_chunk_sum", defaultdict(float))
    monkeypatch.setattr(metrics, "_chunk_count", defaultdict(int))


def test_inc_total_and_error_noop(monkeypatch):
    _reset_metrics(monkeypatch)

    metrics.inc_total("table", 0)
    metrics.inc_error("table", 0)

    assert metrics._totals == {}
    assert metrics._errors == {}


def test_inc_total_and_error(monkeypatch):
    _reset_metrics(monkeypatch)

    metrics.inc_total("bookings", 2)
    metrics.inc_error("bookings")

    assert metrics._totals["bookings"] == 2
    assert metrics._errors["bookings"] == 1


def test_time_chunk_records(monkeypatch):
    _reset_metrics(monkeypatch)

    times = iter([1.0, 2.5])
    monkeypatch.setattr(metrics, "perf_counter", lambda: next(times))

    with metrics.time_chunk("table"):
        pass

    assert metrics._chunk_count["table"] == 1
    assert metrics._chunk_sum["table"] == pytest.approx(1.5)


def test_render_text_with_metrics(monkeypatch):
    _reset_metrics(monkeypatch)

    metrics.inc_total("bookings", 3)
    metrics.inc_error("bookings", 2)
    with metrics.time_chunk("bookings"):
        pass

    text = metrics.render_text()

    assert "retention_purge_total" in text
    assert "retention_purge_errors_total" in text


def test_render_text_empty(monkeypatch):
    _reset_metrics(monkeypatch)

    text = metrics.render_text()

    assert "retention metrics not available" in text


def test_prometheus_paths(monkeypatch):
    class _Counter:
        def __init__(self):
            self.calls = []

        def labels(self, **_kwargs):
            self.calls.append("labels")
            return self

        def inc(self, n):
            self.calls.append(("inc", n))

    class _Timer:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Histogram:
        def labels(self, **_kwargs):
            return self

        def time(self):
            return _Timer()

    counter = _Counter()
    errors = _Counter()
    histogram = _Histogram()

    monkeypatch.setattr(metrics, "_PROM_AVAILABLE", True)
    monkeypatch.setattr(metrics, "_TOTAL_COUNTER", counter)
    monkeypatch.setattr(metrics, "_ERROR_COUNTER", errors)
    monkeypatch.setattr(metrics, "_CHUNK_HISTOGRAM", histogram)
    monkeypatch.setattr(metrics, "generate_latest", lambda: b"ok")

    metrics.inc_total("table", 2)
    metrics.inc_error("table", 3)
    with metrics.time_chunk("table"):
        pass

    assert ("inc", 2) in counter.calls
    assert ("inc", 3) in errors.calls
    assert metrics.render_text() == "ok"
