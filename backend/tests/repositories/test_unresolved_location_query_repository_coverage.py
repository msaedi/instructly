from __future__ import annotations

from app.core.ulid_helper import generate_ulid
from app.models.unresolved_location_query import UnresolvedLocationQuery
from app.repositories.unresolved_location_query_repository import (
    UnresolvedLocationQueryRepository,
)
from tests.conftest import _ensure_region_boundary


def _safe_rollback(db, called=None):
    original = db.rollback

    def _wrapped():
        if called is not None:
            called["called"] = True
        return original()

    return _wrapped


def _raise_rollback(called=None):
    def _wrapped():
        if called is not None:
            called["called"] = True
        raise RuntimeError("rollback failed")

    return _wrapped


def test_track_unresolved_creates_and_updates(db):
    repo = UnresolvedLocationQueryRepository(db)
    query = f"unknown-{generate_ulid().lower()}"

    repo.track_unresolved(query, original_query="Unknown Place")
    db.commit()

    row = repo.get_by_normalized(query)
    assert row is not None
    assert row.search_count == 1
    assert row.unique_user_count == 1
    assert row.sample_original_queries == ["Unknown Place"]

    repo.track_unresolved(query, original_query="Another")
    db.commit()

    row = repo.get_by_normalized(query)
    assert row.search_count == 2
    assert "Another" in row.sample_original_queries


def test_record_click_updates_counts(db):
    repo = UnresolvedLocationQueryRepository(db)
    query = f"click-{generate_ulid().lower()}"
    region = _ensure_region_boundary(db, "Manhattan")

    repo.record_click(
        query, region_boundary_id=str(region.id), original_query="Click Here"
    )
    db.commit()

    row = repo.get_by_normalized(query)
    assert row is not None
    assert row.click_count == 1
    assert row.click_region_counts[str(region.id)] == 1


def test_list_pending_and_evidence(db):
    repo = UnresolvedLocationQueryRepository(db)
    query = f"pending-{generate_ulid().lower()}"
    row = UnresolvedLocationQuery(
        id=generate_ulid(),
        city_id=repo.city_id,
        query_normalized=query,
        sample_original_queries=["Pending"],
        search_count=5,
        unique_user_count=5,
        click_count=2,
        status="pending",
    )
    db.add(row)
    db.commit()

    pending = repo.list_pending(limit=10)
    assert any(r.id == row.id for r in pending)

    evidence = repo.list_pending_with_evidence(min_clicks=1, min_searches=1, limit=10)
    assert any(r.id == row.id for r in evidence)


def test_set_status_and_mark_resolved(db):
    repo = UnresolvedLocationQueryRepository(db)
    query = f"status-{generate_ulid().lower()}"
    region = _ensure_region_boundary(db, "Brooklyn")
    repo.track_unresolved(query)
    db.commit()

    assert repo.set_status(query, status="manual_review") is True
    row = repo.get_by_normalized(query)
    assert row.status == "manual_review"

    assert repo.mark_resolved(query, region_boundary_id=str(region.id)) is True
    row = repo.get_by_normalized(query)
    assert row.reviewed is True
    assert row.resolved_region_boundary_id == str(region.id)

    assert repo.set_status("missing", status="x") is False


def test_track_unresolved_ignores_blank_and_manual_review(db):
    repo = UnresolvedLocationQueryRepository(db)
    repo.track_unresolved("")
    assert repo.get_by_normalized("") is None

    row = UnresolvedLocationQuery(
        id=generate_ulid(),
        city_id=repo.city_id,
        query_normalized=f"manual-{generate_ulid()}",
        sample_original_queries=["Manual"],
        search_count=1,
        unique_user_count=1,
        status="pending",
    )
    db.add(row)
    db.commit()

    repo.mark_manual_review(row)
    db.commit()
    assert row.status == "manual_review"


def test_record_click_ignores_missing_inputs(db):
    repo = UnresolvedLocationQueryRepository(db)
    query = f"ignore-{generate_ulid().lower()}"

    repo.record_click("", region_boundary_id="x")
    repo.record_click(query, region_boundary_id="")

    assert repo.get_by_normalized(query) is None


def test_track_unresolved_handles_errors(db, monkeypatch):
    repo = UnresolvedLocationQueryRepository(db)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo.db, "query", _raise)
    repo.track_unresolved("oops", original_query="Oops")


def test_record_click_handles_errors(db, monkeypatch):
    repo = UnresolvedLocationQueryRepository(db)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo.db, "query", _raise)
    repo.record_click("oops", region_boundary_id="region")


def test_record_click_appends_samples(db):
    repo = UnresolvedLocationQueryRepository(db)
    query = f"samples-{generate_ulid().lower()}"
    region = _ensure_region_boundary(db, "Queens")

    repo.record_click(query, region_boundary_id=str(region.id), original_query="First")
    repo.record_click(query, region_boundary_id=str(region.id), original_query="Second")
    db.commit()

    row = repo.get_by_normalized(query)
    assert row is not None
    assert "Second" in row.sample_original_queries


def test_list_pending_error_rolls_back(db, monkeypatch):
    repo = UnresolvedLocationQueryRepository(db)
    rolled_back = {"called": False}

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo.db, "query", _raise)
    monkeypatch.setattr(repo.db, "rollback", _safe_rollback(repo.db, rolled_back))
    assert repo.list_pending(limit=5) == []
    assert rolled_back["called"] is True


def test_get_by_normalized_error_rolls_back(db, monkeypatch):
    repo = UnresolvedLocationQueryRepository(db)
    rolled_back = {"called": False}

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo.db, "query", _raise)
    monkeypatch.setattr(repo.db, "rollback", _safe_rollback(repo.db, rolled_back))
    assert repo.get_by_normalized("oops") is None
    assert rolled_back["called"] is True


def test_list_pending_with_evidence_error_rolls_back(db, monkeypatch):
    repo = UnresolvedLocationQueryRepository(db)
    rolled_back = {"called": False}

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo.db, "query", _raise)
    monkeypatch.setattr(repo.db, "rollback", _safe_rollback(repo.db, rolled_back))
    assert repo.list_pending_with_evidence(min_clicks=1, min_searches=1, limit=5) == []
    assert rolled_back["called"] is True


def test_mark_manual_review_error_rolls_back(db, monkeypatch):
    repo = UnresolvedLocationQueryRepository(db)
    row = UnresolvedLocationQuery(
        id=generate_ulid(),
        city_id=repo.city_id,
        query_normalized=f"manual-{generate_ulid()}",
        sample_original_queries=["Manual"],
        search_count=1,
        unique_user_count=1,
        status="pending",
    )
    db.add(row)
    db.commit()

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo.db, "flush", _raise)
    monkeypatch.setattr(repo.db, "rollback", _safe_rollback(repo.db))
    repo.mark_manual_review(row)


def test_set_status_error_returns_false(db, monkeypatch):
    repo = UnresolvedLocationQueryRepository(db)
    query = f"status-fail-{generate_ulid().lower()}"
    repo.track_unresolved(query)
    db.commit()

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo.db, "flush", _raise)
    monkeypatch.setattr(repo.db, "rollback", _safe_rollback(repo.db))
    assert repo.set_status(query, status="manual_review") is False


def test_mark_resolved_missing_row_returns_false(db):
    repo = UnresolvedLocationQueryRepository(db)
    assert repo.mark_resolved("missing") is False


def test_mark_resolved_error_returns_false(db, monkeypatch):
    repo = UnresolvedLocationQueryRepository(db)
    query = f"resolve-fail-{generate_ulid().lower()}"
    repo.track_unresolved(query)
    db.commit()

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo.db, "flush", _raise)
    monkeypatch.setattr(repo.db, "rollback", _safe_rollback(repo.db))
    assert repo.mark_resolved(query, region_boundary_id="region") is False


def test_track_unresolved_rollback_failure(db, monkeypatch):
    repo = UnresolvedLocationQueryRepository(db)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo.db, "query", _raise)
    monkeypatch.setattr(repo.db, "rollback", _safe_rollback(repo.db))
    repo.track_unresolved("oops", original_query="Oops")


def test_record_click_rollback_failure(db, monkeypatch):
    repo = UnresolvedLocationQueryRepository(db)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo.db, "query", _raise)
    monkeypatch.setattr(repo.db, "rollback", _safe_rollback(repo.db))
    repo.record_click("oops", region_boundary_id="region")


def test_track_unresolved_does_not_append_when_sample_limit_reached(db):
    repo = UnresolvedLocationQueryRepository(db)
    query = f"limit-{generate_ulid().lower()}"

    repo.track_unresolved(query, original_query="First", max_samples=1)
    repo.track_unresolved(query, original_query="Second", max_samples=1)
    db.commit()

    row = repo.get_by_normalized(query)
    assert row is not None
    assert row.search_count == 2
    assert row.sample_original_queries == ["First"]


def test_track_unresolved_updates_counts_without_original_query(db):
    repo = UnresolvedLocationQueryRepository(db)
    query = f"counts-{generate_ulid().lower()}"

    repo.track_unresolved(query, original_query="Seed")
    repo.track_unresolved(query, original_query=None)
    db.commit()

    row = repo.get_by_normalized(query)
    assert row is not None
    assert row.search_count == 2
    assert row.unique_user_count == 2
    assert row.sample_original_queries == ["Seed"]


def test_record_click_without_original_query_preserves_samples(db):
    repo = UnresolvedLocationQueryRepository(db)
    query = f"click-nosample-{generate_ulid().lower()}"
    region = _ensure_region_boundary(db, "Bronx")

    repo.record_click(query, region_boundary_id=str(region.id), original_query="First")
    repo.record_click(query, region_boundary_id=str(region.id), original_query=None)
    db.commit()

    row = repo.get_by_normalized(query)
    assert row is not None
    assert row.click_count == 2
    assert row.sample_original_queries == ["First"]


def test_mark_resolved_without_region_still_marks_reviewed(db):
    repo = UnresolvedLocationQueryRepository(db)
    query = f"resolved-noregion-{generate_ulid().lower()}"
    repo.track_unresolved(query, original_query="X")
    db.commit()

    assert repo.mark_resolved(query, region_boundary_id=None) is True
    row = repo.get_by_normalized(query)
    assert row is not None
    assert row.reviewed is True
    assert row.resolved_region_boundary_id is None


def test_track_unresolved_ignores_rollback_failure():
    class _DB:
        def query(self, *_args, **_kwargs):
            raise RuntimeError("boom")

        def rollback(self):
            raise RuntimeError("rollback failed")

    repo = UnresolvedLocationQueryRepository(_DB())  # type: ignore[arg-type]
    repo.track_unresolved("oops", original_query="Oops")


def test_record_click_ignores_rollback_failure():
    class _DB:
        def query(self, *_args, **_kwargs):
            raise RuntimeError("boom")

        def rollback(self):
            raise RuntimeError("rollback failed")

    repo = UnresolvedLocationQueryRepository(_DB())  # type: ignore[arg-type]
    repo.record_click("oops", region_boundary_id="region")


def test_list_pending_ignores_rollback_failure():
    class _DB:
        def query(self, *_args, **_kwargs):
            raise RuntimeError("boom")

        def rollback(self):
            raise RuntimeError("rollback failed")

    repo = UnresolvedLocationQueryRepository(_DB())  # type: ignore[arg-type]
    assert repo.list_pending(limit=5) == []


def test_get_by_normalized_ignores_rollback_failure():
    class _DB:
        def query(self, *_args, **_kwargs):
            raise RuntimeError("boom")

        def rollback(self):
            raise RuntimeError("rollback failed")

    repo = UnresolvedLocationQueryRepository(_DB())  # type: ignore[arg-type]
    assert repo.get_by_normalized("oops") is None


def test_list_pending_with_evidence_ignores_rollback_failure():
    class _DB:
        def query(self, *_args, **_kwargs):
            raise RuntimeError("boom")

        def rollback(self):
            raise RuntimeError("rollback failed")

    repo = UnresolvedLocationQueryRepository(_DB())  # type: ignore[arg-type]
    assert repo.list_pending_with_evidence(min_clicks=1, min_searches=1, limit=5) == []


def test_mark_manual_review_ignores_rollback_failure():
    class _DB:
        def flush(self):
            raise RuntimeError("boom")

        def rollback(self):
            raise RuntimeError("rollback failed")

    repo = UnresolvedLocationQueryRepository(_DB())  # type: ignore[arg-type]
    row = UnresolvedLocationQuery(
        id=generate_ulid(),
        city_id=repo.city_id,
        query_normalized=f"manual-fail-{generate_ulid()}",
        sample_original_queries=["Manual"],
        search_count=1,
        unique_user_count=1,
        status="pending",
    )
    repo.mark_manual_review(row)


def test_set_status_ignores_rollback_failure(monkeypatch):
    class _DB:
        def flush(self):
            raise RuntimeError("boom")

        def rollback(self):
            raise RuntimeError("rollback failed")

    repo = UnresolvedLocationQueryRepository(_DB())  # type: ignore[arg-type]
    row = UnresolvedLocationQuery(
        id=generate_ulid(),
        city_id=repo.city_id,
        query_normalized="normalized",
        sample_original_queries=[],
        search_count=1,
        unique_user_count=1,
        status="pending",
    )
    monkeypatch.setattr(repo, "get_by_normalized", lambda _q: row)
    assert repo.set_status("normalized", status="manual_review") is False


def test_mark_resolved_ignores_rollback_failure(monkeypatch):
    class _DB:
        def flush(self):
            raise RuntimeError("boom")

        def rollback(self):
            raise RuntimeError("rollback failed")

    repo = UnresolvedLocationQueryRepository(_DB())  # type: ignore[arg-type]
    row = UnresolvedLocationQuery(
        id=generate_ulid(),
        city_id=repo.city_id,
        query_normalized="normalized",
        sample_original_queries=[],
        search_count=1,
        unique_user_count=1,
        status="pending",
    )
    monkeypatch.setattr(repo, "get_by_normalized", lambda _q: row)
    assert repo.mark_resolved("normalized", region_boundary_id="region") is False
