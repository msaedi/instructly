import datetime as dt
from unittest.mock import MagicMock

import pytest

from app.tasks.search_analytics import generate_search_insights


class DummyRepo:
    def get_hourly_search_counts(self, since, limit=5):
        base = dt.datetime(2025, 9, 1, 12, 0, 0, tzinfo=dt.timezone.utc)
        return [
            {"hour_start": base, "count": 10},
            {"hour_start": base - dt.timedelta(hours=1), "count": 7},
        ]

    # Methods used by task that we don't exercise here
    def count_searches_since(self, since):
        return 0

    def count_searches_with_interactions(self, since):
        return 0

    def get_popular_searches(self, days=7, limit=10):
        return []


@pytest.fixture(autouse=True)
def patch_repo_and_db(monkeypatch):
    import app.tasks.search_analytics as sa

    # Patch DB generator to avoid real DB access
    mock_db = MagicMock()
    monkeypatch.setattr(sa, "get_db", lambda: iter([mock_db]))

    # Patch repository constructor to return our dummy repo
    monkeypatch.setattr(sa, "SearchEventRepository", lambda *a, **k: DummyRepo())
    yield


def test_generate_search_insights_includes_peak_search_hours():
    result = generate_search_insights.run(7)
    assert "peak_search_hours" in result
    assert isinstance(result["peak_search_hours"], list)
    assert len(result["peak_search_hours"]) == 2
    assert result["peak_search_hours"][0]["count"] == 10
