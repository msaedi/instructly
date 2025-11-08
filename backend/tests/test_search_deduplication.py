# backend/tests/test_search_deduplication.py
"""
Test the hybrid search history model with deduplication.

Tests that:
1. First search creates entry in both tables
2. Repeat search updates count/timestamp in search_history, new row in search_events
3. Delete search soft deletes in search_history only (events preserved)
4. Display order is by last_searched_at (most recent first)
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.search_event import SearchEvent
from app.models.search_history import SearchHistory
from app.models.user import User
from app.repositories.search_event_repository import SearchEventRepository
from app.repositories.search_history_repository import SearchHistoryRepository
from app.schemas.search_context import SearchUserContext
from app.services.search_history_service import SearchHistoryService


@pytest.fixture
def search_service(db: Session):
    """Create search history service."""
    return SearchHistoryService(db)


@pytest.fixture
def search_repository(db: Session):
    """Create search history repository."""
    return SearchHistoryRepository(db)


@pytest.fixture
def event_repository(db: Session):
    """Create search event repository."""
    return SearchEventRepository(db)


@pytest.fixture
def test_user(db: Session):
    """Create a test user."""
    user = User(
        email="test@example.com",
        first_name="Test",
        last_name="User",
        phone="+12125550000",
        zip_code="10001",
        hashed_password="hashed",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_search_deduplication(search_service, search_repository, event_repository, test_user, db):
    """Test that repeat searches are deduplicated in history but all recorded in events."""
    # Create context for a test user
    context = SearchUserContext.from_user(user_id=test_user.id, session_id="test-session-123")

    # First search for "piano lessons"
    search_data = {
        "search_query": "piano lessons",
        "search_type": "natural_language",
        "results_count": 5,
        "referrer": "/home",
    }

    # Record first search
    result1 = await search_service.record_search(context=context, search_data=search_data)

    # Verify search_history has 1 entry with count=1
    history_entries = (
        db.query(SearchHistory)
        .filter(SearchHistory.user_id == test_user.id, SearchHistory.search_query == "piano lessons")
        .all()
    )
    assert len(history_entries) == 1
    assert history_entries[0].search_count == 1
    assert history_entries[0].id == result1.id

    # Verify search_events has 1 entry
    event_entries = (
        db.query(SearchEvent)
        .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "piano lessons")
        .all()
    )
    assert len(event_entries) == 1

    # Record second search for same query
    result2 = await search_service.record_search(context=context, search_data=search_data)

    # Verify search_history still has 1 entry but count=2
    history_entries = (
        db.query(SearchHistory)
        .filter(SearchHistory.user_id == test_user.id, SearchHistory.search_query == "piano lessons")
        .all()
    )
    assert len(history_entries) == 1
    assert history_entries[0].search_count == 2
    assert history_entries[0].id == result1.id  # Same ID
    assert result2.id == result1.id  # Service returns same record

    # Verify search_events now has 2 entries
    event_entries = (
        db.query(SearchEvent)
        .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "piano lessons")
        .all()
    )
    assert len(event_entries) == 2

    # Record third search
    _result3 = await search_service.record_search(context=context, search_data=search_data)

    # Verify count is now 3
    history_entries = (
        db.query(SearchHistory)
        .filter(SearchHistory.user_id == test_user.id, SearchHistory.search_query == "piano lessons")
        .all()
    )
    assert len(history_entries) == 1
    assert history_entries[0].search_count == 3

    # Verify events has 3 entries
    event_entries = (
        db.query(SearchEvent)
        .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "piano lessons")
        .all()
    )
    assert len(event_entries) == 3


@pytest.mark.asyncio
async def test_timestamp_ordering(search_service, test_user, db):
    """Test that searches are ordered by last_searched_at."""
    context = SearchUserContext.from_user(user_id=test_user.id)

    # Create searches with time delays
    searches = ["guitar lessons", "piano lessons", "violin lessons"]

    for i, query in enumerate(searches):
        search_data = {"search_query": query, "search_type": "natural_language"}
        await search_service.record_search(context=context, search_data=search_data)

        # Manually update last_searched_at to ensure ordering
        search = (
            db.query(SearchHistory)
            .filter(SearchHistory.user_id == test_user.id, SearchHistory.search_query == query)
            .first()
        )
        search.last_searched_at = datetime.now(timezone.utc) - timedelta(hours=len(searches) - i)
        db.commit()

    # Get recent searches
    recent = search_service.get_recent_searches(context=context, limit=10)

    # Should be ordered by last_searched_at (most recent first)
    assert len(recent) == 3
    assert recent[0].search_query == "violin lessons"  # Most recent
    assert recent[1].search_query == "piano lessons"
    assert recent[2].search_query == "guitar lessons"  # Oldest

    # Now search for "guitar lessons" again
    await search_service.record_search(context=context, search_data={"search_query": "guitar lessons"})

    # Get recent searches again
    recent = search_service.get_recent_searches(context=context, limit=10)

    # Guitar lessons should now be first
    assert recent[0].search_query == "guitar lessons"
    assert recent[0].search_count == 2  # Incremented


@pytest.mark.asyncio
async def test_soft_delete_preserves_events(search_service, search_repository, event_repository, test_user, db):
    """Test that deleting a search only affects search_history, not events."""
    context = SearchUserContext.from_user(user_id=test_user.id)

    # Create a search
    search_data = {"search_query": "drum lessons", "search_type": "natural_language"}
    result = await search_service.record_search(context=context, search_data=search_data)

    # Verify both tables have the entry
    history = db.query(SearchHistory).filter(SearchHistory.id == result.id).first()
    assert history is not None
    assert history.deleted_at is None

    events_before = (
        db.query(SearchEvent)
        .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "drum lessons")
        .count()
    )
    assert events_before == 1

    # Delete the search
    deleted = search_service.delete_search(user_id=test_user.id, search_id=result.id)
    assert deleted is True

    # Verify search_history is soft deleted - reload from DB to see committed state
    db.expire_all()
    reloaded = db.get(SearchHistory, result.id)
    assert reloaded is not None
    assert reloaded.deleted_at is not None

    # Verify events are preserved
    events_after = (
        db.query(SearchEvent)
        .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "drum lessons")
        .count()
    )
    assert events_after == 1  # Still there

    # Verify deleted search doesn't appear in recent searches
    recent = search_service.get_recent_searches(context=context)
    assert len(recent) == 0


@pytest.mark.asyncio
async def test_guest_search_deduplication(search_service, db):
    """Test deduplication works for guest sessions too."""
    import uuid

    guest_id = f"guest-session-{str(uuid.uuid4())[:8]}"
    context = SearchUserContext.from_guest(guest_id, session_id="browser-session-789")

    # Record same search 3 times
    search_data = {"search_query": "swimming lessons", "search_type": "natural_language", "results_count": 8}

    for _ in range(3):
        await search_service.record_search(context=context, search_data=search_data)

    # Verify deduplication in search_history
    history = (
        db.query(SearchHistory)
        .filter(SearchHistory.guest_session_id == guest_id, SearchHistory.search_query == "swimming lessons")
        .all()
    )
    assert len(history) == 1
    assert history[0].search_count == 3

    # Verify all events recorded
    events = (
        db.query(SearchEvent)
        .filter(SearchEvent.guest_session_id == guest_id, SearchEvent.search_query == "swimming lessons")
        .all()
    )
    assert len(events) == 3

    # Verify session_id is recorded in events
    for event in events:
        assert event.session_id == "browser-session-789"


def test_search_analytics_data(event_repository):
    """Test that analytics repository can query event data."""
    # Get popular searches (would normally have more data)
    popular = event_repository.get_popular_searches(days=30, limit=10)
    assert isinstance(popular, list)

    # Get search patterns
    patterns = event_repository.get_search_patterns("piano lessons", days=30)
    assert isinstance(patterns, dict)
    assert "daily_counts" in patterns
    assert "type_distribution" in patterns
    assert "average_results" in patterns
