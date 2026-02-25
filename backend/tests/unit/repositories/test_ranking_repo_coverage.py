"""Unit coverage for RankingRepository – uncovered L153,236,249,252-253."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

from app.repositories.ranking_repository import RankingRepository


def _make_repo() -> tuple[RankingRepository, MagicMock]:
    mock_db = MagicMock()
    repo = RankingRepository(mock_db)
    return repo, mock_db


class TestGetGlobalAverageRating:
    """L153: double-check locking and cached value paths."""

    def test_returns_default_when_no_reviews(self) -> None:
        repo, mock_db = _make_repo()
        row = MagicMock()
        row.global_avg = None
        mock_db.execute.return_value.first.return_value = row

        import app.repositories.ranking_repository as mod

        original_cache = mod._GLOBAL_AVG_RATING_CACHE
        original_at = mod._GLOBAL_AVG_RATING_CACHED_AT
        original_ttl = mod._GLOBAL_AVG_RATING_TTL_S
        try:
            mod._GLOBAL_AVG_RATING_CACHE = None
            mod._GLOBAL_AVG_RATING_CACHED_AT = 0.0
            mod._GLOBAL_AVG_RATING_TTL_S = 600

            result = repo.get_global_average_rating()
            assert result == 4.2
        finally:
            mod._GLOBAL_AVG_RATING_CACHE = original_cache
            mod._GLOBAL_AVG_RATING_CACHED_AT = original_at
            mod._GLOBAL_AVG_RATING_TTL_S = original_ttl

    def test_uses_cached_value(self) -> None:
        """L153: When cached and TTL not expired, returns cached value."""
        import app.repositories.ranking_repository as mod

        original_cache = mod._GLOBAL_AVG_RATING_CACHE
        original_at = mod._GLOBAL_AVG_RATING_CACHED_AT
        original_ttl = mod._GLOBAL_AVG_RATING_TTL_S
        try:
            mod._GLOBAL_AVG_RATING_CACHE = 3.7
            mod._GLOBAL_AVG_RATING_CACHED_AT = time.monotonic()
            mod._GLOBAL_AVG_RATING_TTL_S = 600

            repo, mock_db = _make_repo()
            result = repo.get_global_average_rating()
            assert result == 3.7
            mock_db.execute.assert_not_called()
        finally:
            mod._GLOBAL_AVG_RATING_CACHE = original_cache
            mod._GLOBAL_AVG_RATING_CACHED_AT = original_at
            mod._GLOBAL_AVG_RATING_TTL_S = original_ttl

    def test_ttl_zero_always_queries(self) -> None:
        """When TTL is 0, always queries the database."""
        import app.repositories.ranking_repository as mod

        original_ttl = mod._GLOBAL_AVG_RATING_TTL_S
        try:
            mod._GLOBAL_AVG_RATING_TTL_S = 0

            repo, mock_db = _make_repo()
            row = MagicMock()
            row.global_avg = 4.5
            mock_db.execute.return_value.first.return_value = row

            result = repo.get_global_average_rating()
            assert result == 4.5
        finally:
            mod._GLOBAL_AVG_RATING_TTL_S = original_ttl


class TestGetServiceAudience:
    """L236: empty service_ids."""

    def test_empty_ids(self) -> None:
        repo, _ = _make_repo()
        assert repo.get_service_audience([]) == {}


class TestClassifyAudience:
    """L249,252-253: _classify_audience edge cases."""

    def test_empty_age_groups(self) -> None:
        repo, _ = _make_repo()
        assert repo._classify_audience([]) == "both"

    def test_kids_only(self) -> None:
        repo, _ = _make_repo()
        assert repo._classify_audience(["kids", "teens"]) == "kids"

    def test_adults_only(self) -> None:
        repo, _ = _make_repo()
        assert repo._classify_audience(["adults", "seniors"]) == "adults"

    def test_mixed(self) -> None:
        repo, _ = _make_repo()
        assert repo._classify_audience(["kids", "adults"]) == "both"

    def test_unrecognized_groups(self) -> None:
        """Unrecognized groups lead to neither child nor adult -> 'both'."""
        repo, _ = _make_repo()
        assert repo._classify_audience(["unknown_group"]) == "both"


class TestGetServiceSkillLevels:
    """Cover filter_selections parsing edge cases."""

    def test_empty_ids(self) -> None:
        repo, _ = _make_repo()
        assert repo.get_service_skill_levels([]) == {}

    def test_filter_selections_as_string_json(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        # filter_selections is a JSON string
        query.all.return_value = [
            ("svc-01", json.dumps({"skill_level": ["beginner", "intermediate"]}))
        ]

        result = repo.get_service_skill_levels(["svc-01"])
        assert result["svc-01"] == ["beginner", "intermediate"]

    def test_filter_selections_invalid_json_string(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.all.return_value = [("svc-02", "not-valid-json")]

        result = repo.get_service_skill_levels(["svc-02"])
        assert result["svc-02"] == ["all"]

    def test_filter_selections_none(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.all.return_value = [("svc-03", None)]

        result = repo.get_service_skill_levels(["svc-03"])
        assert result["svc-03"] == ["all"]

    def test_filter_selections_dict_without_skill_level(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.all.return_value = [("svc-04", {"other": "value"})]

        result = repo.get_service_skill_levels(["svc-04"])
        assert result["svc-04"] == ["all"]


class TestGetInstructorMetrics:
    """Empty IDs early return."""

    def test_empty_ids(self) -> None:
        repo, _ = _make_repo()
        assert repo.get_instructor_metrics([]) == {}


class TestGetInstructorDistances:
    """Empty IDs early return."""

    def test_empty_ids(self) -> None:
        repo, _ = _make_repo()
        assert repo.get_instructor_distances([], 0.0, 0.0) == {}


class TestGetInstructorTenureDate:
    """Empty IDs early return."""

    def test_empty_ids(self) -> None:
        repo, _ = _make_repo()
        assert repo.get_instructor_tenure_date([]) == {}
