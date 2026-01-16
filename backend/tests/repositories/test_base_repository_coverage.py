from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.exceptions import RepositoryException
from app.models.user import User
from app.repositories.base_repository import BaseRepository


def _user_payload(suffix: str) -> dict:
    return {
        "email": f"base-repo-{suffix}@example.com",
        "hashed_password": "x",
        "first_name": "Base",
        "last_name": "Repo",
        "zip_code": "10001",
    }


class TestBaseRepositoryCoverage:
    def test_crud_helpers(self, db):
        repo = BaseRepository(db, User)

        created = repo.create(**_user_payload("create"))
        repo.refresh(created)

        fetched = repo.get_by_id(created.id)
        assert fetched is not None

        fetched_no_rel = repo.get_by_id(created.id, load_relationships=False)
        assert fetched_no_rel is not None

        assert repo.exists(email=created.email) is True
        assert repo.count(email=created.email) == 1
        assert repo.find_by(email=created.email)
        assert repo.find_one_by(email=created.email) is not None

        updated = repo.update(created.id, first_name="Updated")
        assert updated is not None
        assert updated.first_name == "Updated"

        all_rows = repo.get_all(skip=0, limit=10)
        assert any(row.id == created.id for row in all_rows)

        assert repo.delete(created.id) is True
        assert repo.delete(created.id) is False

    def test_bulk_create_and_update(self, db):
        repo = BaseRepository(db, User)

        batch = [
            _user_payload("bulk-1"),
            _user_payload("bulk-2"),
        ]
        created = repo.bulk_create(batch)
        assert len(created) == 2

        updates = [
            {"id": created[0].id, "last_name": "Bulked"},
            {"id": created[1].id, "last_name": "Bulked"},
        ]
        updated_count = repo.bulk_update(updates)
        assert updated_count == 2

        assert repo.bulk_update([]) == 0
        assert repo.bulk_update([{"name": "missing"}]) == 0

    def test_transaction_and_execute_helpers(self, db):
        repo = BaseRepository(db, User)

        with repo.transaction():
            repo.create(created_at=datetime.now(timezone.utc), **_user_payload("txn"))

        assert repo.exists(email="base-repo-txn@example.com") is True

        query = repo._build_query().filter(User.email.like("base-repo-%"))
        rows = repo._execute_query(query)
        assert rows

        scalar_query = db.query(func.count(User.id))
        count = repo._execute_scalar(scalar_query)
        assert count >= 1

        assert repo.dialect_name

    def test_error_branches_raise_repository_exception(self):
        class Dummy:
            def __init__(self, **kwargs):
                self.id = kwargs.get("id", "dummy")

        mock_db = MagicMock()
        repo = BaseRepository(mock_db, Dummy)

        mock_db.flush.side_effect = IntegrityError("stmt", {}, Exception("orig"))
        with pytest.raises(RepositoryException):
            repo.create(id="dup")
        assert mock_db.rollback.called

        mock_db.flush.side_effect = None
        mock_db.query.side_effect = SQLAlchemyError("boom")

        with pytest.raises(RepositoryException):
            repo.get_by_id("id")
        with pytest.raises(RepositoryException):
            repo.get_all()
        with pytest.raises(RepositoryException):
            repo.exists(id="id")
        with pytest.raises(RepositoryException):
            repo.count(id="id")
        with pytest.raises(RepositoryException):
            repo.find_by(id="id")
        with pytest.raises(RepositoryException):
            repo.find_one_by(id="id")

        query = MagicMock()
        query.all.side_effect = SQLAlchemyError("boom")
        with pytest.raises(RepositoryException):
            repo._execute_query(query)

        scalar_query = MagicMock()
        scalar_query.scalar.side_effect = SQLAlchemyError("boom")
        with pytest.raises(RepositoryException):
            repo._execute_scalar(scalar_query)

    def test_update_delete_bulk_errors(self):
        class Dummy:
            def __init__(self, **kwargs):
                self.id = kwargs.get("id", "dummy")

        mock_db = MagicMock()
        repo = BaseRepository(mock_db, Dummy)

        repo.get_by_id = MagicMock(return_value=Dummy(id="one"))
        mock_db.flush.side_effect = SQLAlchemyError("boom")
        with pytest.raises(RepositoryException):
            repo.update("one", name="updated")

        mock_db.flush.side_effect = IntegrityError("stmt", {}, Exception("orig"))
        with pytest.raises(RepositoryException):
            repo.delete("one")

        mock_db.flush.side_effect = None
        mock_db.bulk_save_objects.side_effect = SQLAlchemyError("boom")
        with pytest.raises(RepositoryException):
            repo.bulk_create([{"id": "a"}])

        mock_db.bulk_save_objects.side_effect = None
        mock_db.query.side_effect = SQLAlchemyError("boom")
        with pytest.raises(RepositoryException):
            repo.bulk_update([{"id": "a", "name": "updated"}])
