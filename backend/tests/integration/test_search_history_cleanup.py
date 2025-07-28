# backend/tests/integration/test_search_history_cleanup.py
"""
Integration tests for search history cleanup service.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.search_history import SearchHistory
from app.models.user import User
from app.services.search_history_cleanup_service import SearchHistoryCleanupService

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


class TestSearchHistoryCleanup:
    """Test search history cleanup operations."""

    def test_cleanup_soft_deleted_searches(self, db: Session, monkeypatch):
        """Test cleanup of old soft-deleted searches."""
        # Set retention to 30 days for testing
        monkeypatch.setattr(settings, "soft_delete_retention_days", 30)

        service = SearchHistoryCleanupService(db)

        # Create unique test data
        import uuid

        unique_id = uuid.uuid4().hex[:8]

        # Create searches with various deleted_at dates
        now = datetime.now(timezone.utc)
        guest_ids = [
            f"cleanup-test-1-{unique_id}",
            f"cleanup-test-2-{unique_id}",
            f"cleanup-test-3-{unique_id}",
            f"cleanup-test-4-{unique_id}",
        ]

        searches = [
            # Should be kept - not deleted
            SearchHistory(
                guest_session_id=guest_ids[0],
                search_query=f"active search {unique_id}",
                search_type="natural_language",
                first_searched_at=now - timedelta(days=60),
            ),
            # Should be kept - deleted recently
            SearchHistory(
                guest_session_id=guest_ids[1],
                search_query=f"recent delete {unique_id}",
                search_type="natural_language",
                deleted_at=now - timedelta(days=10),
                first_searched_at=now - timedelta(days=20),
            ),
            # Should be cleaned up - old soft delete
            SearchHistory(
                guest_session_id=guest_ids[2],
                search_query=f"old delete 1 {unique_id}",
                search_type="natural_language",
                deleted_at=now - timedelta(days=45),
                first_searched_at=now - timedelta(days=50),
            ),
            # Should be cleaned up - very old soft delete
            SearchHistory(
                guest_session_id=guest_ids[3],
                search_query=f"old delete 2 {unique_id}",
                search_type="natural_language",
                deleted_at=now - timedelta(days=90),
                first_searched_at=now - timedelta(days=100),
            ),
        ]
        db.add_all(searches)
        db.commit()

        # Run cleanup
        deleted_count = service.cleanup_soft_deleted_searches()

        # Should delete at least our 2 test records (might delete more from other tests)
        assert deleted_count >= 2

        # Verify correct records were deleted
        # Only check our test records, not all records in the database
        remaining = db.query(SearchHistory).filter(SearchHistory.guest_session_id.in_(guest_ids)).all()
        assert len(remaining) == 2
        assert any(s.search_query == f"active search {unique_id}" for s in remaining)
        assert any(s.search_query == f"recent delete {unique_id}" for s in remaining)

    def test_cleanup_disabled_with_zero_retention(self, db: Session, monkeypatch):
        """Test that cleanup is disabled when retention is 0."""
        monkeypatch.setattr(settings, "soft_delete_retention_days", 0)

        service = SearchHistoryCleanupService(db)

        # Create old soft-deleted search
        search = SearchHistory(
            guest_session_id="cleanup-disabled-test",
            search_query="old search",
            search_type="natural_language",
            deleted_at=datetime.now(timezone.utc) - timedelta(days=365),
            first_searched_at=datetime.now(timezone.utc),
            last_searched_at=datetime.now(timezone.utc),
        )
        db.add(search)
        db.commit()

        # Run cleanup
        deleted_count = service.cleanup_soft_deleted_searches()

        assert deleted_count == 0
        # Check that our specific test record still exists
        assert db.query(SearchHistory).filter_by(guest_session_id="cleanup-disabled-test").count() == 1

    def test_cleanup_old_guest_sessions(self, db: Session, monkeypatch):
        """Test cleanup of old guest session searches."""
        # Configure cleanup settings
        monkeypatch.setattr(settings, "guest_session_purge_days", 30)
        monkeypatch.setattr(settings, "guest_session_expiry_days", 30)

        service = SearchHistoryCleanupService(db)
        now = datetime.now(timezone.utc)

        # Create user for conversions
        user = User(email="test@example.com", hashed_password="hash", full_name="Test", role="student")
        db.add(user)
        db.commit()

        # Create unique test data
        import uuid

        unique_id = uuid.uuid4().hex[:8]
        guest_ids = [f"guest-1-{unique_id}", f"guest-2-{unique_id}", f"guest-3-{unique_id}", f"guest-4-{unique_id}"]

        # Create various guest searches
        searches = [
            # Should be kept - recent unconverted
            SearchHistory(
                guest_session_id=guest_ids[0],
                search_query=f"recent guest {unique_id}",
                search_type="natural_language",
                first_searched_at=now - timedelta(days=10),
            ),
            # Should be deleted - old converted
            SearchHistory(
                guest_session_id=guest_ids[1],
                search_query=f"old converted {unique_id}",
                search_type="natural_language",
                converted_to_user_id=user.id,
                converted_at=now - timedelta(days=45),
                first_searched_at=now - timedelta(days=50),
            ),
            # Should be deleted - very old unconverted (expired)
            SearchHistory(
                guest_session_id=guest_ids[2],
                search_query=f"expired guest {unique_id}",
                search_type="natural_language",
                first_searched_at=now - timedelta(days=90),  # Older than expiry + purge
            ),
            # Should be kept - recent conversion
            SearchHistory(
                guest_session_id=guest_ids[3],
                search_query=f"recent converted {unique_id}",
                search_type="natural_language",
                converted_to_user_id=user.id,
                converted_at=now - timedelta(days=5),
                first_searched_at=now - timedelta(days=10),
            ),
        ]
        db.add_all(searches)
        db.commit()

        # Run cleanup
        deleted_count = service.cleanup_old_guest_sessions()

        # Should delete at least our 2 test records
        assert deleted_count >= 2

        # Verify correct records remain (filter for our test data)
        remaining = db.query(SearchHistory).filter(SearchHistory.guest_session_id.in_(guest_ids)).all()
        assert len(remaining) == 2
        assert any(s.search_query == f"recent guest {unique_id}" for s in remaining)
        assert any(s.search_query == f"recent converted {unique_id}" for s in remaining)

    def test_cleanup_all(self, db: Session, monkeypatch):
        """Test running all cleanup operations."""
        # Configure settings
        monkeypatch.setattr(settings, "soft_delete_retention_days", 30)
        monkeypatch.setattr(settings, "guest_session_purge_days", 30)
        monkeypatch.setattr(settings, "guest_session_expiry_days", 30)

        service = SearchHistoryCleanupService(db)
        now = datetime.now(timezone.utc)

        # Create searches to be cleaned
        searches = [
            # Old soft-deleted
            SearchHistory(
                guest_session_id="cleanup-all-1",
                search_query="old deleted",
                search_type="natural_language",
                deleted_at=now - timedelta(days=45),
                first_searched_at=now - timedelta(days=50),
            ),
            # Old guest session
            SearchHistory(
                guest_session_id="old-guest",
                search_query="old guest",
                search_type="natural_language",
                first_searched_at=now - timedelta(days=90),
            ),
        ]
        db.add_all(searches)
        db.commit()

        # Run all cleanup
        soft_deleted, guest_sessions = service.cleanup_all()

        # Should delete at least our test records
        assert soft_deleted >= 1
        assert guest_sessions >= 1
        # Check only our test records are gone
        remaining = (
            db.query(SearchHistory).filter(SearchHistory.guest_session_id.in_(["cleanup-all-1", "old-guest"])).count()
        )
        assert remaining == 0

    def test_get_cleanup_statistics(self, db: Session, monkeypatch):
        """Test getting cleanup statistics."""
        # Configure settings
        monkeypatch.setattr(settings, "soft_delete_retention_days", 30)
        monkeypatch.setattr(settings, "guest_session_purge_days", 30)
        monkeypatch.setattr(settings, "guest_session_expiry_days", 30)

        service = SearchHistoryCleanupService(db)
        now = datetime.now(timezone.utc)

        # Create user for converted guest
        user = User(email="stats@example.com", hashed_password="hash", full_name="Stats User", role="student")
        db.add(user)
        db.commit()

        # Create various searches
        searches = [
            # Active search
            SearchHistory(
                guest_session_id="stats-test-1",
                search_query="active",
                search_type="natural_language",
                first_searched_at=datetime.now(timezone.utc),
                last_searched_at=datetime.now(timezone.utc),
            ),
            # Recent soft-deleted (not eligible)
            SearchHistory(
                guest_session_id="stats-test-2",
                search_query="recent delete",
                search_type="natural_language",
                deleted_at=now - timedelta(days=10),
                first_searched_at=now - timedelta(days=10),
                last_searched_at=now - timedelta(days=10),
            ),
            # Old soft-deleted (eligible)
            SearchHistory(
                guest_session_id="stats-test-3",
                search_query="old delete",
                search_type="natural_language",
                deleted_at=now - timedelta(days=45),
                first_searched_at=now - timedelta(days=45),
                last_searched_at=now - timedelta(days=45),
            ),
            # Guest search (not eligible)
            SearchHistory(
                guest_session_id="guest-1",
                search_query="guest",
                search_type="natural_language",
                first_searched_at=datetime.now(timezone.utc),
                last_searched_at=datetime.now(timezone.utc),
            ),
            # Old converted guest (eligible)
            SearchHistory(
                guest_session_id="guest-2",
                search_query="old converted",
                search_type="natural_language",
                converted_to_user_id=user.id,
                converted_at=now - timedelta(days=45),
                first_searched_at=now - timedelta(days=50),
            ),
        ]
        db.add_all(searches)
        db.commit()

        # Get statistics
        stats = service.get_cleanup_statistics()

        # Due to test pollution, we can only check that our test data is included
        assert stats["total_soft_deleted"] >= 2  # At least our 2 test records
        assert stats["soft_deleted_eligible"] >= 1  # At least our 1 eligible record
        assert stats["converted_guest_eligible"] >= 1
        assert stats["expired_guest_eligible"] >= 0
