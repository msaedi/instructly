from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.search.query_parser import ParsedQuery
import app.services.search.retriever as retriever_module
from app.services.search.retriever import PostgresRetriever


def _parsed_query(query: str = "piano lessons") -> ParsedQuery:
    return ParsedQuery(
        original_query=query,
        service_query=query,
        parsing_mode="regex",
    )


@pytest.mark.asyncio
async def test_run_db_uses_session_when_no_override(monkeypatch) -> None:
    embedding_service = Mock()
    retriever = PostgresRetriever(embedding_service=embedding_service, repository=None)

    repo = Mock()

    @contextmanager
    def fake_session():
        yield "db"

    monkeypatch.setattr(retriever_module, "get_db_session", lambda: fake_session())
    monkeypatch.setattr(retriever_module, "RetrieverRepository", lambda db: repo)

    result = await retriever._run_db(lambda r: r)

    assert result is repo


@pytest.mark.asyncio
async def test_search_skips_vector_when_text_strong(monkeypatch) -> None:
    embedding_service = Mock()
    embedding_service.embed_query = AsyncMock(return_value=[0.1])

    repo = Mock()
    repo.text_search.return_value = [
        {
            "id": "svc_1",
            "catalog_id": "cat_1",
            "name": "Piano",
            "description": "",
            "price_per_hour": 50,
            "instructor_id": "inst_1",
            "text_score": 0.95,
        }
    ]

    retriever = PostgresRetriever(embedding_service=embedding_service, repository=repo)

    monkeypatch.setattr(retriever_module, "TEXT_SKIP_VECTOR_MIN_RESULTS", 1)
    monkeypatch.setattr(retriever_module, "TEXT_SKIP_VECTOR_SCORE_THRESHOLD", 0.5)

    result = await retriever.search(_parsed_query())

    assert result.vector_search_used is False
    assert result.degraded is False


@pytest.mark.asyncio
async def test_search_no_embeddings_falls_back_to_text(monkeypatch) -> None:
    embedding_service = Mock()
    embedding_service.embed_query = AsyncMock(return_value=[0.1])

    repo = Mock()
    repo.text_search.return_value = []
    repo.has_embeddings.return_value = False

    retriever = PostgresRetriever(embedding_service=embedding_service, repository=repo)

    monkeypatch.setattr(retriever_module, "TEXT_SKIP_VECTOR_MIN_RESULTS", 99)
    monkeypatch.setattr(retriever_module, "TEXT_SKIP_VECTOR_SCORE_THRESHOLD", 0.99)

    result = await retriever.search(_parsed_query())

    assert result.degraded is True
    assert result.degradation_reason == "no_embeddings_in_database"


@pytest.mark.asyncio
async def test_search_embedding_timeout(monkeypatch) -> None:
    embedding_service = Mock()
    embedding_service.embed_query = AsyncMock(side_effect=asyncio.TimeoutError())

    repo = Mock()
    repo.text_search.return_value = []
    repo.has_embeddings.return_value = True

    retriever = PostgresRetriever(embedding_service=embedding_service, repository=repo)

    monkeypatch.setattr(retriever_module, "TEXT_SKIP_VECTOR_MIN_RESULTS", 99)
    monkeypatch.setattr(retriever_module, "TEXT_SKIP_VECTOR_SCORE_THRESHOLD", 0.99)
    monkeypatch.setattr(retriever_module, "EMBEDDING_SOFT_TIMEOUT_MS", 0)
    monkeypatch.setattr(
        retriever_module,
        "get_search_config",
        lambda: SimpleNamespace(embedding_timeout_ms=1),
    )

    result = await retriever.search(_parsed_query())

    assert result.degraded is True
    assert result.degradation_reason == "embedding_timeout"


def test_vector_search_repo_wrapper() -> None:
    embedding_service = Mock()
    retriever = PostgresRetriever(embedding_service=embedding_service, repository=None)

    repo = Mock()
    repo.vector_search.return_value = [
        {
            "id": "svc_1",
            "catalog_id": "cat_1",
            "name": "Piano",
            "description": "",
            "price_per_hour": 50,
            "instructor_id": "inst_1",
            "vector_score": 0.9,
        }
    ]

    result = retriever.vector_search_repo(repo, [0.1], 5)
    assert "svc_1" in result


def test_text_search_repo_wrapper() -> None:
    embedding_service = Mock()
    retriever = PostgresRetriever(embedding_service=embedding_service, repository=None)

    repo = Mock()
    repo.text_search.return_value = [
        {
            "id": "svc_1",
            "catalog_id": "cat_1",
            "name": "Piano",
            "description": "",
            "price_per_hour": 50,
            "instructor_id": "inst_1",
            "text_score": 0.9,
        }
    ]

    result = retriever.text_search_repo(repo, "piano", "piano", 5)
    assert "svc_1" in result


def test_normalize_query_for_trigram_empty() -> None:
    assert retriever_module.PostgresRetriever._normalize_query_for_trigram("") == ""


def test_fuse_scores_skips_bad_entries() -> None:
    embedding_service = Mock()
    retriever = PostgresRetriever(embedding_service=embedding_service, repository=None)

    result = retriever._fuse_scores({"svc": None}, {}, 5)
    assert result == []
