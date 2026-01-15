from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from app.models.user import User
from app.repositories.retention_repository import RetentionRepository


class TestRetentionRepositoryCoverage:
    def test_has_table_returns_false_when_inspector_missing(self, db) -> None:
        repo = RetentionRepository(db)
        repo._inspector = None

        assert repo.has_table("users") is False

    def test_has_table_handles_inspector_error(self, db) -> None:
        repo = RetentionRepository(db)

        class BrokenInspector:
            def has_table(self, _table_name: str) -> bool:
                raise SQLAlchemyError("boom")

        repo._inspector = BrokenInspector()

        assert repo.has_table("users") is False

    def test_reflect_table_returns_none_when_bind_missing(self, db) -> None:
        repo = RetentionRepository(db)
        repo._bind = None

        assert repo.reflect_table("users") is None

    def test_reflect_table_returns_none_on_missing_table(self, db) -> None:
        repo = RetentionRepository(db)

        assert repo.reflect_table("table_does_not_exist") is None

    def test_delete_rows_returns_len_when_rowcount_none(self, db, monkeypatch) -> None:
        repo = RetentionRepository(db)

        class DummyResult:
            rowcount = None

        def fake_execute(_stmt):
            return DummyResult()

        monkeypatch.setattr(repo.db, "execute", fake_execute)

        result = repo.delete_rows(User.__table__, User.__table__.c.id, ["a", "b", "c"])

        assert result == 3
