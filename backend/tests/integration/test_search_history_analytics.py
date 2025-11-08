# backend/tests/integration/test_search_history_analytics.py
"""
Integration tests for search history analytics features.

Tests cover:
- Guest search tracking
- Soft delete functionality
- Guest-to-user conversion
- Search limit configuration
- Analytics eligibility

These tests require database access and test the full stack integration.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.ulid_helper import generate_ulid
from app.models.search_history import SearchHistory
from app.models.user import User
from app.repositories.search_history_repository import SearchHistoryRepository
from app.services.search_history_service import SearchHistoryService

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


class TestGuestSearchTracking:
    """Test guest search tracking functionality."""

    @pytest.mark.asyncio
    async def test_guest_search_recording(self, db: Session):
        """Test that guest searches are recorded with session ID."""
        service = SearchHistoryService(db)
        guest_session_id = "test-guest-123"

        # Record a guest search
        search = await service.record_search(
            guest_session_id=guest_session_id, query="piano lessons", search_type="natural_language", results_count=5
        )

        assert search is not None
        assert search.guest_session_id == guest_session_id
        assert search.user_id is None
        assert search.search_query == "piano lessons"
        assert search.results_count == 5
        assert search.deleted_at is None

    @pytest.mark.asyncio
    async def test_guest_search_deduplication(self, db: Session):
        """Test that duplicate guest searches update timestamp."""
        service = SearchHistoryService(db)
        import uuid

        guest_session_id = f"test-guest-{uuid.uuid4().hex[:8]}"

        # Record first search
        search1 = await service.record_search(
            guest_session_id=guest_session_id, query="guitar lessons", search_type="natural_language", results_count=3
        )

        # Wait a bit
        import time

        time.sleep(0.1)

        # Record same search again
        search2 = await service.record_search(
            guest_session_id=guest_session_id, query="guitar lessons", search_type="natural_language", results_count=7
        )

        # Should be same record with updated values
        assert search1.id == search2.id
        assert search2.results_count == 7  # Results count SHOULD update to latest
        assert search2.search_count == 2  # Count should increment
        assert search2.last_searched_at >= search1.last_searched_at  # Allow equal due to timing

    def test_guest_recent_searches(self, db: Session):
        """Test retrieving recent guest searches."""
        service = SearchHistoryService(db)
        import uuid

        unique_id = uuid.uuid4().hex[:8]
        guest_session_id = f"test-guest-{unique_id}"

        # Create searches with different timestamps
        searches = []
        base_time = datetime.now(timezone.utc)
        for i, query in enumerate(["piano lessons", "guitar teachers", "drum classes", "violin tutors"]):
            search = SearchHistory(
                guest_session_id=guest_session_id,
                search_query=f"{query} {unique_id}",  # Make queries unique too
                normalized_query=f"{query} {unique_id}".strip().lower(),
                search_type="natural_language",
                first_searched_at=base_time - timedelta(minutes=i),
                last_searched_at=base_time - timedelta(minutes=i),
            )
            db.add(search)
            searches.append(search)
        db.commit()

        # Get recent searches
        recent = service.get_recent_searches(guest_session_id=guest_session_id, limit=3)

        assert len(recent) == 3
        # Should be in reverse chronological order
        assert recent[0].search_query == f"piano lessons {unique_id}"
        assert recent[1].search_query == f"guitar teachers {unique_id}"
        assert recent[2].search_query == f"drum classes {unique_id}"


class TestSoftDeleteFunctionality:
    """Test soft delete features."""

    def test_soft_delete_search(self, db: Session):
        """Test that deleted searches remain in DB with timestamp."""
        service = SearchHistoryService(db)

        # Create a user and a search
        user = User(
            email="test@example.com",
            hashed_password="hash",
            first_name="Test",
            last_name="User",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(user)
        db.commit()

        search = SearchHistory(
            user_id=user.id,
            search_query="test search",
            normalized_query="test search",
            search_type="natural_language",
            first_searched_at=datetime.now(timezone.utc),
            last_searched_at=datetime.now(timezone.utc),
        )
        db.add(search)
        db.commit()

        # Soft delete the search
        deleted = service.delete_search(user_id=user.id, search_id=search.id)

        assert deleted is True

        # Verify it still exists in DB
        db_search = db.query(SearchHistory).filter_by(id=search.id).first()
        assert db_search is not None
        assert db_search.deleted_at is not None

        # Verify it doesn't appear in recent searches
        recent = service.get_recent_searches(user_id=user.id)
        assert len(recent) == 0

    def test_soft_deleted_excluded_from_queries(self, db: Session):
        """Test that soft-deleted searches are excluded from normal queries."""
        repo = SearchHistoryRepository(db)

        # Create user
        user = User(
            email="test2@example.com",
            hashed_password="hash",
            first_name="Test",
            last_name="User",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(user)
        db.commit()

        # Create active and deleted searches
        active_search = SearchHistory(
            user_id=user.id,
            search_query="active search",
            normalized_query="active search",
            search_type="natural_language",
            first_searched_at=datetime.now(timezone.utc),
            last_searched_at=datetime.now(timezone.utc),
        )
        deleted_search = SearchHistory(
            user_id=user.id,
            search_query="deleted search",
            normalized_query="deleted search",
            search_type="natural_language",
            deleted_at=datetime.now(timezone.utc),
            first_searched_at=datetime.now(timezone.utc),
            last_searched_at=datetime.now(timezone.utc),
        )
        db.add_all([active_search, deleted_search])
        db.commit()

        # Test various repository methods
        assert repo.count_searches(user_id=user.id) == 1
        recent = repo.get_recent_searches(user_id=user.id)
        assert len(recent) == 1
        assert recent[0].search_query == "active search"


class TestGuestToUserConversion:
    """Test search conversion when guests become users."""

    def test_guest_search_conversion(self, db: Session):
        """Test converting guest searches to user searches."""
        service = SearchHistoryService(db)
        import uuid

        guest_session_id = f"convert-test-{uuid.uuid4().hex[:8]}"

        # Create user
        user = User(
            email=f"convert-{guest_session_id}@example.com",
            hashed_password="hash",
            first_name="Convert",
            last_name="User",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(user)
        db.commit()

        # Create guest searches
        for query in ["piano lessons", "guitar teachers", "music theory"]:
            search = SearchHistory(
                guest_session_id=guest_session_id,
                search_query=query,
                normalized_query=query.strip().lower(),
                search_type="natural_language",
                first_searched_at=datetime.now(timezone.utc) - timedelta(hours=1),
                last_searched_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            db.add(search)
        db.commit()

        # Convert searches
        converted_count = service.convert_guest_searches_to_user(guest_session_id=guest_session_id, user_id=user.id)

        assert converted_count == 3

        # Verify user now has the searches
        user_searches = service.get_recent_searches(user_id=user.id)
        assert len(user_searches) == 3

        # Verify guest searches are marked as converted
        guest_searches = db.query(SearchHistory).filter_by(guest_session_id=guest_session_id).all()
        for search in guest_searches:
            db.refresh(search)
            assert search.converted_to_user_id == user.id
            assert search.converted_at is not None

    def test_conversion_avoids_duplicates(self, db: Session):
        """Test that conversion doesn't create duplicate searches."""
        service = SearchHistoryService(db)
        import uuid

        guest_session_id = f"no-dup-test-{uuid.uuid4().hex[:8]}"

        # Create user with existing search
        user = User(
            email=f"existing-{guest_session_id}@example.com",
            hashed_password="hash",
            first_name="Existing",
            last_name="User",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(user)
        db.commit()

        existing_search = SearchHistory(
            user_id=user.id,
            search_query="piano lessons",
            normalized_query="piano lessons",
            search_type="natural_language",
            first_searched_at=datetime.now(timezone.utc),
            last_searched_at=datetime.now(timezone.utc),
        )
        db.add(existing_search)

        # Create guest search with same query
        guest_search = SearchHistory(
            guest_session_id=guest_session_id,
            search_query="piano lessons",
            normalized_query="piano lessons",
            search_type="natural_language",
            first_searched_at=datetime.now(timezone.utc),
            last_searched_at=datetime.now(timezone.utc),
        )
        db.add(guest_search)
        db.commit()

        # Convert
        converted_count = service.convert_guest_searches_to_user(guest_session_id=guest_session_id, user_id=user.id)

        # Should not create duplicate
        assert converted_count == 0

        # But guest search should still be marked as converted
        db.refresh(guest_search)
        assert guest_search.converted_to_user_id == user.id

    def test_conversion_preserves_timestamps(self, db: Session):
        """Test that original timestamps are preserved during conversion."""
        service = SearchHistoryService(db)
        import uuid

        unique_id = uuid.uuid4().hex[:8]
        guest_session_id = f"timestamp-test-{unique_id}"
        query = f"old search {unique_id}"

        # Create user
        user = User(
            email=f"timestamp-{unique_id}@example.com",
            hashed_password="hash",
            first_name="Timestamp",
            last_name="User",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(user)
        db.commit()

        # Create guest search with old timestamp
        old_timestamp = datetime.now(timezone.utc) - timedelta(days=7)
        guest_search = SearchHistory(
            guest_session_id=guest_session_id,
            search_query=query,
            normalized_query=query.strip().lower(),
            search_type="natural_language",
            first_searched_at=old_timestamp,
            last_searched_at=old_timestamp,
        )
        db.add(guest_search)
        db.commit()

        # Convert
        service.convert_guest_searches_to_user(guest_session_id=guest_session_id, user_id=user.id)

        # Check user's search has old timestamp
        user_searches = service.get_recent_searches(user_id=user.id)
        assert len(user_searches) == 1
        # Compare timestamps without timezone info
        assert user_searches[0].first_searched_at == old_timestamp


class TestSearchLimitConfiguration:
    """Test configurable search limits."""

    @pytest.mark.asyncio
    async def test_search_limit_enforcement(self, db: Session, monkeypatch):
        """Test that search limits are enforced."""
        # Set low limit for testing
        monkeypatch.setattr(settings, "search_history_max_per_user", 3)

        service = SearchHistoryService(db)
        user = User(
            email="limit@example.com",
            hashed_password="hash",
            first_name="Limit",
            last_name="User",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(user)
        db.commit()

        # Add more searches than limit
        for i in range(5):
            await service.record_search(user_id=user.id, query=f"search {i}", search_type="natural_language")

        # Should only have 3 most recent
        searches = service.get_recent_searches(user_id=user.id, limit=10)
        assert len(searches) == 3
        assert searches[0].search_query == "search 4"  # Most recent
        assert searches[2].search_query == "search 2"  # Oldest kept

    @pytest.mark.asyncio
    async def test_search_limit_disabled(self, db: Session, monkeypatch):
        """Test that setting limit to 0 disables it."""
        # Disable limit
        monkeypatch.setattr(settings, "search_history_max_per_user", 0)

        service = SearchHistoryService(db)
        user = User(
            email="nolimit@example.com",
            hashed_password="hash",
            first_name="No",
            last_name="Limit User",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(user)
        db.commit()

        # Add many searches
        for i in range(20):
            await service.record_search(user_id=user.id, query=f"search {i}", search_type="natural_language")

        # All should be kept
        count = db.query(SearchHistory).filter_by(user_id=user.id, deleted_at=None).count()
        assert count == 20


class TestAnalyticsEligibility:
    """Test analytics data queries."""

    def test_analytics_includes_soft_deleted(self, db: Session):
        """Test that analytics queries include soft-deleted searches."""
        repo = SearchHistoryRepository(db)
        import uuid

        unique_id = uuid.uuid4().hex[:8]

        # Create searches: active and soft-deleted
        guest_id_1 = f"analytics-test-1-{unique_id}"
        guest_id_2 = f"analytics-test-2-{unique_id}"

        searches = [
            SearchHistory(
                guest_session_id=guest_id_1,
                search_query=f"active 1 {unique_id}",
                normalized_query=f"active 1 {unique_id}".strip().lower(),
                search_type="natural_language",
            ),
            SearchHistory(
                guest_session_id=guest_id_1,
                search_query=f"deleted 1 {unique_id}",
                normalized_query=f"deleted 1 {unique_id}".strip().lower(),
                search_type="natural_language",
                deleted_at=datetime.now(timezone.utc),
            ),
            SearchHistory(
                guest_session_id=guest_id_2,
                search_query=f"active 2 {unique_id}",
                normalized_query=f"active 2 {unique_id}".strip().lower(),
                search_type="natural_language",
            ),
            SearchHistory(
                guest_session_id=guest_id_2,
                search_query=f"deleted 2 {unique_id}",
                normalized_query=f"deleted 2 {unique_id}".strip().lower(),
                search_type="natural_language",
                deleted_at=datetime.now(timezone.utc),
            ),
        ]
        db.add_all(searches)
        db.commit()

        # Analytics query should include all our test searches
        analytics_query = repo.find_analytics_eligible_searches(include_deleted=True)
        # Filter to only our test searches to avoid data pollution
        results = analytics_query.filter(SearchHistory.guest_session_id.in_([guest_id_1, guest_id_2])).all()
        assert len(results) == 4

    def test_analytics_excludes_converted_guest_searches(self, db: Session):
        """Test that analytics doesn't double-count converted searches."""
        repo = SearchHistoryRepository(db)
        import uuid

        unique_id = uuid.uuid4().hex[:8]

        # Create user
        user = User(
            email=f"analytics-{unique_id}@example.com",
            hashed_password="hash",
            first_name="Analytics",
            last_name="User",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(user)
        db.commit()

        # Create converted guest search and corresponding user search
        query = f"test query {unique_id}"
        guest_search = SearchHistory(
            guest_session_id=f"analytics-guest-{unique_id}",
            search_query=query,
            normalized_query=query.strip().lower(),
            search_type="natural_language",
            converted_to_user_id=user.id,
            converted_at=datetime.now(timezone.utc),
        )
        user_search = SearchHistory(
            user_id=user.id,
            search_query=query,
            normalized_query=query.strip().lower(),
            search_type="natural_language",
            first_searched_at=datetime.now(timezone.utc),
            last_searched_at=datetime.now(timezone.utc),
        )
        db.add_all([guest_search, user_search])
        db.commit()

        # Analytics should only count the user version
        # Filter by our specific query to avoid test data pollution
        from app.models.search_history import SearchHistory as SH

        analytics_query = repo.find_analytics_eligible_searches()
        results = analytics_query.filter(SH.search_query == query).all()

        # Should have only the user version (converted guest excluded)
        assert len(results) == 1
        assert results[0].user_id == user.id


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_conversion_handles_missing_user(self, db: Session):
        """Test conversion fails gracefully with invalid user ID."""
        service = SearchHistoryService(db)

        # Try to convert with non-existent user
        converted = service.convert_guest_searches_to_user(
            guest_session_id="test-guest", user_id=generate_ulid()
        )  # Non-existent

        assert converted == 0

    def test_constraint_user_or_guest(self, db: Session):
        """Test database constraint requiring user_id OR guest_session_id."""
        # This should fail - no user_id or guest_session_id
        search = SearchHistory(
            search_query="invalid search",
            normalized_query="invalid search",
            search_type="natural_language",
            first_searched_at=datetime.now(timezone.utc),
            last_searched_at=datetime.now(timezone.utc),
        )
        db.add(search)

        with pytest.raises(Exception):  # Should violate constraint
            db.commit()
