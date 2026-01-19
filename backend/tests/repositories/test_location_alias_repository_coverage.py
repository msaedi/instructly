from __future__ import annotations

import secrets

from app.models.location_alias import LocationAlias
from app.repositories.location_alias_repository import LocationAliasRepository


def _unique_alias(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(4)}"


def test_add_get_update_and_list_location_alias(db) -> None:
    repo = LocationAliasRepository(db)
    alias_value = _unique_alias("ues")
    alias = LocationAlias(
        alias_normalized=alias_value,
        status="active",
        source="manual",
        confidence=0.95,
        user_count=2,
    )

    assert repo.add(alias) is True

    fetched = repo.get_by_id(alias.id)
    assert fetched is not None
    assert fetched.alias_normalized == alias_value

    assert repo.update_status(alias.id, "deprecated") is True
    db.refresh(alias)
    assert alias.status == "deprecated"

    assert repo.update_status("missing-id", "active") is False

    # Add a second alias to exercise list filtering.
    alias_value_2 = _unique_alias("soho")
    alias_2 = LocationAlias(
        alias_normalized=alias_value_2,
        status="active",
        source="llm",
        confidence=1.0,
        user_count=1,
    )
    assert repo.add(alias_2) is True

    results = repo.list_by_source_and_status(source="llm", status="active", limit=10)
    assert any(row.id == alias_2.id for row in results)


def test_add_duplicate_alias_returns_false(db) -> None:
    repo = LocationAliasRepository(db)
    alias_value = _unique_alias("dup")
    alias = LocationAlias(alias_normalized=alias_value)
    assert repo.add(alias) is True

    duplicate = LocationAlias(alias_normalized=alias_value)
    assert repo.add(duplicate) is False


def test_repository_error_paths() -> None:
    class FailingSession:
        def add(self, _alias):
            return None

        def flush(self):
            raise RuntimeError("flush failed")

        def rollback(self):
            raise RuntimeError("rollback failed")

        def get(self, _model, _alias_id):
            raise RuntimeError("get failed")

        def query(self, _model):
            raise RuntimeError("query failed")

    repo = LocationAliasRepository(FailingSession())
    alias = LocationAlias(alias_normalized=_unique_alias("bad"))

    assert repo.add(alias) is False
    assert repo.get_by_id("missing") is None

    # Force update_status failure after get_by_id succeeds.
    ok_session = FailingSession()
    repo_ok = LocationAliasRepository(ok_session)
    repo_ok.get_by_id = lambda _alias_id: alias
    assert repo_ok.update_status("alias-id", "active") is False
    assert repo_ok.list_by_source_and_status(source="manual", status="active") == []
