from __future__ import annotations

import secrets
from types import SimpleNamespace
from typing import Any

from app.models.location_alias import LocationAlias
from app.models.region_boundary import RegionBoundary
from app.repositories.location_resolution_repository import LocationResolutionRepository


def _make_region(db, *, name: str, code: str, parent: str = "Manhattan") -> RegionBoundary:
    region = RegionBoundary(
        region_type="nyc",
        region_code=code,
        region_name=name,
        parent_region=parent,
        region_metadata={"borough": parent},
    )
    db.add(region)
    db.commit()
    db.refresh(region)
    return region


def _unique_code(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(2)}"

def _unique_name(prefix: str) -> str:
    return f"{prefix} {secrets.token_hex(2)}"


def test_region_and_alias_lookups(db, unique_nyc_region_code) -> None:
    region_name = _unique_name("Manhattan - Midtown")
    region = _make_region(
        db,
        name=region_name,
        code=unique_nyc_region_code,
    )

    repo = LocationResolutionRepository(db)

    exact = repo.find_exact_region_by_name(region_name.lower())
    assert exact is not None
    assert exact.id == region.id

    assert repo.get_region_by_id(region.id) is not None
    assert repo.get_regions_by_ids([region.id, "missing"]) and repo.get_regions_by_ids([region.id])[0].id == region.id

    names = repo.list_region_names()
    assert region.region_name in names
    regions = repo.list_regions(limit=1000)
    assert any(r.id == region.id for r in regions)

    fragment_matches = repo.find_regions_by_name_fragment(region_name.split()[-1].lower())
    assert any(r.id == region.id for r in fragment_matches)

    alias = LocationAlias(
        alias_normalized=region_name.lower(),
        region_boundary_id=region.id,
        status="active",
        confidence=0.95,
        user_count=2,
        source="manual",
    )
    db.add(alias)
    db.commit()

    trusted = repo.find_trusted_alias(region_name.lower())
    assert trusted is not None
    assert trusted.id == alias.id

    cached = repo.find_cached_alias(region_name.lower(), source="manual")
    assert cached is not None

    repo.increment_alias_user_count(alias)
    db.refresh(alias)
    assert alias.user_count >= 3


def test_fuzzy_and_embedding_paths(db) -> None:
    region_name = _unique_name("Brooklyn - Williamsburg")
    region = _make_region(
        db,
        name=region_name,
        code=_unique_code("BK-WIL"),
        parent="Brooklyn",
    )

    repo = LocationResolutionRepository(db)

    # Fuzzy match paths (pg_trgm may be unavailable; accept empty results).
    fuzzy_region, similarity = repo.find_best_fuzzy_region(region_name.lower(), threshold=0.1)
    if fuzzy_region is not None:
        assert fuzzy_region.id == region.id
        assert similarity > 0
    else:
        assert similarity == 0.0

    best_score = repo.get_best_fuzzy_score(region_name.lower())
    assert best_score >= 0.0

    fuzzy_names = repo.list_fuzzy_region_names(region_name.lower(), limit=3)
    if fuzzy_names:
        assert any(region_name in name for name in fuzzy_names)

    # Embedding paths (pgvector expected in test DB).
    embedding = [0.01] * 1536
    region.name_embedding = embedding
    db.commit()

    assert repo.has_region_name_embeddings() is True

    pairs: list[tuple[Any, float]] = repo.find_regions_by_name_embedding(embedding, limit=100)
    if pairs:
        assert any(pair_region.id == region.id for pair_region, _ in pairs)
        assert all(sim >= 0.0 for _, sim in pairs)


def test_get_regions_by_ids_empty_returns_empty(db) -> None:
    repo = LocationResolutionRepository(db)
    assert repo.get_regions_by_ids([]) == []


def test_list_fuzzy_region_names_blank_query(db) -> None:
    repo = LocationResolutionRepository(db)
    assert repo.list_fuzzy_region_names("   ") == []


def test_find_regions_by_name_fragment_blank_query(db) -> None:
    repo = LocationResolutionRepository(db)
    assert repo.find_regions_by_name_fragment("   ") == []


def test_find_best_fuzzy_region_no_row(monkeypatch, db) -> None:
    repo = LocationResolutionRepository(db)

    class _Result:
        def first(self):
            return None

    monkeypatch.setattr(repo.db, "execute", lambda *args, **kwargs: _Result())
    region, similarity = repo.find_best_fuzzy_region("nope", threshold=0.5)
    assert region is None
    assert similarity == 0.0


def test_find_best_fuzzy_region_missing_region(monkeypatch, db) -> None:
    repo = LocationResolutionRepository(db)
    row = SimpleNamespace(id="missing-id", sim=0.9)

    class _Result:
        def first(self):
            return row

    monkeypatch.setattr(repo.db, "execute", lambda *args, **kwargs: _Result())
    monkeypatch.setattr(repo, "get_region_by_id", lambda *_args, **_kwargs: None)
    region, similarity = repo.find_best_fuzzy_region("missing", threshold=0.1)
    assert region is None
    assert similarity == 0.0


def test_list_fuzzy_region_names_handles_bad_rows(monkeypatch, db) -> None:
    repo = LocationResolutionRepository(db)

    class BadRow:
        def __bool__(self):
            return True

        def __getitem__(self, _idx):
            raise IndexError("boom")

    class _Result:
        def fetchall(self):
            return [BadRow()]

    monkeypatch.setattr(repo.db, "execute", lambda *args, **kwargs: _Result())
    assert repo.list_fuzzy_region_names("bad-row") == []


def test_find_regions_by_name_embedding_edge_cases(monkeypatch, db) -> None:
    repo = LocationResolutionRepository(db)

    assert repo.find_regions_by_name_embedding([]) == []

    class _EmptyResult:
        def fetchall(self):
            return []

    monkeypatch.setattr(repo.db, "execute", lambda *args, **kwargs: _EmptyResult())
    assert repo.find_regions_by_name_embedding([0.1, 0.2]) == []

    class _Row:
        def __init__(self, row_id, similarity):
            self.id = row_id
            self.similarity = similarity

    rows = [_Row("missing-id", 0.5), _Row("valid-id", "bad")]

    class _RowsResult:
        def fetchall(self):
            return rows

    region = RegionBoundary(region_type="nyc", region_code="TEST", region_name="Astoria")
    region.id = "valid-id"

    monkeypatch.setattr(repo.db, "execute", lambda *args, **kwargs: _RowsResult())
    monkeypatch.setattr(repo, "get_regions_by_ids", lambda _ids: [region])
    pairs = repo.find_regions_by_name_embedding([0.1, 0.2], limit=5)
    assert len(pairs) == 1
    assert pairs[0][0].id == "valid-id"
    assert pairs[0][1] == 0.0


def test_repository_error_handling_paths() -> None:
    class FailingSession:
        def query(self, *args, **kwargs):
            raise RuntimeError("query failed")

        def execute(self, *args, **kwargs):
            raise RuntimeError("execute failed")

        def flush(self):
            raise RuntimeError("flush failed")

        def rollback(self):
            raise RuntimeError("rollback failed")

    repo = LocationResolutionRepository(FailingSession())
    alias = LocationAlias(alias_normalized="fail")

    assert repo.find_exact_region_by_name("fail") is None
    assert repo.find_trusted_alias("fail") is None
    assert repo.find_cached_alias("fail") is None
    repo.increment_alias_user_count(alias)
    assert repo.get_region_by_id("missing") is None
    assert repo.get_regions_by_ids(["missing"]) == []
    assert repo.list_regions(limit=1) == []
    assert repo.find_best_fuzzy_region("fail", threshold=0.1) == (None, 0.0)
    assert repo.get_best_fuzzy_score("fail") == 0.0
    assert repo.list_fuzzy_region_names("fail") == []
    assert repo.find_regions_by_name_fragment("fail") == []
    assert repo.list_region_names() == []
    assert repo.has_region_name_embeddings() is False
    assert repo.find_regions_by_name_embedding([0.1, 0.2]) == []
