# backend/scripts/send_daily_reminders.py
"""
Daily reminder email script.

This script should be run daily (e.g., at 9 AM) to send reminder emails
for all bookings scheduled for the next day.

For production, set up a cron job:
    0 9 * * * /usr/bin/python /path/to/send_daily_reminders.py

Or use a task scheduler like Celery for more sophisticated scheduling.
"""

import asyncio
from datetime import datetime
import logging
from pathlib import Path
import sys

# Add the parent directory to the path
sys.path.append(str(Path(__file__).parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.services.notification_service import NotificationService  # noqa: E402

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("reminder_emails.log"), logging.StreamHandler()],
)

logger = logging.getLogger(__name__)


async def send_daily_reminders():
    """Send reminder emails for tomorrow's bookings."""
    logger.info("Starting daily reminder email job")

    db = SessionLocal()

    try:
        notification_service = NotificationService(db)
        count = await notification_service.send_reminder_emails()

        logger.info(f"Successfully sent {count} reminder emails")

        # You could also send a summary email to admin here
        # await send_admin_summary(count)

        return count

    except Exception as e:
        logger.error(f"Error in daily reminder job: {str(e)}")
        raise

    finally:
        db.close()


async def main():
    """Main entry point."""
    start_time = datetime.now()
    logger.info(f"Daily reminder job started at {start_time}")

    try:
        count = await send_daily_reminders()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info(f"Daily reminder job completed in {duration:.2f} seconds")
        logger.info(f"Total reminders sent: {count}")

    except Exception as e:
        logger.error(f"Daily reminder job failed: {str(e)}")
        # In production, send alert to admin
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
