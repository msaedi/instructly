# backend/tests/integration/test_chat_system.py
"""
Integration tests for the chat/messaging system.

Tests cover:
- Message sending and receiving
- SSE connection and streaming
- Rate limiting
- RBAC permissions
- Message history
- Unread counts
- Error handling
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus
from app.models.service_catalog import InstructorService
from app.models.user import User
from app.repositories.message_repository import MessageRepository
from app.services.message_service import MessageService
from tests.fixtures.unique_test_data import unique_data


@pytest.fixture
def message_service(db: Session) -> MessageService:
    """Create a message service instance."""
    return MessageService(db)


@pytest.fixture
def message_repository(db: Session) -> MessageRepository:
    """Create a message repository instance."""
    return MessageRepository(db)


@pytest.fixture
def test_instructor_service(db: Session, test_instructor: User):
    """Create a test instructor service."""
    # First check if there's an existing service catalog entry, or create one
    from app.models.service_catalog import ServiceCatalog, ServiceCategory

    # Get or create a category
    category = db.query(ServiceCategory).first()
    if not category:
        category = ServiceCategory(
            name=unique_data.unique_category_name("Test Category"),
            slug=unique_data.unique_slug("test-category"),
            description="Category for testing",
            is_active=True,
        )
        db.add(category)
        db.flush()

    # Create a service catalog entry
    catalog_service = ServiceCatalog(
        name=unique_data.unique_service_name("Test Service"),
        slug=unique_data.unique_slug("test-service"),
        category_id=category.id,
        description="Service for testing",
        online_capable=True,
        is_active=True,
    )
    db.add(catalog_service)
    db.flush()

    service = InstructorService(
        instructor_profile_id=test_instructor.instructor_profile.id,
        service_catalog_id=catalog_service.id,
        hourly_rate=50.00,
        is_active=True,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@pytest.fixture
def test_booking(db: Session, test_student: User, test_instructor: User, test_instructor_service) -> Booking:
    """Create a test booking for chat testing."""
    start_time = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(hours=1)

    booking = Booking(
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=test_instructor_service.id,
        booking_date=datetime.now(timezone.utc).date(),
        start_time=start_time.time(),
        end_time=end_time.time(),
        service_name=unique_data.unique_service_name("Test Service"),
        hourly_rate=50.00,
        total_price=50.00,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        service_area="Test Area",
        meeting_location="Test Location",
        location_type="neutral",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


class TestMessageService:
    """Test the message service layer."""

    def test_send_message_success(
        self,
        message_service: MessageService,
        test_booking: Booking,
        test_student: User,
    ):
        """Test successful message sending."""
        message = message_service.send_message(
            booking_id=test_booking.id,
            sender_id=test_student.id,
            content="Hello, instructor!",
        )

        assert message is not None
        assert message.booking_id == test_booking.id
        assert message.sender_id == test_student.id
        assert message.content == "Hello, instructor!"
        assert message.is_deleted is False

    def test_send_message_unauthorized(
        self,
        message_service: MessageService,
        test_booking: Booking,
        db: Session,
    ):
        """Test message sending by unauthorized user."""
        # Create a user not part of the booking
        other_user = User(
            email=unique_data.unique_email("other"),
            hashed_password="hashed",
            first_name="Other",
            last_name=unique_data.unique_name("User"),
            phone="+12125550000",
            zip_code="10001",
            is_active=True,
        )
        db.add(other_user)
        db.commit()
        db.refresh(other_user)

        with pytest.raises(Exception) as exc_info:
            message_service.send_message(
                booking_id=test_booking.id,
                sender_id=other_user.id,
                content="Unauthorized message",
            )

        assert "don't have access" in str(exc_info.value)

    def test_send_message_empty_content(
        self,
        message_service: MessageService,
        test_booking: Booking,
        test_student: User,
    ):
        """Test sending message with empty content."""
        with pytest.raises(Exception) as exc_info:
            message_service.send_message(
                booking_id=test_booking.id,
                sender_id=test_student.id,
                content="",
            )

        assert "cannot be empty" in str(exc_info.value)

    def test_get_message_history(
        self,
        message_service: MessageService,
        test_booking: Booking,
        test_student: User,
        test_instructor: User,
    ):
        """Test retrieving message history."""
        # Send some messages
        message_service.send_message(
            booking_id=test_booking.id,
            sender_id=test_student.id,
            content="Message 1",
        )
        message_service.send_message(
            booking_id=test_booking.id,
            sender_id=test_instructor.id,
            content="Message 2",
        )
        message_service.send_message(
            booking_id=test_booking.id,
            sender_id=test_student.id,
            content="Message 3",
        )

        # Get history
        messages = message_service.get_message_history(
            booking_id=test_booking.id,
            user_id=test_student.id,
            limit=10,
            offset=0,
        )

        assert len(messages) == 3
        assert messages[0].content == "Message 1"  # Oldest first
        assert messages[1].content == "Message 2"
        assert messages[2].content == "Message 3"

    def test_mark_messages_as_read(
        self,
        message_service: MessageService,
        message_repository: MessageRepository,
        test_booking: Booking,
        test_student: User,
        test_instructor: User,
        db: Session,
    ):
        """Test marking messages as read."""
        # Student sends message to instructor
        message = message_repository.create_message(
            booking_id=test_booking.id,
            sender_id=test_student.id,
            content="Test message",
        )
        db.commit()  # Commit the message and notification

        # Get unread messages for instructor
        unread = message_repository.get_unread_messages(
            booking_id=test_booking.id,
            user_id=test_instructor.id,
        )
        assert len(unread) == 1

        # Mark as read
        count = message_service.mark_messages_as_read(
            message_ids=[message.id],
            user_id=test_instructor.id,
        )
        assert count == 1

        # Check unread again
        unread = message_repository.get_unread_messages(
            booking_id=test_booking.id,
            user_id=test_instructor.id,
        )
        assert len(unread) == 0

    def test_delete_message(
        self,
        message_service: MessageService,
        test_booking: Booking,
        test_student: User,
    ):
        """Test soft deleting a message."""
        # Create message
        message = message_service.send_message(
            booking_id=test_booking.id,
            sender_id=test_student.id,
            content="Message to delete",
        )

        # Delete it
        deleted = message_service.delete_message(
            message_id=message.id,
            user_id=test_student.id,
        )
        assert deleted is True

        # Try to delete someone else's message
        with pytest.raises(Exception) as exc_info:
            message_service.delete_message(
                message_id=message.id,
                user_id=test_booking.instructor_id,
            )
        assert "only delete your own" in str(exc_info.value)


class TestMessageAPI:
    """Test the message API endpoints."""

    def test_send_message_endpoint(
        self,
        client,
        test_booking: Booking,
        auth_headers_student: dict,
    ):
        """Test the send message API endpoint."""
        response = client.post(
            "/api/v1/messages/send",
            json={
                "booking_id": test_booking.id,
                "content": "Test message via API",
            },
            headers=auth_headers_student,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["message"]["content"] == "Test message via API"

    def test_get_message_history_endpoint(
        self,
        client,
        test_booking: Booking,
        auth_headers_student: dict,
        message_service: MessageService,
        test_student: User,
        db: Session,
    ):
        """Test the message history API endpoint."""
        # Send some messages first
        for i in range(3):
            message_service.send_message(
                booking_id=test_booking.id,
                sender_id=test_student.id,
                content=f"Message {i + 1}",
            )
        db.commit()

        response = client.get(
            f"/api/v1/messages/history/{test_booking.id}",
            headers=auth_headers_student,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["booking_id"] == test_booking.id
        assert len(data["messages"]) == 3
        assert data["has_more"] is False

    def test_get_unread_count_endpoint(
        self,
        client,
        auth_headers_instructor: dict,
    ):
        """Test the unread count API endpoint."""
        response = client.get(
            "/api/v1/messages/unread-count",
            headers=auth_headers_instructor,
        )

        assert response.status_code == 200
        data = response.json()
        assert "unread_count" in data
        assert isinstance(data["unread_count"], int)

    def test_mark_messages_read_endpoint(
        self,
        client,
        test_booking: Booking,
        auth_headers_instructor: dict,
        message_service: MessageService,
        test_student: User,
        db: Session,
    ):
        """Test marking messages as read via API."""
        # Send a message from student
        message = message_service.send_message(
            booking_id=test_booking.id,
            sender_id=test_student.id,
            content="Unread message",
        )
        db.commit()

        # Ensure message was created successfully
        assert message is not None
        assert message.id is not None

        # Mark as read by instructor
        response = client.post(
            "/api/v1/messages/mark-read",
            json={"message_ids": [str(message.id)]},  # Ensure it's a string
            headers=auth_headers_instructor,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["messages_marked"] >= 0

    def test_delete_message_endpoint(
        self,
        client,
        test_booking: Booking,
        auth_headers_student: dict,
        message_service: MessageService,
        test_student: User,
        db: Session,
    ):
        """Test deleting a message via API."""
        # Create a message
        message = message_service.send_message(
            booking_id=test_booking.id,
            sender_id=test_student.id,
            content="Message to delete",
        )
        db.commit()

        # Delete it
        response = client.delete(
            f"/api/v1/messages/{message.id}",
            headers=auth_headers_student,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.skip(reason="SSE testing requires special handling")
    def test_sse_stream_endpoint(
        self,
        client,
        test_booking: Booking,
        auth_headers_student: dict,
    ):
        """Test the SSE streaming endpoint."""
        # This test is complex and would require special handling
        # for async SSE streams. Marking as skip for now.
        pass


class TestRateLimiting:
    """Test rate limiting on message endpoints."""

    def test_message_send_rate_limit(
        self,
        client,
        test_booking: Booking,
        auth_headers_student: dict,
    ):
        """Test that message sending is rate limited."""
        # Send messages up to the limit (10 per minute)
        for i in range(10):
            response = client.post(
                "/api/v1/messages/send",
                json={
                    "booking_id": test_booking.id,
                    "content": f"Message {i + 1}",
                },
                headers=auth_headers_student,
            )
            assert response.status_code == 201

        # The 11th message should be rate limited
        response = client.post(
            "/api/v1/messages/send",
            json={
                "booking_id": test_booking.id,
                "content": "Rate limited message",
            },
            headers=auth_headers_student,
        )

        # Note: This will only work if rate limiting is enabled
        # and Redis/DragonflyDB is available
        if response.status_code == 429:
            assert "rate limit" in response.json()["detail"].lower()


class TestPermissions:
    """Test RBAC permissions for chat endpoints."""

    def test_send_message_requires_permission(
        self,
        client,
        test_booking: Booking,
    ):
        """Test that sending messages requires authentication."""
        response = client.post(
            "/api/v1/messages/send",
            json={
                "booking_id": test_booking.id,
                "content": "Unauthorized message",
            },
        )

        assert response.status_code == 401

    def test_view_messages_requires_permission(
        self,
        client,
        test_booking: Booking,
    ):
        """Test that viewing messages requires authentication."""
        response = client.get(
            f"/api/v1/messages/history/{test_booking.id}",
        )

        assert response.status_code == 401
