#!/usr/bin/env python3
"""
Send a test push notification to a user.

Usage:
    python scripts/test_push_notification.py <user_email>
    python scripts/test_push_notification.py stg <user_email>
    python scripts/test_push_notification.py preview <user_email>

Defaults to stg when no mode is provided.

Requirements:
    - VAPID keys configured in .env
    - User must have at least one push subscription
"""

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

from app.core.config import settings
from app.models import User
from app.services.push_notification_service import PushNotificationService


def main() -> None:
    if len(ARGS) < 1:
        print("Usage: python scripts/test_push_notification.py [stg|preview|int|prod] <user_email>")
        print("Example: python scripts/test_push_notification.py sarah.chen@example.com")
        print("Example: python scripts/test_push_notification.py preview sarah.chen@example.com")
        sys.exit(1)

    email = ARGS[0]

    if not PushNotificationService.is_configured():
        print("ERROR: VAPID keys not configured.")
        print("Run: python scripts/generate_vapid_keys.py")
        print("Then add keys to .env")
        sys.exit(1)

    try:
        db_url = settings.get_database_url()
    except Exception as exc:
        print(f"ERROR: Database URL not configured: {exc}")
        print("Check SITE_MODE and your database environment variables.")
        sys.exit(1)

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"ERROR: User not found: {email}")
            sys.exit(1)

        print(f"Found user: {user.first_name} {user.last_name} ({user.email})")

        service = PushNotificationService(db)
        subscriptions = service.get_user_subscriptions(user.id)

        if not subscriptions:
            print("ERROR: No push subscriptions for this user.")
            print("User needs to enable push notifications in settings first.")
            sys.exit(1)

        print(f"Found {len(subscriptions)} subscription(s)")
        print("Sending test push notification...")

        result = service.send_push_notification(
            user_id=user.id,
            title="Test Notification",
            body="Push notifications are working. This is a test from InstaInstru.",
            url="/instructor/dashboard",
            tag="test-notification",
        )

        sent = result.get("sent", 0)
        failed = result.get("failed", 0)
        expired = result.get("expired", 0)

        print("Results:")
        print(f"  Sent: {sent}")
        print(f"  Failed: {failed}")
        print(f"  Expired: {expired}")

        if sent > 0:
            print("Success: Check your browser/device for the notification.")
        else:
            print("Warning: No notifications were delivered. Check the logs for errors.")
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
