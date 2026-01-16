from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core import timezone_utils


def test_timezone_conversions() -> None:
    user = SimpleNamespace(timezone="UTC")

    tz = timezone_utils.get_user_timezone(user)
    assert str(tz) == "UTC"

    now = timezone_utils.get_user_now(user)
    assert now.tzinfo is not None

    today = timezone_utils.get_user_today(user)
    assert today == now.date()

    naive = datetime(2024, 1, 1, 12, 0, 0)
    converted = timezone_utils.convert_to_user_timezone(naive, user)
    assert converted.tzinfo is not None

    payload = timezone_utils.format_datetime_for_user(naive, user)
    assert payload["timezone"] == "UTC"


def test_user_today_by_id(monkeypatch) -> None:
    user = SimpleNamespace(timezone="UTC")

    class DummyRepo:
        def get_by_id(self, _user_id):
            return user

    class DummyFactory:
        @staticmethod
        def create_user_repository(_db):
            return DummyRepo()

    monkeypatch.setattr("app.repositories.factory.RepositoryFactory", DummyFactory, raising=False)

    result = timezone_utils.get_user_today_by_id("u1", db=SimpleNamespace())
    assert result == timezone_utils.get_user_today(user)


def test_user_now_by_id_missing_user(monkeypatch) -> None:
    class DummyRepo:
        def get_by_id(self, _user_id):
            return None

    class DummyFactory:
        @staticmethod
        def create_user_repository(_db):
            return DummyRepo()

    monkeypatch.setattr("app.repositories.factory.RepositoryFactory", DummyFactory, raising=False)

    with pytest.raises(ValueError):
        timezone_utils.get_user_now_by_id("u1", db=SimpleNamespace())
