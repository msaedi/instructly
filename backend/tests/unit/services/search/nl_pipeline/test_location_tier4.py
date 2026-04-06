"""Unit tests for location_tier4.py — pure helper function coverage."""

from __future__ import annotations

from unittest.mock import Mock

from app.services.search.nl_pipeline.location_tier4 import (
    _build_tier4_result,
    _candidate_similarity,
    _record_tier4_error,
)

# ---------------------------------------------------------------------------
# _record_tier4_error (line 96)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _build_tier4_result (lines 118-126)
# ---------------------------------------------------------------------------


class TestBuildTier4Result:
    def test_none_embedding_without_diagnostics(self) -> None:
        """embedding=None, diagnostics=None → returns (None, [])."""
        result, names = _build_tier4_result(
            embedding=None,
            region_lookup=Mock(embeddings=[]),
            location_llm_top_k=5,
            llm_embedding_threshold=0.3,
            diagnostics=None,
            tier4_start=0.0,
        )
        assert result is None
        assert names == []

    def test_none_embedding_with_diagnostics_records_miss(self) -> None:
        """embedding=None, diagnostics present → records MISS, returns (None, [])."""
        diagnostics = Mock()
        result, names = _build_tier4_result(
            embedding=None,
            region_lookup=Mock(embeddings=[]),
            location_llm_top_k=5,
            llm_embedding_threshold=0.3,
            diagnostics=diagnostics,
            tier4_start=0.0,
        )
        assert result is None
        assert names == []
        diagnostics.record_location_tier.assert_called_once()
        call_kwargs = diagnostics.record_location_tier.call_args.kwargs
        assert call_kwargs["status"] == "miss"
        assert call_kwargs["details"] == "no_embedding"

    def test_empty_list_embedding_treated_as_falsy(self) -> None:
        """embedding=[] is falsy → same early return path."""
        result, names = _build_tier4_result(
            embedding=[],
            region_lookup=Mock(embeddings=[]),
            location_llm_top_k=5,
            llm_embedding_threshold=0.3,
            diagnostics=None,
            tier4_start=0.0,
        )
        assert result is None
        assert names == []


# ---------------------------------------------------------------------------
# _record_tier4_error (line 96)
# ---------------------------------------------------------------------------


class TestRecordTier4Error:
    def test_none_diagnostics_returns_early(self) -> None:
        """diagnostics=None → early return, no crash."""
        _record_tier4_error(diagnostics=None, started_at=0.0, error=Exception("test"))

    def test_with_diagnostics_records_error(self) -> None:
        """With valid diagnostics → record_location_tier is called."""
        diagnostics = Mock()
        _record_tier4_error(diagnostics=diagnostics, started_at=0.0, error=Exception("boom"))
        diagnostics.record_location_tier.assert_called_once()
        call_kwargs = diagnostics.record_location_tier.call_args.kwargs
        assert call_kwargs["tier"] == 4
        assert call_kwargs["attempted"] is True
        assert call_kwargs["status"] == "error"


# ---------------------------------------------------------------------------
# _candidate_similarity (lines 187-192)
# ---------------------------------------------------------------------------


class TestCandidateSimilarity:
    def test_float_value_returned_directly(self) -> None:
        assert _candidate_similarity({"similarity": 0.85}) == 0.85

    def test_int_value_converted_to_float(self) -> None:
        assert _candidate_similarity({"similarity": 1}) == 1.0

    def test_valid_string_converted(self) -> None:
        """String "0.85" → float 0.85 (line 187-189)."""
        assert _candidate_similarity({"similarity": "0.85"}) == 0.85

    def test_invalid_string_returns_zero(self) -> None:
        """Unparseable string "abc" → 0.0 (line 190-191)."""
        assert _candidate_similarity({"similarity": "abc"}) == 0.0

    def test_none_returns_zero(self) -> None:
        """None similarity → 0.0 (line 192)."""
        assert _candidate_similarity({"similarity": None}) == 0.0

    def test_list_returns_zero(self) -> None:
        """Non-numeric type (list) → 0.0 (line 192)."""
        assert _candidate_similarity({"similarity": [1, 2]}) == 0.0

    def test_missing_key_returns_zero(self) -> None:
        """No 'similarity' key at all → 0.0."""
        assert _candidate_similarity({}) == 0.0
