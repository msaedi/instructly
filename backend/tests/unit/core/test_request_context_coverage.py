"""Tests for app/core/request_context.py — coverage gaps L64, L66."""
from __future__ import annotations

import logging

import pytest

from app.core.request_context import (
    RequestIdFilter,
    _is_empty_otel_value,
    attach_request_id_filter,
)


@pytest.mark.unit
class TestIsEmptyOtelValueCoverage:
    """Cover _is_empty_otel_value edge cases — L64, L66."""

    def test_none_is_empty(self) -> None:
        """None is falsy => True."""
        assert _is_empty_otel_value(None) is True

    def test_empty_string_is_empty(self) -> None:
        assert _is_empty_otel_value("") is True

    def test_all_zeros_is_empty(self) -> None:
        """L65: string of all '0' chars is empty."""
        assert _is_empty_otel_value("0000000000000000") is True

    def test_single_zero_is_empty(self) -> None:
        assert _is_empty_otel_value("0") is True

    def test_whitespace_only_is_empty(self) -> None:
        """L63-64: stripped empty string is empty."""
        assert _is_empty_otel_value("   ") is True

    def test_zeros_with_whitespace_is_empty(self) -> None:
        """L65: strip then check all zeros."""
        assert _is_empty_otel_value("  000  ") is True

    def test_valid_trace_id_not_empty(self) -> None:
        assert _is_empty_otel_value("abc123def456") is False

    def test_mixed_zeros_and_chars_not_empty(self) -> None:
        assert _is_empty_otel_value("00a0") is False

    def test_integer_zero_is_empty(self) -> None:
        """int 0 is falsy => True."""
        assert _is_empty_otel_value(0) is True

    def test_integer_nonzero_not_empty(self) -> None:
        """L66: non-string non-falsy => False."""
        assert _is_empty_otel_value(42) is False

    def test_false_is_empty(self) -> None:
        """bool False is falsy => True."""
        assert _is_empty_otel_value(False) is True

    def test_true_is_not_empty(self) -> None:
        """bool True is truthy, not a string => L66: False."""
        assert _is_empty_otel_value(True) is False

    def test_empty_list_is_empty(self) -> None:
        """Empty list is falsy => True."""
        assert _is_empty_otel_value([]) is True

    def test_nonempty_list_is_not_empty(self) -> None:
        """Non-empty list is truthy, not string => L66: False."""
        assert _is_empty_otel_value([1]) is False


@pytest.mark.unit
class TestRequestIdFilterOtelBranches:
    """Test filter with existing otelTraceID/otelSpanID attributes."""

    def test_filter_with_valid_trace_id(self) -> None:
        """When record already has valid otelTraceID, don't overwrite."""
        filt = RequestIdFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        record.otelTraceID = "abc123"  # type: ignore[attr-defined]
        record.otelSpanID = "def456"  # type: ignore[attr-defined]
        filt.filter(record)
        assert record.otelTraceID == "abc123"  # type: ignore[attr-defined]
        assert record.otelSpanID == "def456"  # type: ignore[attr-defined]

    def test_filter_with_all_zeros_trace_id(self) -> None:
        """All-zeros trace ID should be replaced with 'no-trace'."""
        filt = RequestIdFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        record.otelTraceID = "00000000000000000000000000000000"  # type: ignore[attr-defined]
        record.otelSpanID = "0000000000000000"  # type: ignore[attr-defined]
        filt.filter(record)
        assert record.otelTraceID == "no-trace"  # type: ignore[attr-defined]
        assert record.otelSpanID == "no-span"  # type: ignore[attr-defined]

    def test_filter_with_none_otel_values(self) -> None:
        """None otel values should be replaced."""
        filt = RequestIdFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        record.otelTraceID = None  # type: ignore[attr-defined]
        record.otelSpanID = None  # type: ignore[attr-defined]
        filt.filter(record)
        assert record.otelTraceID == "no-trace"  # type: ignore[attr-defined]
        assert record.otelSpanID == "no-span"  # type: ignore[attr-defined]


@pytest.mark.unit
class TestAttachRequestIdFilterCoverage:
    """Cover attach_request_id_filter."""

    def test_attach_to_specific_logger(self) -> None:
        logger = logging.getLogger("test.attach.coverage")
        handler = logging.StreamHandler()
        logger.addHandler(handler)
        initial_filter_count = len(handler.filters)
        attach_request_id_filter(logger)
        assert len(handler.filters) == initial_filter_count + 1
        logger.removeHandler(handler)
