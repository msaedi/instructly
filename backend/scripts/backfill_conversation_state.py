"""Backfill conversation_state from existing messages.

This script populates the conversation_state table for any existing bookings
that have messages. It computes:
- Last message metadata (id, preview, timestamp, sender)
- Unread counts for instructor and student

Usage:
    python scripts/backfill_conversation_state.py
"""

from sqlalchemy import func
import ulid

from app.database import SessionLocal
from app.models import Booking, ConversationState, Message


def backfill():
    """Backfill conversation_state for all bookings with messages."""
    db = SessionLocal()
    try:
        print("Starting conversation_state backfill...")

        # Get all bookings with messages
        bookings_with_messages = (
            db.query(
                Message.booking_id,
                Booking.instructor_id,
                Booking.student_id,
            )
            .join(Booking, Message.booking_id == Booking.id)
            .group_by(Message.booking_id, Booking.instructor_id, Booking.student_id)
            .all()
        )

        print(f"Found {len(bookings_with_messages)} bookings with messages")

        for booking_id, instructor_id, student_id in bookings_with_messages:
            # Get latest message
            latest = (
                db.query(Message)
                .filter(Message.booking_id == booking_id)
                .order_by(Message.created_at.desc())
                .first()
            )

            # Count unread messages for instructor (sent by student)
            # Note: This counts ALL messages from student as unread since we don't
            # have historical read state. In production, the trigger handles this.
            instructor_unread = (
                db.query(func.count(Message.id))
                .filter(
                    Message.booking_id == booking_id,
                    Message.sender_id == student_id,
                )
                .scalar()
            ) or 0

            # Count unread messages for student (sent by instructor)
            student_unread = (
                db.query(func.count(Message.id))
                .filter(
                    Message.booking_id == booking_id,
                    Message.sender_id == instructor_id,
                )
                .scalar()
            ) or 0

            # Check if conversation_state already exists
            existing = (
                db.query(ConversationState)
                .filter(ConversationState.booking_id == booking_id)
                .first()
            )

            if existing:
                # Update existing record
                existing.instructor_unread_count = instructor_unread
                existing.student_unread_count = student_unread
                existing.last_message_id = latest.id if latest else None
                existing.last_message_preview = latest.content[:100] if latest else None
                existing.last_message_at = latest.created_at if latest else None
                existing.last_message_sender_id = latest.sender_id if latest else None
                print(f"  Updated conversation_state for booking {booking_id}")
            else:
                # Create new conversation_state record
                state = ConversationState(
                    id=str(ulid.ULID()),
                    booking_id=booking_id,
                    instructor_id=instructor_id,
                    student_id=student_id,
                    instructor_unread_count=instructor_unread,
                    student_unread_count=student_unread,
                    last_message_id=latest.id if latest else None,
                    last_message_preview=latest.content[:100] if latest else None,
                    last_message_at=latest.created_at if latest else None,
                    last_message_sender_id=latest.sender_id if latest else None,
                )
                db.add(state)
                print(f"  Created conversation_state for booking {booking_id}")

        db.commit()
        print(f"\nBackfill complete! Processed {len(bookings_with_messages)} conversation states")

    except Exception as e:
        print(f"Error during backfill: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    backfill()
