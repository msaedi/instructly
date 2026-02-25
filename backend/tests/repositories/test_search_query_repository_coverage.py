from __future__ import annotations

import json

from sqlalchemy.exc import SQLAlchemyError

from app.models.nl_search import SearchQuery
from app.repositories.search_query_repository import SearchQueryRepository


def _create_search_query(db, *, normalized_query):
    row = SearchQuery(
        original_query="Piano lessons",
        normalized_query=normalized_query,
        parsing_mode="regex",
        parsing_latency_ms=10,
        result_count=2,
        total_latency_ms=20,
    )
    db.add(row)
    db.commit()
    return row


def test_get_normalized_query_variants(db):
    repo = SearchQueryRepository(db)

    row = _create_search_query(db, normalized_query={"category": "music"})
    assert repo.get_normalized_query(row.id) == {"category": "music"}

    row = _create_search_query(db, normalized_query=json.dumps({"category": "tutoring"}))
    assert repo.get_normalized_query(row.id) == {"category": "tutoring"}

    row = _create_search_query(db, normalized_query=json.dumps(["bad"]))
    assert repo.get_normalized_query(row.id) is None

    row = _create_search_query(db, normalized_query="not-json")
    assert repo.get_normalized_query(row.id) is None

    assert repo.get_normalized_query("missing") is None


def test_get_normalized_query_handles_errors(db, monkeypatch):
    repo = SearchQueryRepository(db)

    def _raise(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(repo.db, "get", _raise)
    assert repo.get_normalized_query("any") is None


def test_get_normalized_query_rollback_error(db, monkeypatch):
    """L44-45: db.rollback() raises inside the except block – should not propagate."""
    from unittest.mock import MagicMock

    mock_db = MagicMock()
    repo = SearchQueryRepository(mock_db)

    mock_db.get.side_effect = SQLAlchemyError("db error")
    mock_db.rollback.side_effect = RuntimeError("rollback failed")

    assert repo.get_normalized_query("any-id") is None


def test_get_normalized_query_none_payload(db):
    """When normalized_query is None, should return None."""
    repo = SearchQueryRepository(db)
    row = _create_search_query(db, normalized_query=None)
    assert repo.get_normalized_query(row.id) is None
