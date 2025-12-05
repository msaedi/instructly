#!/usr/bin/env python3
"""
Data migration script: Migrate messages to per-user-pair conversations.

This script:
1. Queries all existing messages grouped by booking
2. For each unique student-instructor pair, creates a Conversation record
3. Updates each message to set conversation_id
4. Creates system messages for booking creations (maintaining original timestamp)

IMPORTANT: Run this script after schema migration but before enforcing
the NOT NULL constraint on messages.conversation_id.

Usage:
    python scripts/migrate_messages_to_conversations.py [--dry-run] [--env int|stg|prod]

Options:
    --dry-run   Preview changes without committing
    --env       Database environment (default: int)
"""

import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
from typing import Dict, Set, Tuple

import ulid

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Now import app modules
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.models.conversation import Conversation
from app.models.message import (
    MESSAGE_TYPE_SYSTEM_BOOKING_CREATED,
    MESSAGE_TYPE_USER,
    Message,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_booking_participants(db: Session) -> list[dict]:
    """
    Get all unique student-instructor pairs from bookings.

    Returns list of dicts with:
    - booking_id
    - student_id
    - instructor_id
    - created_at (earliest booking date for this pair)
    """
    query = text("""
        SELECT DISTINCT
            b.id as booking_id,
            b.student_id,
            b.instructor_id,
            b.created_at
        FROM bookings b
        ORDER BY b.created_at ASC
    """)

    result = db.execute(query)
    return [dict(row._mapping) for row in result]


def get_messages_without_conversation(db: Session) -> list[Message]:
    """Get all messages that don't have a conversation_id set."""
    return (
        db.query(Message)
        .filter(Message.conversation_id.is_(None))
        .order_by(Message.created_at.asc())
        .all()
    )


def create_conversation_for_pair(
    db: Session,
    student_id: str,
    instructor_id: str,
    created_at: datetime,
) -> Conversation:
    """Create a new conversation for a student-instructor pair."""
    conversation = Conversation(
        id=str(ulid.ULID()),
        student_id=student_id,
        instructor_id=instructor_id,
    )
    # Use the original timestamp
    conversation.created_at = created_at
    conversation.updated_at = created_at

    db.add(conversation)
    db.flush()

    logger.debug(
        f"Created conversation {conversation.id} for pair "
        f"student={student_id}, instructor={instructor_id}"
    )
    return conversation


def create_system_booking_message(
    db: Session,
    conversation_id: str,
    booking_id: str,
    sender_id: str,
    booking_created_at: datetime,
) -> Message:
    """
    Create a system message announcing a booking was created.

    Uses the booking's created_at timestamp so it appears in chronological order.
    """
    # System message appears slightly before the booking time
    message = Message(
        id=str(ulid.ULID()),
        conversation_id=conversation_id,
        booking_id=booking_id,
        sender_id=sender_id,
        message_type=MESSAGE_TYPE_SYSTEM_BOOKING_CREATED,
        content="📅 A lesson has been booked",
        created_at=booking_created_at,
        updated_at=booking_created_at,
    )
    db.add(message)

    logger.debug(
        f"Created system booking message for booking {booking_id} "
        f"in conversation {conversation_id}"
    )
    return message


def migrate_messages_to_conversations(
    db: Session, dry_run: bool = False
) -> Dict[str, int]:
    """
    Main migration function.

    Returns stats dict with counts of actions taken.
    """
    stats = {
        "conversations_created": 0,
        "messages_updated": 0,
        "system_messages_created": 0,
        "errors": 0,
    }

    # Track conversations we've created: (student_id, instructor_id) -> conversation_id
    pair_to_conversation: Dict[Tuple[str, str], str] = {}

    # Track which bookings we've created system messages for
    bookings_with_system_messages: Set[str] = set()

    logger.info("Starting message migration to conversations...")

    # Step 1: Get all bookings and their participants
    logger.info("Step 1: Getting booking participants...")
    bookings = get_booking_participants(db)
    logger.info(f"Found {len(bookings)} bookings")

    # Step 2: Create conversations for unique pairs
    logger.info("Step 2: Creating conversations for unique student-instructor pairs...")

    for booking in bookings:
        student_id = booking["student_id"]
        instructor_id = booking["instructor_id"]
        booking_id = booking["booking_id"]
        booking_created_at = booking["created_at"]

        # Normalize pair (sorted tuple)
        pair = tuple(sorted([student_id, instructor_id]))

        if pair not in pair_to_conversation:
            try:
                # Create conversation
                conv = create_conversation_for_pair(
                    db, student_id, instructor_id, booking_created_at
                )
                pair_to_conversation[pair] = conv.id
                stats["conversations_created"] += 1

            except Exception as e:
                logger.error(f"Error creating conversation for pair {pair}: {e}")
                stats["errors"] += 1
                continue

        # Create system message for this booking if we haven't already
        if booking_id not in bookings_with_system_messages:
            try:
                conversation_id = pair_to_conversation[pair]
                create_system_booking_message(
                    db,
                    conversation_id,
                    booking_id,
                    instructor_id,  # Instructor is the "sender" of system messages
                    booking_created_at,
                )
                bookings_with_system_messages.add(booking_id)
                stats["system_messages_created"] += 1

            except Exception as e:
                logger.error(
                    f"Error creating system message for booking {booking_id}: {e}"
                )
                stats["errors"] += 1

    logger.info(f"Created {stats['conversations_created']} conversations")
    logger.info(f"Created {stats['system_messages_created']} system messages")

    # Step 3: Update existing messages to set conversation_id
    logger.info("Step 3: Updating existing messages with conversation_id...")

    messages = get_messages_without_conversation(db)
    logger.info(f"Found {len(messages)} messages without conversation_id")

    for message in messages:
        if not message.booking_id:
            logger.warning(f"Message {message.id} has no booking_id, skipping")
            continue

        try:
            # Get booking info to find the pair
            booking_query = text("""
                SELECT student_id, instructor_id
                FROM bookings
                WHERE id = :booking_id
            """)
            result = db.execute(booking_query, {"booking_id": message.booking_id})
            row = result.fetchone()

            if not row:
                logger.warning(
                    f"Booking {message.booking_id} not found for message {message.id}"
                )
                continue

            student_id = row.student_id
            instructor_id = row.instructor_id
            pair = tuple(sorted([student_id, instructor_id]))

            if pair not in pair_to_conversation:
                # This shouldn't happen if Step 2 was successful
                logger.error(f"No conversation found for pair {pair}")
                stats["errors"] += 1
                continue

            # Update message with conversation_id
            message.conversation_id = pair_to_conversation[pair]
            message.message_type = MESSAGE_TYPE_USER

            stats["messages_updated"] += 1

            if stats["messages_updated"] % 100 == 0:
                logger.info(f"Updated {stats['messages_updated']} messages...")

        except Exception as e:
            logger.error(f"Error updating message {message.id}: {e}")
            stats["errors"] += 1

    # Step 4: Update conversation last_message_at timestamps
    logger.info("Step 4: Updating conversation last_message_at timestamps...")

    for conv_id in set(pair_to_conversation.values()):
        try:
            # Find the most recent message in this conversation
            latest_msg = (
                db.query(Message)
                .filter(Message.conversation_id == conv_id)
                .order_by(Message.created_at.desc())
                .first()
            )

            if latest_msg:
                conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
                if conv:
                    conv.last_message_at = latest_msg.created_at
                    conv.updated_at = datetime.now(timezone.utc)

        except Exception as e:
            logger.error(f"Error updating last_message_at for conversation {conv_id}: {e}")
            stats["errors"] += 1

    # Commit or rollback
    if dry_run:
        logger.info("DRY RUN - Rolling back changes")
        db.rollback()
    else:
        logger.info("Committing changes...")
        db.commit()
        logger.info("Migration complete!")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Migrate messages to per-user-pair conversations"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without committing",
    )
    parser.add_argument(
        "--env",
        choices=["int", "stg", "prod"],
        default="int",
        help="Database environment (default: int)",
    )
    args = parser.parse_args()

    # Set environment variables for database selection
    import os

    if args.env == "stg":
        os.environ["USE_STG_DATABASE"] = "true"
    elif args.env == "prod":
        os.environ["USE_PROD_DATABASE"] = "true"
        # Production requires confirmation
        confirm = input(
            "⚠️  WARNING: You are about to modify PRODUCTION data.\n"
            "Type 'yes' to confirm: "
        )
        if confirm.lower() != "yes":
            logger.info("Aborting")
            sys.exit(1)

    logger.info(f"Using database environment: {args.env}")
    logger.info(f"Dry run: {args.dry_run}")

    # Get database session
    with get_db_session() as db:
        stats = migrate_messages_to_conversations(db, dry_run=args.dry_run)

    # Print summary
    logger.info("\n" + "=" * 50)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 50)
    logger.info(f"Conversations created: {stats['conversations_created']}")
    logger.info(f"System messages created: {stats['system_messages_created']}")
    logger.info(f"Messages updated: {stats['messages_updated']}")
    logger.info(f"Errors: {stats['errors']}")

    if stats["errors"] > 0:
        logger.warning("⚠️  Some errors occurred during migration")
        sys.exit(1)

    logger.info("✅ Migration completed successfully!")


if __name__ == "__main__":
    main()
