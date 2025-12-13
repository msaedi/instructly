"""
Tests for Conversation Repository.

Tests the per-user-pair conversation architecture:
- Finding conversations by user pairs
- Get-or-create idempotency
- Listing conversations for a user
- Updating conversation metadata
"""

from datetime import datetime, timedelta, timezone

from app.models.conversation import Conversation
from app.repositories.conversation_repository import ConversationRepository


class TestConversationRepositoryFindByPair:
    """Tests for finding conversations by student-instructor pair."""

    def test_find_by_pair_returns_conversation_if_exists(
        self, db, test_student, test_instructor_with_availability
    ):
        """Should find conversation when it exists for the pair."""
        repo = ConversationRepository(db)

        # Create a conversation
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.commit()

        # Find it
        found = repo.find_by_pair(
            test_student.id, test_instructor_with_availability.id
        )

        assert found is not None
        assert found.id == conversation.id
        assert found.student_id == test_student.id
        assert found.instructor_id == test_instructor_with_availability.id

    def test_find_by_pair_returns_none_if_not_exists(
        self, db, test_student, test_instructor_with_availability
    ):
        """Should return None when no conversation exists for the pair."""
        repo = ConversationRepository(db)

        # Try to find a non-existent conversation
        found = repo.find_by_pair(
            test_student.id, test_instructor_with_availability.id
        )

        assert found is None

    def test_find_by_pair_is_symmetric(
        self, db, test_student, test_instructor_with_availability
    ):
        """Should find conversation regardless of argument order."""
        repo = ConversationRepository(db)

        # Create a conversation with student_id and instructor_id
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.commit()

        # Find with arguments in both orders
        found1 = repo.find_by_pair(
            test_student.id, test_instructor_with_availability.id
        )
        found2 = repo.find_by_pair(
            test_instructor_with_availability.id, test_student.id
        )

        # Both should find the same conversation
        assert found1 is not None
        assert found2 is not None
        assert found1.id == found2.id


class TestConversationRepositoryGetOrCreate:
    """Tests for get-or-create functionality."""

    def test_get_or_create_creates_new_conversation(
        self, db, test_student, test_instructor_with_availability
    ):
        """Should create a new conversation if none exists."""
        repo = ConversationRepository(db)

        # Get or create
        conversation, created = repo.get_or_create(
            test_student.id, test_instructor_with_availability.id
        )
        db.commit()

        assert created is True
        assert conversation is not None
        assert conversation.student_id == test_student.id
        assert conversation.instructor_id == test_instructor_with_availability.id
        assert conversation.id is not None

    def test_get_or_create_returns_existing_conversation(
        self, db, test_student, test_instructor_with_availability
    ):
        """Should return existing conversation if one exists."""
        repo = ConversationRepository(db)

        # Create a conversation first
        existing = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(existing)
        db.commit()

        # Get or create should return the existing one
        conversation, created = repo.get_or_create(
            test_student.id, test_instructor_with_availability.id
        )

        assert created is False
        assert conversation.id == existing.id

    def test_get_or_create_is_idempotent(
        self, db, test_student, test_instructor_with_availability
    ):
        """Multiple calls should return the same conversation."""
        repo = ConversationRepository(db)

        # Call get_or_create multiple times
        conv1, created1 = repo.get_or_create(
            test_student.id, test_instructor_with_availability.id
        )
        db.commit()

        conv2, created2 = repo.get_or_create(
            test_student.id, test_instructor_with_availability.id
        )
        db.commit()

        conv3, created3 = repo.get_or_create(
            test_instructor_with_availability.id, test_student.id
        )
        db.commit()

        # First should create, rest should find
        assert created1 is True
        assert created2 is False
        assert created3 is False

        # All should be the same conversation
        assert conv1.id == conv2.id == conv3.id


class TestConversationRepositoryFindForUser:
    """Tests for finding conversations for a user."""

    def test_find_for_user_returns_user_conversations(
        self, db, test_student, test_instructor_with_availability
    ):
        """Should return all conversations where user is a participant."""
        repo = ConversationRepository(db)

        # Create a conversation
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.commit()

        # Find for student
        student_convos = repo.find_for_user(test_student.id)
        assert len(student_convos) == 1
        assert student_convos[0].id == conversation.id

        # Find for instructor
        instructor_convos = repo.find_for_user(test_instructor_with_availability.id)
        assert len(instructor_convos) == 1
        assert instructor_convos[0].id == conversation.id

    def test_find_for_user_returns_empty_if_no_conversations(
        self, db, test_student
    ):
        """Should return empty list if user has no conversations."""
        repo = ConversationRepository(db)

        conversations = repo.find_for_user(test_student.id)

        assert conversations == []

    def test_find_for_user_respects_limit(
        self, db, test_student, test_instructor_with_availability, test_instructor_2
    ):
        """Should respect the limit parameter."""
        repo = ConversationRepository(db)

        # Create two conversations for the student using two different instructors
        conv1 = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            last_message_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        conv2 = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_2.id,
            last_message_at=datetime.now(timezone.utc),
        )
        db.add_all([conv1, conv2])
        db.commit()

        # Limit to 1
        conversations = repo.find_for_user(test_student.id, limit=1)
        assert len(conversations) == 1
        # Should be the most recent (conv2)
        assert conversations[0].id == conv2.id

    def test_find_for_user_orders_by_last_message_at(
        self, db, test_student, test_instructor_with_availability, test_instructor_2
    ):
        """Should order conversations by last_message_at descending."""
        repo = ConversationRepository(db)

        # Create conversations with different last_message_at
        older_conv = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            last_message_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        newer_conv = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_2.id,
            last_message_at=datetime.now(timezone.utc),
        )
        db.add_all([older_conv, newer_conv])
        db.commit()

        # Find all
        conversations = repo.find_for_user(test_student.id)

        # Should be ordered newest first
        assert len(conversations) == 2
        assert conversations[0].id == newer_conv.id
        assert conversations[1].id == older_conv.id


class TestConversationRepositoryCountForUser:
    """Tests for counting conversations for a user."""

    def test_count_for_user_returns_correct_count(
        self, db, test_student, test_instructor_with_availability, test_instructor_2
    ):
        """Should return correct count of conversations."""
        repo = ConversationRepository(db)

        # Start with 0
        assert repo.count_for_user(test_student.id) == 0

        # Create one conversation
        conv1 = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conv1)
        db.commit()

        assert repo.count_for_user(test_student.id) == 1

        # Create another with different instructor
        conv2 = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_2.id,
        )
        db.add(conv2)
        db.commit()

        assert repo.count_for_user(test_student.id) == 2


class TestConversationRepositoryUpdateLastMessageAt:
    """Tests for updating last_message_at timestamp."""

    def test_update_last_message_at_with_timestamp(
        self, db, test_student, test_instructor_with_availability
    ):
        """Should update last_message_at with provided timestamp."""
        repo = ConversationRepository(db)

        # Create conversation
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.commit()

        # Update with specific timestamp
        specific_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        updated = repo.update_last_message_at(conversation.id, specific_time)

        assert updated is not None
        assert updated.last_message_at == specific_time

    def test_update_last_message_at_defaults_to_now(
        self, db, test_student, test_instructor_with_availability
    ):
        """Should default to current time if no timestamp provided."""
        repo = ConversationRepository(db)

        # Create conversation
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.commit()

        before = datetime.now(timezone.utc)

        # Update without timestamp
        updated = repo.update_last_message_at(conversation.id)

        after = datetime.now(timezone.utc)

        assert updated is not None
        assert updated.last_message_at is not None
        assert before <= updated.last_message_at <= after

    def test_update_last_message_at_returns_none_for_nonexistent(
        self, db
    ):
        """Should return None for non-existent conversation."""
        repo = ConversationRepository(db)

        result = repo.update_last_message_at("nonexistent-id")

        assert result is None


class TestConversationRepositoryMiscMethods:
    """Tests for miscellaneous repository methods."""

    def test_find_by_user_pair_ids(
        self, db, test_student, test_instructor_with_availability
    ):
        """Should find conversation by any two user IDs."""
        repo = ConversationRepository(db)

        # Create conversation
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.commit()

        # Find by user pair IDs (order shouldn't matter)
        found1 = repo.find_by_user_pair_ids(
            test_student.id, test_instructor_with_availability.id
        )
        found2 = repo.find_by_user_pair_ids(
            test_instructor_with_availability.id, test_student.id
        )

        assert found1 is not None
        assert found2 is not None
        assert found1.id == found2.id == conversation.id

    def test_get_with_participant_info_loads_relationships(
        self, db, test_student, test_instructor_with_availability
    ):
        """Should eagerly load student and instructor relationships."""
        repo = ConversationRepository(db)

        # Create conversation
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.commit()

        # Get with participant info
        conv_with_info = repo.get_with_participant_info(conversation.id)

        assert conv_with_info is not None
        # Relationships should be loaded
        assert conv_with_info.student is not None
        assert conv_with_info.instructor is not None
        assert conv_with_info.student.id == test_student.id
        assert conv_with_info.instructor.id == test_instructor_with_availability.id


class TestConversationModelMethods:
    """Tests for Conversation model helper methods."""

    def test_get_other_user_id(
        self, db, test_student, test_instructor_with_availability
    ):
        """Should return the other participant's ID."""
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.commit()

        # From student's perspective
        assert conversation.get_other_user_id(test_student.id) == test_instructor_with_availability.id

        # From instructor's perspective
        assert conversation.get_other_user_id(test_instructor_with_availability.id) == test_student.id

    def test_is_participant(
        self, db, test_student, test_instructor_with_availability, test_instructor_2
    ):
        """Should correctly identify participants."""
        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.commit()

        # Participants
        assert conversation.is_participant(test_student.id) is True
        assert conversation.is_participant(test_instructor_with_availability.id) is True

        # Non-participant (test_instructor_2 is not in this conversation)
        assert conversation.is_participant(test_instructor_2.id) is False
