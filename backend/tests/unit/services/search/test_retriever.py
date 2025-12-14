# backend/tests/unit/services/search/test_retriever.py
"""
Unit tests for hybrid candidate retrieval.
"""
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.search.query_parser import ParsedQuery
from app.services.search.retriever import (
    MAX_CANDIDATES,
    SINGLE_SOURCE_PENALTY,
    TEXT_WEIGHT,
    VECTOR_WEIGHT,
    PostgresRetriever,
    RetrievalResult,
    ServiceCandidate,
)


@pytest.fixture
def mock_db() -> Mock:
    """Create mock database session."""
    return Mock()


@pytest.fixture
def mock_embedding_service() -> Mock:
    """Create mock embedding service."""
    service = Mock()
    service.embed_query = AsyncMock(return_value=[0.1] * 1536)
    return service


@pytest.fixture
def mock_repository() -> Mock:
    """Create mock retriever repository."""
    repo = Mock()

    # Default mock data
    repo.vector_search.return_value = [
        {
            "id": "svc_001",
            "catalog_id": "cat_001",
            "name": "Piano Lessons",
            "description": "Learn piano",
            "price_per_hour": 50,
            "instructor_id": "inst_001",
            "vector_score": 0.95,
        },
        {
            "id": "svc_002",
            "catalog_id": "cat_002",
            "name": "Guitar Lessons",
            "description": "Learn guitar",
            "price_per_hour": 45,
            "instructor_id": "inst_002",
            "vector_score": 0.80,
        },
    ]

    repo.text_search.return_value = [
        {
            "id": "svc_001",
            "catalog_id": "cat_001",
            "name": "Piano Lessons",
            "description": "Learn piano",
            "price_per_hour": 50,
            "instructor_id": "inst_001",
            "text_score": 0.90,
        },
        {
            "id": "svc_003",
            "catalog_id": "cat_003",
            "name": "Keyboard Lessons",
            "description": "Learn keyboard",
            "price_per_hour": 55,
            "instructor_id": "inst_003",
            "text_score": 0.70,
        },
    ]

    return repo


@pytest.fixture
def retriever(
    mock_db: Mock,
    mock_embedding_service: Mock,
    mock_repository: Mock,
) -> PostgresRetriever:
    """Create retriever with mocks."""
    return PostgresRetriever(
        db=mock_db,
        embedding_service=mock_embedding_service,
        repository=mock_repository,
    )


@pytest.fixture
def sample_parsed_query() -> ParsedQuery:
    """Create sample parsed query."""
    return ParsedQuery(
        original_query="piano lessons",
        service_query="piano lessons",
        parsing_mode="regex",
    )


class TestHybridSearch:
    """Tests for hybrid search functionality."""

    @pytest.mark.asyncio
    async def test_hybrid_search_combines_results(
        self,
        retriever: PostgresRetriever,
        sample_parsed_query: ParsedQuery,
    ) -> None:
        """Should return candidates from both vector and text search."""
        result = await retriever.search(sample_parsed_query)

        assert result.vector_search_used is True
        assert result.degraded is False
        assert len(result.candidates) == 3  # 2 vector + 2 text - 1 overlap

    @pytest.mark.asyncio
    async def test_service_in_both_gets_combined_score(
        self,
        retriever: PostgresRetriever,
        sample_parsed_query: ParsedQuery,
    ) -> None:
        """Services in both results should have combined score."""
        result = await retriever.search(sample_parsed_query)

        # Find the overlapping service (svc_001)
        overlap_candidate = next(
            c for c in result.candidates if c.service_id == "svc_001"
        )

        # Should have both scores
        assert overlap_candidate.vector_score is not None
        assert overlap_candidate.text_score is not None

        # Hybrid score should be weighted combination
        expected_hybrid = (VECTOR_WEIGHT * 0.95) + (TEXT_WEIGHT * 0.90)
        assert abs(overlap_candidate.hybrid_score - expected_hybrid) < 0.001

    @pytest.mark.asyncio
    async def test_vector_only_candidate_gets_penalty(
        self,
        retriever: PostgresRetriever,
        sample_parsed_query: ParsedQuery,
    ) -> None:
        """Services only in vector results should have penalty applied."""
        result = await retriever.search(sample_parsed_query)

        # Find vector-only service (svc_002)
        vector_only = next(c for c in result.candidates if c.service_id == "svc_002")

        assert vector_only.vector_score is not None
        assert vector_only.text_score is None

        expected_hybrid = 0.80 * SINGLE_SOURCE_PENALTY
        assert abs(vector_only.hybrid_score - expected_hybrid) < 0.001

    @pytest.mark.asyncio
    async def test_text_only_candidate_gets_penalty(
        self,
        retriever: PostgresRetriever,
        sample_parsed_query: ParsedQuery,
    ) -> None:
        """Services only in text results should have penalty applied."""
        result = await retriever.search(sample_parsed_query)

        # Find text-only service (svc_003)
        text_only = next(c for c in result.candidates if c.service_id == "svc_003")

        assert text_only.vector_score is None
        assert text_only.text_score is not None

        expected_hybrid = 0.70 * SINGLE_SOURCE_PENALTY
        assert abs(text_only.hybrid_score - expected_hybrid) < 0.001

    @pytest.mark.asyncio
    async def test_results_sorted_by_hybrid_score(
        self,
        retriever: PostgresRetriever,
        sample_parsed_query: ParsedQuery,
    ) -> None:
        """Results should be sorted by hybrid score descending."""
        result = await retriever.search(sample_parsed_query)

        scores = [c.hybrid_score for c in result.candidates]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_respects_top_k_limit(
        self,
        retriever: PostgresRetriever,
        sample_parsed_query: ParsedQuery,
    ) -> None:
        """Should respect the top_k limit."""
        result = await retriever.search(sample_parsed_query, top_k=2)

        assert len(result.candidates) <= 2

    @pytest.mark.asyncio
    async def test_calls_repository_methods(
        self,
        retriever: PostgresRetriever,
        sample_parsed_query: ParsedQuery,
        mock_repository: Mock,
    ) -> None:
        """Should call repository methods with correct parameters."""
        await retriever.search(sample_parsed_query)

        # Vector search called with embedding
        mock_repository.vector_search.assert_called_once()
        call_args = mock_repository.vector_search.call_args
        assert len(call_args[0][0]) == 1536  # embedding vector

        # Text search called with queries
        mock_repository.text_search.assert_called_once_with(
            "piano lessons", "piano lessons", 30
        )


class TestDegradedMode:
    """Tests for degraded (text-only) mode."""

    @pytest.mark.asyncio
    async def test_falls_back_to_text_only_when_no_embedding(
        self,
        mock_db: Mock,
        mock_repository: Mock,
    ) -> None:
        """Should use text-only search when embedding fails."""
        # Mock embedding service returns None
        embedding_service = Mock()
        embedding_service.embed_query = AsyncMock(return_value=None)

        retriever = PostgresRetriever(
            db=mock_db,
            embedding_service=embedding_service,
            repository=mock_repository,
        )

        result = await retriever.search(
            ParsedQuery(
                original_query="piano",
                service_query="piano",
                parsing_mode="regex",
            )
        )

        assert result.vector_search_used is False
        assert result.degraded is True
        assert result.degradation_reason == "embedding_service_unavailable"

    @pytest.mark.asyncio
    async def test_text_only_does_not_call_vector_search(
        self,
        mock_db: Mock,
        mock_repository: Mock,
    ) -> None:
        """Text-only mode should skip vector search."""
        embedding_service = Mock()
        embedding_service.embed_query = AsyncMock(return_value=None)

        retriever = PostgresRetriever(
            db=mock_db,
            embedding_service=embedding_service,
            repository=mock_repository,
        )

        await retriever.search(
            ParsedQuery(
                original_query="piano",
                service_query="piano",
                parsing_mode="regex",
            )
        )

        mock_repository.vector_search.assert_not_called()
        mock_repository.text_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_text_only_search_method(
        self,
        retriever: PostgresRetriever,
    ) -> None:
        """text_only_search should return results with text scores only."""
        result = await retriever.text_only_search(
            service_query="piano",
            original_query="piano",
            top_k=10,
        )

        assert result.degraded is True
        assert result.vector_search_used is False
        assert result.degradation_reason == "text_only_mode"
        assert len(result.candidates) > 0

        # All candidates should have text_score but no vector_score
        for c in result.candidates:
            assert c.text_score is not None
            assert c.vector_score is None

    @pytest.mark.asyncio
    async def test_text_only_applies_penalty(
        self,
        retriever: PostgresRetriever,
    ) -> None:
        """Text-only candidates should have penalty applied."""
        result = await retriever.text_only_search(
            service_query="piano",
            original_query="piano",
            top_k=10,
        )

        for c in result.candidates:
            expected = (c.text_score or 0) * SINGLE_SOURCE_PENALTY
            assert abs(c.hybrid_score - expected) < 0.001


class TestScoreFusion:
    """Tests for score fusion logic."""

    def test_fuse_empty_results(self, retriever: PostgresRetriever) -> None:
        """Should handle empty results gracefully."""
        candidates = retriever._fuse_scores({}, {}, 10)

        assert candidates == []

    def test_fuse_vector_only_results(self, retriever: PostgresRetriever) -> None:
        """Should handle vector-only results."""
        vector_results = {
            "svc_001": (
                0.9,
                {
                    "service_catalog_id": "cat_001",
                    "name": "Test",
                    "description": None,
                    "price_per_hour": 50,
                    "instructor_id": "i1",
                },
            )
        }

        candidates = retriever._fuse_scores(vector_results, {}, 10)

        assert len(candidates) == 1
        assert candidates[0].hybrid_score == 0.9 * SINGLE_SOURCE_PENALTY
        assert candidates[0].vector_score == 0.9
        assert candidates[0].text_score is None

    def test_fuse_text_only_results(self, retriever: PostgresRetriever) -> None:
        """Should handle text-only results."""
        text_results = {
            "svc_001": (
                0.8,
                {
                    "service_catalog_id": "cat_001",
                    "name": "Test",
                    "description": None,
                    "price_per_hour": 50,
                    "instructor_id": "i1",
                },
            )
        }

        candidates = retriever._fuse_scores({}, text_results, 10)

        assert len(candidates) == 1
        assert candidates[0].hybrid_score == 0.8 * SINGLE_SOURCE_PENALTY
        assert candidates[0].vector_score is None
        assert candidates[0].text_score == 0.8

    def test_fuse_overlapping_results(self, retriever: PostgresRetriever) -> None:
        """Should combine scores for overlapping results."""
        service_data = {
            "service_catalog_id": "cat_001",
            "name": "Test",
            "description": "A test",
            "price_per_hour": 60,
            "instructor_id": "i1",
        }
        vector_results = {"svc_001": (0.9, service_data)}
        text_results = {"svc_001": (0.8, service_data)}

        candidates = retriever._fuse_scores(vector_results, text_results, 10)

        assert len(candidates) == 1
        expected = (VECTOR_WEIGHT * 0.9) + (TEXT_WEIGHT * 0.8)
        assert abs(candidates[0].hybrid_score - expected) < 0.001
        assert candidates[0].vector_score == 0.9
        assert candidates[0].text_score == 0.8

    def test_fuse_respects_top_k(self, retriever: PostgresRetriever) -> None:
        """Should limit results to top_k."""
        results = {
            f"svc_{i}": (
                0.9 - i * 0.1,
                {
                    "service_catalog_id": f"cat_{i}",
                    "name": f"Test {i}",
                    "description": None,
                    "price_per_hour": 50,
                    "instructor_id": f"i{i}",
                },
            )
            for i in range(10)
        }

        candidates = retriever._fuse_scores(results, {}, 3)

        assert len(candidates) == 3
        # Should be top 3 by score
        assert candidates[0].hybrid_score > candidates[1].hybrid_score
        assert candidates[1].hybrid_score > candidates[2].hybrid_score


class TestServiceCandidate:
    """Tests for ServiceCandidate dataclass."""

    def test_candidate_creation(self) -> None:
        """Should create candidate with all fields."""
        candidate = ServiceCandidate(
            service_id="svc_001",
            service_catalog_id="cat_001",
            hybrid_score=0.85,
            vector_score=0.9,
            text_score=0.8,
            name="Piano Lessons",
            description="Learn piano",
            price_per_hour=50,
            instructor_id="inst_001",
        )

        assert candidate.service_id == "svc_001"
        assert candidate.hybrid_score == 0.85
        assert candidate.vector_score == 0.9
        assert candidate.text_score == 0.8
        assert candidate.name == "Piano Lessons"
        assert candidate.description == "Learn piano"
        assert candidate.price_per_hour == 50
        assert candidate.instructor_id == "inst_001"

    def test_candidate_with_none_scores(self) -> None:
        """Should allow None for optional scores."""
        candidate = ServiceCandidate(
            service_id="svc_001",
            service_catalog_id="cat_001",
            hybrid_score=0.72,
            vector_score=None,
            text_score=0.9,
            name="Piano Lessons",
            description=None,
            price_per_hour=50,
            instructor_id="inst_001",
        )

        assert candidate.vector_score is None
        assert candidate.text_score == 0.9
        assert candidate.description is None


class TestRetrievalResult:
    """Tests for RetrievalResult dataclass."""

    def test_result_creation(self) -> None:
        """Should create result with all fields."""
        candidates = [
            ServiceCandidate(
                service_id="svc_001",
                service_catalog_id="cat_001",
                hybrid_score=0.9,
                vector_score=0.9,
                text_score=0.8,
                name="Test",
                description=None,
                price_per_hour=50,
                instructor_id="i1",
            )
        ]

        result = RetrievalResult(
            candidates=candidates,
            total_candidates=1,
            vector_search_used=True,
            degraded=False,
            degradation_reason=None,
        )

        assert len(result.candidates) == 1
        assert result.total_candidates == 1
        assert result.vector_search_used is True
        assert result.degraded is False
        assert result.degradation_reason is None

    def test_degraded_result(self) -> None:
        """Should create degraded result correctly."""
        result = RetrievalResult(
            candidates=[],
            total_candidates=0,
            vector_search_used=False,
            degraded=True,
            degradation_reason="embedding_service_unavailable",
        )

        assert result.degraded is True
        assert result.degradation_reason == "embedding_service_unavailable"
        assert result.vector_search_used is False


class TestRetrieverConstants:
    """Tests for retriever constants."""

    def test_weight_sum(self) -> None:
        """Vector and text weights should sum to 1.0."""
        assert VECTOR_WEIGHT + TEXT_WEIGHT == 1.0

    def test_penalty_less_than_one(self) -> None:
        """Single source penalty should be less than 1.0."""
        assert 0 < SINGLE_SOURCE_PENALTY < 1.0

    def test_max_candidates_reasonable(self) -> None:
        """Max candidates should be reasonable."""
        assert 10 <= MAX_CANDIDATES <= 100
