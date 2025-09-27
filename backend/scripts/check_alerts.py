#!/usr/bin/env python3
"""Check alert history in the database."""

import os
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Force test database
os.environ["DATABASE_URL"] = os.getenv(
    "test_database_url", "postgresql://postgres:postgres@localhost:5432/instainstru_test"
)

from app.database import SessionLocal
from app.models.monitoring import AlertHistory


def main():
    db = SessionLocal()
    try:
        print("=== Alert History in Database ===")
        print(f"Database: {os.environ['DATABASE_URL'].split('@')[1]}")
        print()

        alerts = db.query(AlertHistory).order_by(AlertHistory.created_at.desc()).all()

        if not alerts:
            print("No alerts found in database.")
            print("\nPossible reasons:")
            print("1. Celery workers are using a different database")
            print("2. Tasks failed to execute")
            print("3. Tasks are still in queue")
            print("\nCheck Celery worker logs for errors.")
        else:
            print(f"Found {len(alerts)} alerts:\n")

            for alert in alerts:
                print(f"ID: {alert.id}")
                print(f"Type: {alert.alert_type}")
                print(f"Severity: {alert.severity}")
                print(f"Title: {alert.title}")
                print(f"Message: {alert.message}")
                print(f"Created: {alert.created_at}")
                print(f"Email sent: {alert.email_sent}")
                print(f"GitHub issue: {alert.github_issue_created}")
                if alert.details:
                    print(f"Details: {alert.details}")
                print("-" * 50)

    finally:
        db.close()


if __name__ == "__main__":
    main()
