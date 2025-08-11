# backend/tests/test_search_tracking.py
"""
Test session and referrer tracking in search analytics.

Tests that session IDs and referrer headers are properly captured
and stored in the search_events table.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.search_event import SearchEvent
from app.models.user import User
from app.schemas.search_context import SearchUserContext
from app.services.search_history_service import SearchHistoryService


@pytest.fixture
def test_user(db: Session):
    """Create a test user."""
    user = User(
        email="tracker@example.com",
        first_name="Tracker",
        last_name="Test",
        phone="+12125550000",
        zip_code="10001",
        hashed_password="hashed",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def search_service(db: Session):
    """Create search history service."""
    return SearchHistoryService(db)


@pytest.mark.asyncio
async def test_session_id_tracking(search_service, test_user, db):
    """Test that session IDs are properly tracked in search events."""
    # Create context with session ID
    session_id = "test-browser-session-123"
    context = SearchUserContext.from_user(user_id=test_user.id, session_id=session_id)

    # Record a search
    search_data = {"search_query": "guitar lessons", "search_type": "natural_language", "results_count": 15}

    await search_service.record_search(context=context, search_data=search_data)

    # Verify session ID is stored in search_events
    event = (
        db.query(SearchEvent)
        .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "guitar lessons")
        .first()
    )

    assert event is not None
    assert event.session_id == session_id


@pytest.mark.asyncio
async def test_referrer_tracking(search_service, test_user, db):
    """Test that referrer headers are properly tracked."""
    # Create context with search origin
    context = SearchUserContext.from_user(user_id=test_user.id)
    context.search_origin = "/services/music"

    # Record a search with referrer
    search_data = {
        "search_query": "piano teacher",
        "search_type": "natural_language",
        "results_count": 8,
        "referrer": context.search_origin,
    }

    await search_service.record_search(context=context, search_data=search_data)

    # Verify referrer is stored
    event = (
        db.query(SearchEvent)
        .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "piano teacher")
        .first()
    )

    assert event is not None
    assert event.referrer == "/services/music"


@pytest.mark.asyncio
async def test_service_pill_tracking(search_service, test_user, db):
    """Test that service pill clicks are tracked with origin page."""
    context = SearchUserContext.from_user(user_id=test_user.id)
    context.search_origin = "/home"

    # Record a service pill click
    search_data = {
        "search_query": "Yoga",
        "search_type": "service_pill",
        "results_count": 0,  # Pills don't know results yet
        "referrer": context.search_origin,
        "context": {"pill_location": "homepage_popular", "position": 3},
    }

    await search_service.record_search(context=context, search_data=search_data)

    # Verify it's tracked as service_pill with context
    event = (
        db.query(SearchEvent).filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "Yoga").first()
    )

    assert event is not None
    assert event.search_type == "service_pill"
    assert event.referrer == "/home"
    assert event.search_context is not None
    assert event.search_context["pill_location"] == "homepage_popular"


@pytest.mark.asyncio
async def test_guest_session_tracking(search_service, db):
    """Test that guest sessions are tracked properly."""
    guest_session_id = "guest-abc-123"
    browser_session_id = "browser-xyz-789"

    context = SearchUserContext.from_guest(guest_session_id=guest_session_id, session_id=browser_session_id)
    context.search_origin = "/search"

    # Record guest search
    search_data = {
        "search_query": "swimming instructor",
        "search_type": "natural_language",
        "results_count": 12,
        "referrer": context.search_origin,
    }

    await search_service.record_search(context=context, search_data=search_data)

    # Verify both session IDs are tracked
    event = (
        db.query(SearchEvent)
        .filter(SearchEvent.guest_session_id == guest_session_id, SearchEvent.search_query == "swimming instructor")
        .first()
    )

    assert event is not None
    assert event.session_id == browser_session_id
    assert event.guest_session_id == guest_session_id
    assert event.referrer == "/search"


@pytest.mark.asyncio
async def test_search_journey_tracking(search_service, test_user, db):
    """Test that we can track a complete search journey."""
    session_id = "journey-session-456"

    # User starts on homepage
    context1 = SearchUserContext.from_user(user_id=test_user.id, session_id=session_id)
    context1.search_origin = "/home"

    # First search from homepage
    await search_service.record_search(
        context=context1,
        search_data={
            "search_query": "music lessons",
            "search_type": "natural_language",
            "results_count": 25,
            "referrer": context1.search_origin,
        },
    )

    # User navigates to services page and searches again
    context2 = SearchUserContext.from_user(user_id=test_user.id, session_id=session_id)
    context2.search_origin = "/services"

    await search_service.record_search(
        context=context2,
        search_data={
            "search_query": "piano lessons manhattan",
            "search_type": "natural_language",
            "results_count": 8,
            "referrer": context2.search_origin,
        },
    )

    # User clicks a service pill
    context3 = SearchUserContext.from_user(user_id=test_user.id, session_id=session_id)
    context3.search_origin = "/search?q=piano+lessons+manhattan"

    await search_service.record_search(
        context=context3,
        search_data={
            "search_query": "Piano",
            "search_type": "service_pill",
            "results_count": 5,
            "referrer": context3.search_origin,
        },
    )

    # Verify we can reconstruct the journey
    events = db.query(SearchEvent).filter(SearchEvent.session_id == session_id).order_by(SearchEvent.searched_at).all()

    assert len(events) == 3

    # First search from homepage
    assert events[0].search_query == "music lessons"
    assert events[0].referrer == "/home"

    # Refined search from services
    assert events[1].search_query == "piano lessons manhattan"
    assert events[1].referrer == "/services"

    # Service pill click from search results
    assert events[2].search_query == "Piano"
    assert events[2].search_type == "service_pill"
    assert events[2].referrer == "/search?q=piano+lessons+manhattan"


@pytest.mark.asyncio
async def test_search_context_storage(search_service, test_user, db):
    """Test that additional search context is properly stored."""
    context = SearchUserContext.from_user(user_id=test_user.id)

    # Record search with rich context
    search_data = {
        "search_query": "yoga near central park",
        "search_type": "natural_language",
        "results_count": 7,
        "context": {
            "viewport": "1920x1080",
            "device": "desktop",
            "filters_applied": {"location": "central_park", "price_range": "50-100"},
            "search_timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

    await search_service.record_search(context=context, search_data=search_data)

    # Verify context is stored as JSONB
    event = (
        db.query(SearchEvent)
        .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "yoga near central park")
        .first()
    )

    assert event is not None
    assert event.search_context is not None
    assert event.search_context["viewport"] == "1920x1080"
    assert event.search_context["device"] == "desktop"
    assert event.search_context["filters_applied"]["location"] == "central_park"
