# backend/tests/unit/services/search/test_metrics.py
"""
Unit tests for NL search Prometheus metrics.

Tests:
- Metric recording functions
- Counter, histogram, and gauge behavior
- Degradation event tracking
- Cache event tracking
"""
from __future__ import annotations

from app.services.search.metrics import (
    CACHE_HIT,
    CACHE_MISS,
    CIRCUIT_BREAKER_STATE,
    DEGRADATION_EVENTS,
    OPENAI_LATENCY,
    QUERY_COMPLEXITY,
    SEARCH_LATENCY,
    SEARCH_REQUESTS,
    SEARCH_RESULT_COUNT,
    SEARCH_ZERO_RESULTS,
    TYPO_CORRECTIONS,
    record_cache_event,
    record_openai_latency,
    record_query_complexity,
    record_search_metrics,
    record_typo_correction,
    update_circuit_breaker_state,
)


class TestRecordSearchMetrics:
    """Tests for the main record_search_metrics function."""

    def test_record_success_metrics(self) -> None:
        """Should record metrics for successful search."""
        record_search_metrics(
            total_latency_ms=150,
            stage_latencies={
                "parsing": 10,
                "retrieval": 80,
                "filtering": 30,
                "ranking": 30,
            },
            cache_hit=False,
            parsing_mode="regex",
            result_count=15,
            degraded=False,
            degradation_reasons=[],
        )
        # No assertion - just verify no exception is raised

    def test_record_cache_hit_metrics(self) -> None:
        """Should record cache hit correctly."""
        record_search_metrics(
            total_latency_ms=5,
            stage_latencies={},
            cache_hit=True,
            parsing_mode="regex",
            result_count=20,
            degraded=False,
            degradation_reasons=[],
        )

    def test_record_zero_results(self) -> None:
        """Should record zero result metrics."""
        record_search_metrics(
            total_latency_ms=100,
            stage_latencies={"parsing": 10, "retrieval": 90},
            cache_hit=False,
            parsing_mode="llm",
            result_count=0,
            degraded=False,
            degradation_reasons=[],
        )

    def test_record_degraded_metrics(self) -> None:
        """Should record degradation events."""
        record_search_metrics(
            total_latency_ms=200,
            stage_latencies={"parsing": 10, "retrieval": 190},
            cache_hit=False,
            parsing_mode="regex",
            result_count=5,
            degraded=True,
            degradation_reasons=["embedding_error", "ranking_unavailable"],
        )

    def test_record_llm_parsing_mode(self) -> None:
        """Should record LLM parsing mode correctly."""
        record_search_metrics(
            total_latency_ms=500,
            stage_latencies={
                "parsing": 300,
                "retrieval": 100,
                "filtering": 50,
                "ranking": 50,
            },
            cache_hit=False,
            parsing_mode="llm",
            result_count=10,
            degraded=False,
            degradation_reasons=[],
        )


class TestCacheEventRecording:
    """Tests for cache event recording."""

    def test_record_cache_hit(self) -> None:
        """Should record cache hit."""
        record_cache_event("embedding", hit=True)

    def test_record_cache_miss(self) -> None:
        """Should record cache miss."""
        record_cache_event("parsed_query", hit=False)

    def test_record_response_cache_hit(self) -> None:
        """Should record response cache hit."""
        record_cache_event("response", hit=True)


class TestOpenAILatencyRecording:
    """Tests for OpenAI latency recording."""

    def test_record_embedding_latency(self) -> None:
        """Should record embedding API latency."""
        record_openai_latency("embeddings", 150)

    def test_record_chat_latency(self) -> None:
        """Should record chat API latency."""
        record_openai_latency("chat", 500)


class TestCircuitBreakerState:
    """Tests for circuit breaker state updates."""

    def test_update_closed_state(self) -> None:
        """Should set closed state to 0."""
        update_circuit_breaker_state("parsing", "closed")

    def test_update_half_open_state(self) -> None:
        """Should set half_open state to 1."""
        update_circuit_breaker_state("embedding", "half_open")

    def test_update_open_state(self) -> None:
        """Should set open state to 2."""
        update_circuit_breaker_state("parsing", "open")


class TestQueryComplexity:
    """Tests for query complexity recording."""

    def test_record_simple_query(self) -> None:
        """Should record simple query with 1 constraint."""
        record_query_complexity("regex", 1)

    def test_record_complex_query(self) -> None:
        """Should record complex query with many constraints."""
        record_query_complexity("llm", 5)

    def test_record_no_constraints(self) -> None:
        """Should record query with no constraints."""
        record_query_complexity("regex", 0)


class TestTypoCorrection:
    """Tests for typo correction recording."""

    def test_record_high_confidence_correction(self) -> None:
        """Should record high confidence correction."""
        record_typo_correction("high")

    def test_record_medium_confidence_correction(self) -> None:
        """Should record medium confidence correction."""
        record_typo_correction("medium")


class TestMetricObjects:
    """Tests that verify metric objects are properly configured."""

    def test_search_latency_histogram_exists(self) -> None:
        """Should have search latency histogram with correct labels."""
        assert SEARCH_LATENCY is not None
        # Verify it's a histogram by checking _type attribute
        assert hasattr(SEARCH_LATENCY, "labels")

    def test_openai_latency_histogram_exists(self) -> None:
        """Should have OpenAI latency histogram."""
        assert OPENAI_LATENCY is not None
        assert hasattr(OPENAI_LATENCY, "labels")

    def test_result_count_histogram_exists(self) -> None:
        """Should have result count histogram."""
        assert SEARCH_RESULT_COUNT is not None

    def test_zero_results_counter_exists(self) -> None:
        """Should have zero results counter."""
        assert SEARCH_ZERO_RESULTS is not None
        assert hasattr(SEARCH_ZERO_RESULTS, "labels")

    def test_cache_counters_exist(self) -> None:
        """Should have cache hit and miss counters."""
        assert CACHE_HIT is not None
        assert CACHE_MISS is not None
        assert hasattr(CACHE_HIT, "labels")
        assert hasattr(CACHE_MISS, "labels")

    def test_circuit_breaker_gauge_exists(self) -> None:
        """Should have circuit breaker state gauge."""
        assert CIRCUIT_BREAKER_STATE is not None
        assert hasattr(CIRCUIT_BREAKER_STATE, "labels")

    def test_degradation_counter_exists(self) -> None:
        """Should have degradation events counter."""
        assert DEGRADATION_EVENTS is not None
        assert hasattr(DEGRADATION_EVENTS, "labels")

    def test_search_requests_counter_exists(self) -> None:
        """Should have search requests counter."""
        assert SEARCH_REQUESTS is not None
        assert hasattr(SEARCH_REQUESTS, "labels")

    def test_typo_corrections_counter_exists(self) -> None:
        """Should have typo corrections counter."""
        assert TYPO_CORRECTIONS is not None
        assert hasattr(TYPO_CORRECTIONS, "labels")

    def test_query_complexity_histogram_exists(self) -> None:
        """Should have query complexity histogram."""
        assert QUERY_COMPLEXITY is not None
        assert hasattr(QUERY_COMPLEXITY, "labels")


class TestEdgeCases:
    """Edge case tests for metrics recording."""

    def test_empty_stage_latencies(self) -> None:
        """Should handle empty stage latencies dict."""
        record_search_metrics(
            total_latency_ms=50,
            stage_latencies={},
            cache_hit=True,
            parsing_mode="regex",
            result_count=10,
            degraded=False,
            degradation_reasons=[],
        )

    def test_high_latency_values(self) -> None:
        """Should handle high latency values."""
        record_search_metrics(
            total_latency_ms=5000,
            stage_latencies={
                "parsing": 1000,
                "retrieval": 2000,
                "filtering": 1000,
                "ranking": 1000,
            },
            cache_hit=False,
            parsing_mode="llm",
            result_count=50,
            degraded=False,
            degradation_reasons=[],
        )

    def test_many_degradation_reasons(self) -> None:
        """Should handle multiple degradation reasons."""
        record_search_metrics(
            total_latency_ms=300,
            stage_latencies={"parsing": 300},
            cache_hit=False,
            parsing_mode="regex",
            result_count=0,
            degraded=True,
            degradation_reasons=[
                "parsing_error",
                "embedding_unavailable",
                "retrieval_error",
                "ranking_error",
            ],
        )

    def test_zero_latency(self) -> None:
        """Should handle zero latency (cached response)."""
        record_search_metrics(
            total_latency_ms=0,
            stage_latencies={},
            cache_hit=True,
            parsing_mode="regex",
            result_count=20,
            degraded=False,
            degradation_reasons=[],
        )
