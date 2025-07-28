# backend/tests/repositories/test_search_history_repository.py
"""
Unit tests for SearchHistoryRepository.

Tests repository methods in isolation with a test database.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.search_history import SearchHistory
from app.models.user import User
from app.repositories.search_history_repository import SearchHistoryRepository


class TestSearchHistoryRepository:
    """Test SearchHistoryRepository methods."""

    def test_find_existing_search_user(self, db: Session):
        """Test finding existing search for a user."""
        repo = SearchHistoryRepository(db)

        # Create user and search
        user = User(
            email="test@example.com",
            hashed_password="hash",
            full_name="Test",
        )
        db.add(user)
        db.commit()

        search = SearchHistory(
            user_id=user.id,
            search_query="test query",
            search_type="natural_language",
            first_searched_at=datetime.now(timezone.utc),
            last_searched_at=datetime.now(timezone.utc),
        )
        db.add(search)
        db.commit()

        # Find it
        found = repo.find_existing_search(user_id=user.id, query="test query")
        assert found is not None
        assert found.id == search.id

        # Non-existent query
        not_found = repo.find_existing_search(user_id=user.id, query="different query")
        assert not_found is None

    def test_find_existing_search_guest(self, db: Session):
        """Test finding existing search for a guest."""
        repo = SearchHistoryRepository(db)
        import uuid

        unique_id = uuid.uuid4().hex[:8]
        guest_id = f"guest-{unique_id}"
        query = f"guest query {unique_id}"

        search = SearchHistory(
            guest_session_id=guest_id,
            search_query=query,
            search_type="category",
            first_searched_at=datetime.now(timezone.utc),
            last_searched_at=datetime.now(timezone.utc),
        )
        db.add(search)
        db.commit()

        # Find it
        found = repo.find_existing_search(guest_session_id=guest_id, query=query)
        assert found is not None
        assert found.id == search.id

        # Different guest session
        not_found = repo.find_existing_search(guest_session_id="different-guest", query=query)
        assert not_found is None

    def test_find_existing_search_excludes_deleted(self, db: Session):
        """Test that soft-deleted searches are excluded."""
        repo = SearchHistoryRepository(db)

        user = User(
            email="deleted@example.com",
            hashed_password="hash",
            full_name="Test",
        )
        db.add(user)
        db.commit()

        # Create deleted search
        search = SearchHistory(
            user_id=user.id,
            search_query="deleted query",
            search_type="natural_language",
            deleted_at=datetime.now(timezone.utc),
            first_searched_at=datetime.now(timezone.utc),
            last_searched_at=datetime.now(timezone.utc),
        )
        db.add(search)
        db.commit()

        # Should not find it
        found = repo.find_existing_search(user_id=user.id, query="deleted query")
        assert found is None

    def test_get_recent_searches_ordering(self, db: Session):
        """Test recent searches are ordered by last_searched_at desc."""
        repo = SearchHistoryRepository(db)
        import uuid

        guest_id = f"order-test-{uuid.uuid4().hex[:8]}"

        # Clean up any existing test data first
        db.query(SearchHistory).filter(SearchHistory.guest_session_id.like("order-test-%")).delete()
        db.commit()

        # Create searches with different timestamps
        base_time = datetime.now(timezone.utc)
        for i in range(5):
            search = SearchHistory(
                guest_session_id=guest_id,
                search_query=f"query {i}",
                search_type="natural_language",
                first_searched_at=base_time - timedelta(hours=i),
                last_searched_at=base_time - timedelta(hours=i),
            )
            db.add(search)
        db.commit()

        # Get recent
        recent = repo.get_recent_searches(guest_session_id=guest_id, limit=3)

        # Debug output
        for i, search in enumerate(recent):
            print(f"recent[{i}] = {search.search_query} (last_searched_at: {search.last_searched_at})")

        assert len(recent) == 3
        assert recent[0].search_query == "query 0"  # Most recent
        assert recent[1].search_query == "query 1"
        assert recent[2].search_query == "query 2"

    def test_count_searches(self, db: Session):
        """Test counting searches with various filters."""
        repo = SearchHistoryRepository(db)

        user = User(
            email="count@example.com",
            hashed_password="hash",
            full_name="Count",
        )
        db.add(user)
        db.commit()

        # Create mix of searches
        searches = [
            SearchHistory(
                user_id=user.id,
                search_query="active 1",
                search_type="natural_language",
                first_searched_at=datetime.now(timezone.utc),
                last_searched_at=datetime.now(timezone.utc),
            ),
            SearchHistory(
                user_id=user.id,
                search_query="active 2",
                search_type="natural_language",
                first_searched_at=datetime.now(timezone.utc),
                last_searched_at=datetime.now(timezone.utc),
            ),
            SearchHistory(
                user_id=user.id,
                search_query="deleted",
                search_type="natural_language",
                deleted_at=datetime.now(timezone.utc),
                first_searched_at=datetime.now(timezone.utc),
                last_searched_at=datetime.now(timezone.utc),
            ),
        ]
        db.add_all(searches)
        db.commit()

        # Count excluding deleted
        count = repo.count_searches(user_id=user.id, exclude_deleted=True)
        assert count == 2

        # Count including deleted
        count = repo.count_searches(user_id=user.id, exclude_deleted=False)
        assert count == 3

        # Count for non-existent user
        count = repo.count_searches(user_id=99999)
        assert count == 0

    def test_get_searches_to_delete(self, db: Session):
        """Test getting subquery for searches to keep."""
        repo = SearchHistoryRepository(db)
        import uuid

        unique_id = uuid.uuid4().hex[:8]
        guest_id = f"keep-test-{unique_id}"

        # Create 5 searches
        base_time = datetime.now(timezone.utc)
        for i in range(5):
            search = SearchHistory(
                guest_session_id=guest_id,
                search_query=f"query {i} {unique_id}",
                search_type="natural_language",
                first_searched_at=base_time - timedelta(minutes=i),
                last_searched_at=base_time - timedelta(minutes=i),
            )
            db.add(search)
        db.commit()

        # Get subquery for top 3 to keep
        keep_subquery = repo.get_searches_to_delete(guest_session_id=guest_id, keep_count=3)

        # Use subquery to find which would be kept
        kept_ids = db.query(keep_subquery).all()
        assert len(kept_ids) == 3

        # Verify they're the most recent
        kept_searches = (
            db.query(SearchHistory)
            .filter(SearchHistory.id.in_([id[0] for id in kept_ids]))
            .order_by(SearchHistory.last_searched_at.desc())
            .all()
        )

        assert kept_searches[0].search_query == f"query 0 {unique_id}"
        assert kept_searches[1].search_query == f"query 1 {unique_id}"
        assert kept_searches[2].search_query == f"query 2 {unique_id}"

    def test_soft_delete_old_searches(self, db: Session):
        """Test soft deleting searches not in keep list."""
        repo = SearchHistoryRepository(db)
        user_id = 1

        # Create user
        user = User(
            id=user_id,
            email="softdel@example.com",
            hashed_password="hash",
            full_name="SoftDel",
        )
        db.add(user)
        db.commit()

        # Create 5 searches
        for i in range(5):
            search = SearchHistory(
                user_id=user_id,
                search_query=f"query {i}",
                search_type="natural_language",
                first_searched_at=datetime.now(timezone.utc) - timedelta(minutes=i),
                last_searched_at=datetime.now(timezone.utc) - timedelta(minutes=i),
            )
            db.add(search)
        db.commit()

        # Get keep list (top 2)
        keep_subquery = repo.get_searches_to_delete(user_id=user_id, keep_count=2)

        # Soft delete others
        deleted_count = repo.soft_delete_old_searches(user_id=user_id, keep_ids_subquery=keep_subquery)
        db.commit()

        assert deleted_count == 3

        # Verify correct ones were deleted
        active = (
            db.query(SearchHistory).filter(SearchHistory.user_id == user_id, SearchHistory.deleted_at.is_(None)).all()
        )
        assert len(active) == 2
        assert active[0].search_query in ["query 0", "query 1"]

        deleted = (
            db.query(SearchHistory).filter(SearchHistory.user_id == user_id, SearchHistory.deleted_at.isnot(None)).all()
        )
        assert len(deleted) == 3

    def test_soft_delete_by_id(self, db: Session):
        """Test soft deleting a specific search."""
        repo = SearchHistoryRepository(db)

        # Create user and searches
        user = User(
            email="delbyid@example.com",
            hashed_password="hash",
            full_name="Del",
        )
        db.add(user)
        db.commit()

        search1 = SearchHistory(
            user_id=user.id,
            search_query="keep me",
            search_type="natural_language",
            first_searched_at=datetime.now(timezone.utc),
            last_searched_at=datetime.now(timezone.utc),
        )
        search2 = SearchHistory(
            user_id=user.id,
            search_query="delete me",
            search_type="natural_language",
            first_searched_at=datetime.now(timezone.utc),
            last_searched_at=datetime.now(timezone.utc),
        )
        db.add_all([search1, search2])
        db.commit()

        # Delete search2
        deleted = repo.soft_delete_by_id(search_id=search2.id, user_id=user.id)
        db.commit()

        assert deleted is True

        # Verify
        db.refresh(search1)
        db.refresh(search2)
        assert search1.deleted_at is None
        assert search2.deleted_at is not None

        # Try to delete non-existent
        deleted = repo.soft_delete_by_id(search_id=99999, user_id=user.id)
        assert deleted is False

        # Try to delete another user's search
        other_user = User(
            email="other@example.com",
            hashed_password="hash",
            full_name="Other",
        )
        db.add(other_user)
        db.commit()

        deleted = repo.soft_delete_by_id(search_id=search1.id, user_id=other_user.id)
        assert deleted is False

    def test_get_guest_searches_for_conversion(self, db: Session):
        """Test getting guest searches ready for conversion."""
        repo = SearchHistoryRepository(db)
        import uuid

        unique_id = uuid.uuid4().hex[:8]
        guest_id = f"convert-ready-{unique_id}"

        # Create a user for the converted search
        user = User(
            email=f"converted-{unique_id}@example.com",
            hashed_password="hash",
            full_name="Converted",
        )
        db.add(user)
        db.commit()

        # Create mix of searches
        searches = [
            # Should be included
            SearchHistory(
                guest_session_id=guest_id, search_query=f"convert 1 {unique_id}", search_type="natural_language"
            ),
            SearchHistory(
                guest_session_id=guest_id, search_query=f"convert 2 {unique_id}", search_type="natural_language"
            ),
            # Should be included - deleted searches are now converted too
            SearchHistory(
                guest_session_id=guest_id,
                search_query=f"deleted {unique_id}",
                search_type="natural_language",
                deleted_at=datetime.now(timezone.utc),
            ),
            # Should be excluded - already converted
            SearchHistory(
                guest_session_id=guest_id,
                search_query=f"converted {unique_id}",
                search_type="natural_language",
                converted_to_user_id=user.id,
                converted_at=datetime.now(timezone.utc),
            ),
        ]
        db.add_all(searches)
        db.commit()

        # Get convertible searches
        convertible = repo.get_guest_searches_for_conversion(guest_id)

        # Now includes deleted searches
        assert len(convertible) == 3
        assert convertible[0].search_query == f"convert 1 {unique_id}"
        assert convertible[1].search_query == f"convert 2 {unique_id}"
        assert convertible[2].search_query == f"deleted {unique_id}"

    def test_mark_searches_as_converted(self, db: Session):
        """Test marking guest searches as converted."""
        repo = SearchHistoryRepository(db)
        import uuid

        unique_id = uuid.uuid4().hex[:8]
        guest_id = f"mark-converted-{unique_id}"

        # Create a user
        user = User(
            email=f"mark-{unique_id}@example.com",
            hashed_password="hash",
            full_name="Mark",
        )
        db.add(user)
        db.commit()
        user_id = user.id

        # Create guest searches
        searches = []
        for i in range(3):
            search = SearchHistory(
                guest_session_id=guest_id, search_query=f"query {i} {unique_id}", search_type="natural_language"
            )
            db.add(search)
            searches.append(search)
        db.commit()

        # Mark as converted
        marked_count = repo.mark_searches_as_converted(guest_id, user_id)
        db.commit()

        assert marked_count == 3

        # Verify all marked
        for search in searches:
            db.refresh(search)
            assert search.converted_to_user_id == user_id
            assert search.converted_at is not None

        # Try again - should mark 0 (already converted)
        marked_count = repo.mark_searches_as_converted(guest_id, user_id)
        assert marked_count == 0

    def test_find_analytics_eligible_searches(self, db: Session):
        """Test finding searches for analytics."""
        repo = SearchHistoryRepository(db)
        import uuid

        unique_id = uuid.uuid4().hex[:8]

        # Create user
        user = User(
            email=f"analytics-{unique_id}@example.com",
            hashed_password="hash",
            full_name="Analytics",
        )
        db.add(user)
        db.commit()

        # Create various searches
        base_time = datetime.now(timezone.utc)
        searches = [
            # Regular user search
            SearchHistory(
                user_id=user.id,
                search_query=f"user search {unique_id}",
                search_type="natural_language",
                first_searched_at=base_time - timedelta(days=1),
                last_searched_at=base_time - timedelta(days=1),
            ),
            # Soft deleted search
            SearchHistory(
                user_id=user.id,
                search_query=f"deleted search {unique_id}",
                search_type="natural_language",
                deleted_at=base_time,
                first_searched_at=base_time - timedelta(days=2),
                last_searched_at=base_time - timedelta(days=2),
            ),
            # Converted guest search (should be excluded)
            SearchHistory(
                guest_session_id=f"guest-123-{unique_id}",
                search_query=f"converted guest {unique_id}",
                search_type="natural_language",
                converted_to_user_id=user.id,
                converted_at=base_time,
                first_searched_at=base_time - timedelta(days=3),
                last_searched_at=base_time - timedelta(days=3),
            ),
            # Non-converted guest search
            SearchHistory(
                guest_session_id=f"guest-456-{unique_id}",
                search_query=f"active guest {unique_id}",
                search_type="natural_language",
                first_searched_at=base_time - timedelta(days=1),
                last_searched_at=base_time - timedelta(days=1),
            ),
        ]
        db.add_all(searches)
        db.commit()

        # Query with deleted included
        query = repo.find_analytics_eligible_searches(include_deleted=True)
        # Filter to only our test data to avoid pollution
        results = query.filter(
            SearchHistory.search_query.in_(
                [
                    f"user search {unique_id}",
                    f"deleted search {unique_id}",
                    f"active guest {unique_id}"
                    # Note: converted guest should NOT appear
                ]
            )
        ).all()

        # Should have all 3 eligible searches
        assert len(results) == 3

        # Query without deleted
        query = repo.find_analytics_eligible_searches(include_deleted=False)
        results = query.filter(
            SearchHistory.search_query.in_([f"user search {unique_id}", f"active guest {unique_id}"])
        ).all()

        # Should have only non-deleted (excluding converted)
        assert len(results) == 2  # user search and active guest search

        # Query with date range
        query = repo.find_analytics_eligible_searches(start_date=base_time - timedelta(days=1.5), end_date=base_time)
        results = query.filter(
            SearchHistory.search_query.in_([f"user search {unique_id}", f"active guest {unique_id}"])
        ).all()

        # Should only include searches within date range
        assert len(results) == 2  # user search and active guest search

    def test_repository_inherits_base_methods(self, db: Session):
        """Test that repository inherits BaseRepository methods."""
        repo = SearchHistoryRepository(db)

        # Test create (inherited)
        search = repo.create(
            guest_session_id="test-inherit",
            search_query="inherited create",
            search_type="natural_language",
            results_count=5,
        )
        db.commit()

        assert search.id is not None
        assert search.search_query == "inherited create"

        # Test get_by_id (inherited)
        found = repo.get_by_id(search.id)
        assert found is not None
        assert found.id == search.id

        # Test exists (inherited)
        exists = repo.exists(id=search.id)
        assert exists is True

        # Test count (inherited)
        count = repo.count()
        assert count >= 1
