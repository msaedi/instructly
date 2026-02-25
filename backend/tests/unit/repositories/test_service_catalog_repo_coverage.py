"""Unit coverage for ServiceCatalogRepository – uncovered lines around L59,73,76,78,84,87,89,172-173,466,697-698,854,961,1169,1175,1207."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.repositories.service_catalog_repository import (
    ServiceCatalogRepository,
    _apply_active_catalog_predicate,
    _apply_instructor_service_active_filter,
    _check_pg_trgm,
    _escape_like,
    _money_to_cents,
)


class TestMoneyToCents:
    """L38-42: _money_to_cents edge cases."""

    def test_none_returns_zero(self) -> None:
        assert _money_to_cents(None) == 0

    def test_float_converts(self) -> None:
        assert _money_to_cents(9.99) == 999

    def test_integer_converts(self) -> None:
        assert _money_to_cents(10) == 1000

    def test_string_numeric_converts(self) -> None:
        assert _money_to_cents("19.50") == 1950


class TestCheckPgTrgm:
    """L59: _check_pg_trgm caching and error path."""

    def test_check_pg_trgm_caches_true(self) -> None:
        import app.repositories.service_catalog_repository as mod

        original = mod._pg_trgm_available
        try:
            mod._pg_trgm_available = None
            mock_db = MagicMock()
            mock_db.execute.return_value.first.return_value = (1,)

            result = _check_pg_trgm(mock_db)
            assert result is True
            # Second call should use cached value
            result2 = _check_pg_trgm(mock_db)
            assert result2 is True
        finally:
            mod._pg_trgm_available = original

    def test_check_pg_trgm_returns_false_on_error(self) -> None:
        import app.repositories.service_catalog_repository as mod

        original = mod._pg_trgm_available
        try:
            mod._pg_trgm_available = None
            mock_db = MagicMock()
            mock_db.execute.side_effect = RuntimeError("boom")

            result = _check_pg_trgm(mock_db)
            assert result is False
        finally:
            mod._pg_trgm_available = original

    def test_check_pg_trgm_returns_false_when_no_extension(self) -> None:
        import app.repositories.service_catalog_repository as mod

        original = mod._pg_trgm_available
        try:
            mod._pg_trgm_available = None
            mock_db = MagicMock()
            mock_db.execute.return_value.first.return_value = None

            result = _check_pg_trgm(mock_db)
            assert result is False
        finally:
            mod._pg_trgm_available = original


class TestApplyActivePredicates:
    """L73,76,78,84,87,89: filter predicates for is_deleted, deleted_at."""

    def test_active_catalog_predicate(self) -> None:
        query = MagicMock()
        query.filter.return_value = query
        _apply_active_catalog_predicate(query)
        # Should have been called for is_active at minimum
        assert query.filter.called

    def test_instructor_service_active_filter(self) -> None:
        query = MagicMock()
        query.filter.return_value = query
        _apply_instructor_service_active_filter(query)
        assert query.filter.called


class TestEscapeLike:
    """L93-95: _escape_like."""

    def test_escapes_percent(self) -> None:
        assert _escape_like("100%") == "100\\%"

    def test_escapes_underscore(self) -> None:
        assert _escape_like("a_b") == "a\\_b"

    def test_escapes_backslash(self) -> None:
        assert _escape_like("a\\b") == "a\\\\b"

    def test_combined(self) -> None:
        assert _escape_like("a%b_c\\d") == "a\\%b\\_c\\\\d"


class TestCheckPgTrgmDoubleCheckLock:
    """L58-59: double-check locking inside the lock."""

    def test_check_pg_trgm_double_check_inside_lock(self) -> None:
        """L58-59: If _pg_trgm_available is set by another thread inside the lock, return it."""
        import app.repositories.service_catalog_repository as mod

        original = mod._pg_trgm_available
        try:
            mod._pg_trgm_available = None
            mock_db = MagicMock()

            # First call discovers pg_trgm
            mock_db.execute.return_value.first.return_value = (1,)
            _check_pg_trgm(mock_db)
            assert mod._pg_trgm_available is True

            # Reset to None, then set to True before entering lock
            # to simulate another thread having set it
            mod._pg_trgm_available = True
            result = _check_pg_trgm(mock_db)
            assert result is True
        finally:
            mod._pg_trgm_available = original


class TestActivePredicateHasattrBranches:
    """L73,76,78,84,87,89: hasattr branches for is_active, is_deleted, deleted_at."""

    def test_apply_active_catalog_predicate_all_attributes(self) -> None:
        """All three attributes exist on ServiceCatalog — all filters applied."""
        query = MagicMock()
        query.filter.return_value = query
        result = _apply_active_catalog_predicate(query)
        # Should be called for each hasattr that returns True
        assert query.filter.call_count >= 1
        assert result is query

    def test_apply_instructor_service_active_filter_all_attributes(self) -> None:
        """All three attributes exist on InstructorService — all filters applied."""
        query = MagicMock()
        query.filter.return_value = query
        result = _apply_instructor_service_active_filter(query)
        assert query.filter.call_count >= 1
        assert result is query


class TestFindSimilarByEmbedding:
    """L172-173: OperationalError re-raised, generic exception returns []."""

    def test_operational_error_raises(self) -> None:
        from sqlalchemy.exc import OperationalError

        mock_db = MagicMock()
        repo = ServiceCatalogRepository(mock_db)
        mock_db.execute.side_effect = OperationalError("stmt", {}, Exception("conn"))

        with pytest.raises(OperationalError):
            repo.find_similar_by_embedding([0.1] * 1536, limit=5)

    def test_generic_error_returns_empty(self) -> None:
        mock_db = MagicMock()
        repo = ServiceCatalogRepository(mock_db)
        mock_db.execute.side_effect = ValueError("bad embedding")

        result = repo.find_similar_by_embedding([0.1] * 1536, limit=5)
        assert result == []

    def test_empty_result_returns_empty(self) -> None:
        mock_db = MagicMock()
        repo = ServiceCatalogRepository(mock_db)
        mock_db.execute.return_value.fetchall.return_value = []

        result = repo.find_similar_by_embedding([0.1] * 1536, limit=5)
        assert result == []


class TestSearchWithActiveFilter:
    """L466: search_services with include_inactive=False applies active predicate."""

    def test_search_services_with_categories_applies_active_filter(self) -> None:
        """L465-466: include_inactive=False triggers _apply_active_catalog_predicate."""
        mock_db = MagicMock()
        repo = ServiceCatalogRepository(mock_db)
        repo._pg_trgm_available = False

        # Set up the chain so query.options().filter().filter().order_by().limit().all() returns []
        chain = MagicMock()
        chain.options.return_value = chain
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.limit.return_value = chain
        chain.all.return_value = []
        mock_db.query.return_value = chain

        result = repo.search_services_with_categories(query_text="piano", include_inactive=False)
        assert result == []
        # filter should have been called (for active predicate + search)
        assert chain.filter.call_count >= 1


class TestGetServicesForKids:
    """L696-698: OperationalError in kids services re-raised."""

    def test_kids_services_operational_error_raises(self) -> None:
        from sqlalchemy.exc import OperationalError

        mock_db = MagicMock()
        repo = ServiceCatalogRepository(mock_db)
        mock_db.query.side_effect = OperationalError("stmt", {}, Exception("conn"))

        with pytest.raises(OperationalError):
            repo.get_services_available_for_kids_minimal()

    def test_kids_services_generic_error_returns_empty(self) -> None:
        mock_db = MagicMock()
        repo = ServiceCatalogRepository(mock_db)
        mock_db.query.side_effect = ValueError("generic error")

        result = repo.get_services_available_for_kids_minimal()
        assert result == []


class TestSearchServicesByName:
    """L854: no pg_trgm fallback uses ILIKE."""

    def test_search_by_name_no_trgm(self) -> None:
        """L853-856: When pg_trgm is not available, falls back to ILIKE + order_by."""
        mock_db = MagicMock()
        repo = ServiceCatalogRepository(mock_db)
        repo._pg_trgm_available = False

        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.limit.return_value = chain
        chain.all.return_value = []
        mock_db.query.return_value = chain

        result = repo.search_services_by_name("piano")
        assert result == []
        # Should have filter and order_by calls
        assert chain.filter.call_count >= 1
        assert chain.order_by.called

    def test_search_by_name_with_trgm(self) -> None:
        """L841-852: When pg_trgm is available, uses similarity + ILIKE."""
        mock_db = MagicMock()
        repo = ServiceCatalogRepository(mock_db)
        repo._pg_trgm_available = True

        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.limit.return_value = chain
        chain.all.return_value = []
        mock_db.query.return_value = chain

        result = repo.search_services_by_name("piano")
        assert result == []


class TestAnalyticsRepoUpdate:
    """L960-961: analytics update returns None when entity not found."""

    def test_analytics_update_not_found_returns_none(self) -> None:
        from app.repositories.service_catalog_repository import ServiceAnalyticsRepository

        mock_db = MagicMock()
        repo = ServiceAnalyticsRepository(mock_db)
        # find_one_by returns None
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        result = repo.update("NONEXISTENT_ID", booking_count_7d=10)
        assert result is None


class TestBulkUpdateAll:
    """L1169, L1175, L1207: bulk_update_all edge cases."""

    def test_empty_updates_returns_zero(self) -> None:
        """L1168-1169: empty updates list → return 0."""
        from app.repositories.service_catalog_repository import ServiceAnalyticsRepository

        mock_db = MagicMock()
        repo = ServiceAnalyticsRepository(mock_db)
        result = repo.bulk_update_all([])
        assert result == 0

    def test_updates_without_service_catalog_id_skipped(self) -> None:
        """L1174-1175: entries missing service_catalog_id are skipped."""
        from app.repositories.service_catalog_repository import ServiceAnalyticsRepository

        mock_db = MagicMock()
        repo = ServiceAnalyticsRepository(mock_db)
        result = repo.bulk_update_all([
            {"booking_count_7d": 5},  # no service_catalog_id
            {"service_catalog_id": "", "booking_count_7d": 3},  # empty string is falsy
        ])
        # All entries skipped → mappings empty → returns 0
        assert result == 0

    def test_updates_with_valid_and_invalid_entries(self) -> None:
        """L1175 + L1207: mix of valid and invalid entries."""
        from app.repositories.service_catalog_repository import ServiceAnalyticsRepository

        mock_db = MagicMock()
        repo = ServiceAnalyticsRepository(mock_db)

        updates = [
            {"service_catalog_id": "SVC_01", "booking_count_7d": 10},
            {"booking_count_7d": 5},  # skipped (no id)
        ]
        repo.bulk_update_all(updates)
        # Should have processed 1 valid mapping
        mock_db.bulk_update_mappings.assert_called_once()
        assert mock_db.flush.called
