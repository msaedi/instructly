#!/usr/bin/env python3
"""
Test script to create notifications for UI testing.

Usage:
    python test_notification_inbox.py <user_email>
    python test_notification_inbox.py stg <user_email>
    python test_notification_inbox.py preview <user_email>

Defaults to stg when no mode is provided.

Example:
    python test_notification_inbox.py sarah.chen@example.com
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import sys

# Add backend to path
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Load backend/.env so lowercase keys are available when running directly
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(BACKEND_DIR / ".env.render", override=False)
except Exception:
    pass

_SUPPORTED_MODES = {"int", "stg", "preview", "prod"}
_MODE_TO_SITE = {"int": "int", "stg": "local", "preview": "preview", "prod": "prod"}
_NON_INT_SITE_MODES = {
    "preview",
    "prod",
    "production",
    "beta",
    "live",
    "stg",
    "stage",
    "staging",
    "local",
}


def _resolve_mode(argv: list[str]) -> tuple[str | None, list[str]]:
    if argv and argv[0].strip().lower() in _SUPPORTED_MODES:
        return argv[0].strip().lower(), argv[1:]
    return None, argv


def _apply_site_mode(mode: str | None) -> None:
    if mode:
        os.environ["SITE_MODE"] = _MODE_TO_SITE[mode]
        return

    current = (os.getenv("SITE_MODE") or "").strip().lower()
    if current in _NON_INT_SITE_MODES:
        return

    os.environ["SITE_MODE"] = "local"


MODE_ARG, ARGS = _resolve_mode(sys.argv[1:])
_apply_site_mode(MODE_ARG)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ulid import ULID

from app.core.config import settings
from app.models.notification import Notification
from app.models.user import User
from app.repositories.notification_repository import NotificationRepository


def create_test_notifications(email: str):
    """Create test notifications for a user."""

    # Connect to database
    try:
        db_url = settings.get_database_url()
    except Exception as exc:
        print(f"❌ Database URL not configured: {exc}")
        print("Check SITE_MODE and your database environment variables.")
        return

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # Find user
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"❌ User not found: {email}")
            return

        print(f"✅ Found user: {user.first_name} {user.last_name} ({user.id})")

        repo = NotificationRepository(db)

        # Create various test notifications
        test_notifications = [
            {
                "category": "lesson_updates",
                "type": "booking_confirmed",
                "title": "New Booking!",
                "body": "John Smith booked Piano Lessons for tomorrow at 2:00 PM",
                "data": {"booking_id": "test123", "url": "/instructor/dashboard?panel=bookings"},
            },
            {
                "category": "lesson_updates",
                "type": "booking_cancelled",
                "title": "Booking Cancelled",
                "body": "Emma Johnson cancelled their Guitar Lesson for Friday",
                "data": {"booking_id": "test456", "url": "/instructor/dashboard?panel=bookings"},
            },
            {
                "category": "lesson_updates",
                "type": "booking_reminder",
                "title": "Upcoming Lesson",
                "body": "Reminder: You have a lesson with Michael in 1 hour",
                "data": {"booking_id": "test789", "url": "/instructor/dashboard?panel=bookings"},
            },
            {
                "category": "promotional",
                "type": "platform_update",
                "title": "New Feature Available!",
                "body": "You can now offer group lessons. Check it out!",
                "data": {},
            },
        ]

        created_count = 0
        for notif_data in test_notifications:
            notification = Notification(
                id=str(ULID()),
                user_id=user.id,
                category=notif_data["category"],
                type=notif_data["type"],
                title=notif_data["title"],
                body=notif_data["body"],
                data=notif_data["data"],
                read_at=None,  # All unread
                created_at=datetime.now(timezone.utc),
            )
            db.add(notification)
            created_count += 1
            print(f"  📬 Created: {notif_data['title']}")

        db.commit()
        print(f"\n✅ Created {created_count} test notifications for {email}")

        # Show current counts
        total = repo.get_user_notification_count(user.id)
        unread = repo.get_unread_count(user.id)
        print(f"📊 Total: {total}, Unread: {unread}")

    finally:
        db.close()

def clear_notifications(email: str):
    """Clear all notifications for a user."""

    try:
        db_url = settings.get_database_url()
    except Exception as exc:
        print(f"❌ Database URL not configured: {exc}")
        print("Check SITE_MODE and your database environment variables.")
        return

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"❌ User not found: {email}")
            return

        deleted = db.query(Notification).filter(Notification.user_id == user.id).delete()
        db.commit()
        print(f"🗑️ Deleted {deleted} notifications for {email}")

    finally:
        db.close()

if __name__ == "__main__":
    if len(ARGS) < 1:
        print("Usage: python test_notification_inbox.py [stg|preview|int|prod] <user_email> [--clear]")
        print("Example: python test_notification_inbox.py sarah.chen@example.com")
        print("         python test_notification_inbox.py preview sarah.chen@example.com")
        print("         python test_notification_inbox.py sarah.chen@example.com --clear")
        sys.exit(1)

    email = ARGS[0]

    if len(ARGS) > 1 and ARGS[1] == "--clear":
        clear_notifications(email)
    else:
        create_test_notifications(email)
