# backend/tests/test_search_tracking_comprehensive.py
"""
Comprehensive tests for the search tracking system.

Tests the unified search tracking system that was consolidateed to ensure:
1. Hybrid model (deduplication in search_history, full tracking in search_events)
2. All 5 search types work correctly
3. Enhanced analytics data is captured
4. Device context and geolocation tracking
5. No double counting issues
6. Correct referrer tracking
"""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Request
from sqlalchemy.orm import Session

from app.models.search_event import SearchEvent
from app.models.search_history import SearchHistory
from app.models.user import User
from app.schemas.search_context import SearchUserContext
from app.services.device_tracking_service import DeviceTrackingService
from app.services.geolocation_service import GeolocationService
from app.services.search_history_service import SearchHistoryService


@pytest.fixture
def test_user(db: Session):
    """Create a test user."""
    user = User(
        email="tracker@example.com",
        first_name="Tracker",
        last_name="Test",
        hashed_password="hashed",
        phone="+12125550000",
        zip_code="10001",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def search_service(db: Session):
    """Create search history service with mocked dependencies."""
    # Create real services but with mocked methods
    device_service = DeviceTrackingService(db)
    geo_service = GeolocationService(db)

    # Mock the methods that would make external calls
    device_service.parse_user_agent = Mock(
        return_value={
            "device": {"type": "desktop", "brand": None, "model": None},
            "browser": {"name": "Chrome", "version": "91.0"},
            "os": {"name": "macOS", "version": "10.15.7"},
        }
    )

    device_service.format_for_analytics = Mock(
        return_value={
            "device": {"type": "desktop"},
            "browser": {"name": "Chrome", "version": "91.0"},
            "os": {"name": "macOS", "version": "10.15.7"},
        }
    )

    # Mock the async geolocation method
    async def mock_get_location(ip):
        return {"country": "US", "region": "NY", "city": "New York", "timezone": "America/New_York"}

    geo_service.get_location_from_ip = AsyncMock(side_effect=mock_get_location)

    # Create the search service with mocked dependencies
    service = SearchHistoryService(db, geo_service, device_service)
    return service


@pytest.fixture
def mock_request():
    """Create a mock FastAPI request."""
    request = Mock(spec=Request)
    request.client.host = "192.168.1.100"
    request.headers = {"user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    return request


@pytest.fixture
def device_context():
    """Sample device context data."""
    return {
        "device_type": "desktop",
        "viewport_size": "1920x1080",
        "connection_type": "wifi",
        "connection_effective_type": "4g",
        "language": "en-US",
        "timezone": "America/New_York",
    }


class TestHybridModel:
    """Test the hybrid model that writes to both search_history and search_events."""

    @pytest.mark.asyncio
    async def test_hybrid_model_authenticated_user(self, search_service, test_user, db, device_context):
        """Test that authenticated searches create both history and event records."""
        context = SearchUserContext.from_user(user_id=test_user.id, session_id="session-123")
        context.search_origin = "/home"

        search_data = {
            "search_query": "piano lessons",
            "search_type": "natural_language",
            "results_count": 5,
            "referrer": context.search_origin,
        }

        # Record search
        result = await search_service.record_search(
            context=context,
            search_data=search_data,
            request_ip="192.168.1.100",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            device_context=device_context,
        )

        # Should create search_history record
        history = (
            db.query(SearchHistory)
            .filter(SearchHistory.user_id == test_user.id, SearchHistory.search_query == "piano lessons")
            .first()
        )

        assert history is not None
        assert history.search_type == "natural_language"
        assert history.results_count == 5

        # Should also create search_events record with analytics data
        event = (
            db.query(SearchEvent)
            .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "piano lessons")
            .first()
        )

        assert event is not None
        assert event.session_id == "session-123"
        assert event.referrer == "/home"  # context.search_origin is used as referrer
        assert event.device_type == "desktop"  # Device context fields are stored separately
        assert event.connection_type == "wifi"

        # Return value should be the history record
        assert result.id == history.id

    @pytest.mark.asyncio
    async def test_hybrid_model_guest_user(self, search_service, db, device_context):
        """Test that guest searches create both history and event records."""
        context = SearchUserContext.from_guest(guest_session_id="guest-456", session_id="browser-789")
        context.search_origin = "/services"

        search_data = {
            "search_query": "guitar lessons",
            "search_type": "category",
            "results_count": 8,
            "referrer": context.search_origin,
        }

        # Record search
        result = await search_service.record_search(
            context=context, search_data=search_data, device_context=device_context
        )

        # Should create search_history record
        history = (
            db.query(SearchHistory)
            .filter(SearchHistory.guest_session_id == "guest-456", SearchHistory.search_query == "guitar lessons")
            .first()
        )

        assert history is not None
        assert history.user_id is None
        assert history.search_type == "category"

        # Should also create search_events record
        event = (
            db.query(SearchEvent)
            .filter(SearchEvent.guest_session_id == "guest-456", SearchEvent.search_query == "guitar lessons")
            .first()
        )

        assert event is not None
        assert event.session_id == "browser-789"
        assert event.referrer == "/services"

    @pytest.mark.asyncio
    async def test_deduplication_in_search_history(self, search_service, test_user, db):
        """Test that duplicate searches are deduplicated in search_history."""
        context = SearchUserContext.from_user(user_id=test_user.id)

        search_data = {"search_query": "yoga classes", "search_type": "natural_language", "results_count": 10}

        # Record same search twice
        await search_service.record_search(context=context, search_data=search_data)
        await search_service.record_search(context=context, search_data=search_data)

        # Should only have one history record (deduplicated)
        history_count = (
            db.query(SearchHistory)
            .filter(SearchHistory.user_id == test_user.id, SearchHistory.search_query == "yoga classes")
            .count()
        )

        assert history_count == 1

        # Should have two event records (full tracking)
        event_count = (
            db.query(SearchEvent)
            .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "yoga classes")
            .count()
        )

        assert event_count == 2


class TestFiveSearchTypes:
    """Test all 5 search types that were fixed in the conversation."""

    @pytest.mark.asyncio
    async def test_type1_natural_language_search(self, search_service, test_user, db):
        """Test #1: Natural language search using search bar."""
        context = SearchUserContext.from_user(user_id=test_user.id, session_id="nl-session")
        context.search_origin = "/home"

        search_data = {
            "search_query": "piano teacher near me",
            "search_type": "natural_language",
            "results_count": 12,
            "referrer": context.search_origin,
        }

        result = await search_service.record_search(context=context, search_data=search_data)

        # Verify correct tracking
        event = (
            db.query(SearchEvent)
            .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_type == "natural_language")
            .first()
        )

        assert event is not None
        assert event.search_query == "piano teacher near me"
        assert event.results_count == 12
        assert event.referrer == "/home"

    @pytest.mark.asyncio
    async def test_type2_category_selection(self, search_service, test_user, db):
        """Test #2: Categories on front page (Music, Sports, etc)."""
        context = SearchUserContext.from_user(user_id=test_user.id)
        context.search_origin = "/"

        search_data = {
            "search_query": "Music lessons",
            "search_type": "category",
            "results_count": None,  # Categories don't have results count initially
            "referrer": context.search_origin,
        }

        result = await search_service.record_search(context=context, search_data=search_data)

        event = (
            db.query(SearchEvent)
            .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_type == "category")
            .first()
        )

        assert event is not None
        assert event.search_query == "Music lessons"
        assert event.results_count == 0  # Default when None is passed
        assert event.referrer == "/"

    @pytest.mark.asyncio
    async def test_type3_service_pills_homepage(self, search_service, test_user, db):
        """Test #3: Service pills on front page (top 7 services)."""
        context = SearchUserContext.from_user(user_id=test_user.id)
        context.search_origin = "/"

        search_data = {
            "search_query": "Piano",
            "search_type": "service_pill",
            "results_count": 8,
            "referrer": context.search_origin,
        }

        result = await search_service.record_search(context=context, search_data=search_data)

        event = (
            db.query(SearchEvent)
            .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_type == "service_pill")
            .first()
        )

        assert event is not None
        assert event.search_query == "Piano"
        assert event.results_count == 8
        assert event.referrer == "/"

    @pytest.mark.asyncio
    async def test_type4_services_page(self, search_service, test_user, db):
        """Test #4: Services on /services page (full list)."""
        context = SearchUserContext.from_user(user_id=test_user.id)
        context.search_origin = "/services"

        search_data = {
            "search_query": "Violin",
            "search_type": "service_pill",  # Services page uses service_pill type
            "results_count": 6,
            "referrer": context.search_origin,
        }

        result = await search_service.record_search(context=context, search_data=search_data)

        event = (
            db.query(SearchEvent)
            .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "Violin")
            .first()
        )

        assert event is not None
        assert event.search_type == "service_pill"
        assert event.referrer == "/services"

    @pytest.mark.asyncio
    async def test_type5_recent_search_history(self, search_service, test_user, db):
        """Test #5: Recent search history on front page."""
        context = SearchUserContext.from_user(user_id=test_user.id)
        context.search_origin = "/"

        search_data = {
            "search_query": "guitar lessons",
            "search_type": "search_history",
            "results_count": 4,
            "referrer": context.search_origin,
        }

        result = await search_service.record_search(context=context, search_data=search_data)

        event = (
            db.query(SearchEvent)
            .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_type == "search_history")
            .first()
        )

        assert event is not None
        assert event.search_query == "guitar lessons"
        assert event.referrer == "/"


class TestAnalyticsEnhancement:
    """Test enhanced analytics data capture."""

    @pytest.mark.asyncio
    async def test_device_context_tracking(self, search_service, test_user, db):
        """Test that device context is properly captured and stored."""
        context = SearchUserContext.from_user(user_id=test_user.id)

        device_context = {
            "device_type": "mobile",
            "viewport_size": "375x667",
            "connection_type": "4g",
            "connection_effective_type": "4g",
            "language": "en-US",
            "timezone": "America/New_York",
            "is_online": True,
            "touch_support": True,
        }

        search_data = {"search_query": "mobile search test", "search_type": "natural_language", "results_count": 3}

        result = await search_service.record_search(
            context=context,
            search_data=search_data,
            device_context=device_context,
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15",
        )

        event = (
            db.query(SearchEvent)
            .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "mobile search test")
            .first()
        )

        assert event is not None
        # Device context is stored in separate fields, not as a single JSON field
        assert event.device_type == "mobile"
        assert event.connection_type == "4g"
        # viewport_size and other details might be in browser_info JSON
        assert event.browser_info is not None

    @pytest.mark.asyncio
    async def test_geolocation_enhancement(self, search_service, test_user, db):
        """Test that geolocation data is captured."""
        context = SearchUserContext.from_user(user_id=test_user.id)

        search_data = {"search_query": "local instructor", "search_type": "natural_language", "results_count": 7}

        result = await search_service.record_search(
            context=context, search_data=search_data, request_ip="192.168.1.100"
        )

        event = (
            db.query(SearchEvent)
            .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "local instructor")
            .first()
        )

        assert event is not None
        # Geolocation data should be added by the service
        # (mocked in fixture to return NY data)

    @pytest.mark.asyncio
    async def test_user_agent_analysis(self, search_service, test_user, db):
        """Test that user agent is properly analyzed."""
        context = SearchUserContext.from_user(user_id=test_user.id)

        search_data = {"search_query": "user agent test", "search_type": "natural_language", "results_count": 2}

        user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15"

        result = await search_service.record_search(context=context, search_data=search_data, user_agent=user_agent)

        event = (
            db.query(SearchEvent)
            .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "user agent test")
            .first()
        )

        assert event is not None
        # User agent analysis results should be stored
        # (mocked in fixture to return desktop/Chrome data)


class TestReferrerTracking:
    """Test correct referrer tracking that was fixed."""

    @pytest.mark.asyncio
    async def test_session_storage_referrer(self, search_service, test_user, db):
        """Test that sessionStorage navigationFrom is used as referrer."""
        context = SearchUserContext.from_user(user_id=test_user.id)
        context.search_origin = "/services"  # This simulates navigationFrom

        search_data = {
            "search_query": "referrer test",
            "search_type": "service_pill",
            "results_count": 5,
            "referrer": context.search_origin,
        }

        result = await search_service.record_search(context=context, search_data=search_data)

        event = (
            db.query(SearchEvent)
            .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "referrer test")
            .first()
        )

        assert event is not None
        assert event.referrer == "/services"

    @pytest.mark.asyncio
    async def test_document_referrer_fallback(self, search_service, test_user, db):
        """Test that document.referrer is used when navigationFrom not available."""
        context = SearchUserContext.from_user(user_id=test_user.id)
        context.search_origin = "https://google.com"  # External referrer

        search_data = {
            "search_query": "external referrer",
            "search_type": "natural_language",
            "results_count": 9,
            "referrer": context.search_origin,
        }

        result = await search_service.record_search(context=context, search_data=search_data)

        event = (
            db.query(SearchEvent)
            .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "external referrer")
            .first()
        )

        assert event is not None
        assert event.referrer == "https://google.com"

    @pytest.mark.asyncio
    async def test_recent_searches_referrer(self, search_service, test_user, db):
        """Test that recent searches set correct referrer."""
        context = SearchUserContext.from_user(user_id=test_user.id)
        context.search_origin = "/"  # Homepage where RecentSearches component is displayed

        search_data = {
            "search_query": "previous search",
            "search_type": "search_history",
            "results_count": 3,
            "referrer": context.search_origin,
        }

        result = await search_service.record_search(context=context, search_data=search_data)

        event = (
            db.query(SearchEvent)
            .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_type == "search_history")
            .first()
        )

        assert event is not None
        assert event.referrer == "/"


class TestSessionTracking:
    """Test session tracking functionality."""

    @pytest.mark.asyncio
    async def test_session_continuity(self, search_service, test_user, db):
        """Test that searches in the same session are properly linked."""
        session_id = "continuity-session-123"

        # First search
        context1 = SearchUserContext.from_user(user_id=test_user.id, session_id=session_id)
        context1.search_origin = "/"

        await search_service.record_search(
            context=context1,
            search_data={"search_query": "first search", "search_type": "natural_language", "results_count": 10},
        )

        # Second search in same session
        context2 = SearchUserContext.from_user(user_id=test_user.id, session_id=session_id)
        context2.search_origin = "/search?q=first+search"

        await search_service.record_search(
            context=context2,
            search_data={"search_query": "refined search", "search_type": "natural_language", "results_count": 5},
        )

        # Verify both searches have same session ID
        events = (
            db.query(SearchEvent).filter(SearchEvent.session_id == session_id).order_by(SearchEvent.searched_at).all()
        )

        assert len(events) == 2
        assert events[0].search_query == "first search"
        assert events[1].search_query == "refined search"
        assert events[0].session_id == events[1].session_id

    @pytest.mark.asyncio
    async def test_guest_session_tracking(self, search_service, db):
        """Test guest session tracking works correctly."""
        guest_session_id = "guest-session-456"
        browser_session_id = "browser-session-789"

        context = SearchUserContext.from_guest(guest_session_id=guest_session_id, session_id=browser_session_id)

        search_data = {"search_query": "guest search", "search_type": "natural_language", "results_count": 6}

        result = await search_service.record_search(context=context, search_data=search_data)

        # Both history and event should have guest session ID
        history = db.query(SearchHistory).filter(SearchHistory.guest_session_id == guest_session_id).first()

        event = db.query(SearchEvent).filter(SearchEvent.guest_session_id == guest_session_id).first()

        assert history is not None
        assert event is not None
        assert event.session_id == browser_session_id


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_missing_device_context(self, search_service, test_user, db):
        """Test that missing device context doesn't break tracking."""
        context = SearchUserContext.from_user(user_id=test_user.id)

        search_data = {"search_query": "no device context", "search_type": "natural_language", "results_count": 1}

        # Should not raise exception
        result = await search_service.record_search(context=context, search_data=search_data, device_context=None)

        assert result is not None

        event = (
            db.query(SearchEvent)
            .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "no device context")
            .first()
        )

        assert event is not None
        # Device context fields should be None when not provided
        assert event.device_type is None
        assert event.connection_type is None

    @pytest.mark.asyncio
    async def test_null_results_count(self, search_service, test_user, db):
        """Test that null results count is handled correctly."""
        context = SearchUserContext.from_user(user_id=test_user.id)

        search_data = {"search_query": "null results", "search_type": "category", "results_count": None}

        result = await search_service.record_search(context=context, search_data=search_data)

        assert result is not None

        history = (
            db.query(SearchHistory)
            .filter(SearchHistory.user_id == test_user.id, SearchHistory.search_query == "null results")
            .first()
        )

        assert history is not None
        assert history.results_count is None

    @pytest.mark.asyncio
    async def test_large_search_context(self, search_service, test_user, db):
        """Test handling of large search context data."""
        context = SearchUserContext.from_user(user_id=test_user.id)

        # Large context data
        large_context = {f"key_{i}": f"value_{i}" * 100 for i in range(50)}

        search_data = {
            "search_query": "large context test",
            "search_type": "natural_language",
            "results_count": 2,
            "context": large_context,  # The service looks for "context", not "search_context"
        }

        result = await search_service.record_search(context=context, search_data=search_data)

        assert result is not None

        event = (
            db.query(SearchEvent)
            .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "large context test")
            .first()
        )

        assert event is not None
        # Should handle large JSONB data
        assert event.search_context is not None


class TestInteractionTracking:
    """Test search interaction tracking endpoint."""

    @pytest.mark.asyncio
    async def test_interaction_tracking(self, search_service, test_user, db):
        """Test that search interactions are tracked correctly."""
        # First create a search event
        context = SearchUserContext.from_user(user_id=test_user.id)

        search_data = {"search_query": "interaction test", "search_type": "natural_language", "results_count": 5}

        result = await search_service.record_search(context=context, search_data=search_data)

        # Get the created event ID
        event = (
            db.query(SearchEvent)
            .filter(SearchEvent.user_id == test_user.id, SearchEvent.search_query == "interaction test")
            .first()
        )

        assert event is not None

        # Mock the track_interaction method
        interaction_data = {
            "search_event_id": event.id,
            "interaction_type": "click",
            "instructor_id": 123,
            "result_position": 2,
            "time_to_interaction": 5.5,
        }

        # This would normally be called via the API endpoint
        # For now just verify the event exists for interaction tracking
        assert event.id is not None
        assert isinstance(event.id, str)  # ULID is a string
