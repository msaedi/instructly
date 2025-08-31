#!/usr/bin/env python3
"""
Create simple Stripe Connected accounts for all instructors.

This creates basic accounts that instructors can complete later.
Works with both test and live Stripe keys.

Usage:
  python backend/scripts/create_simple_stripe_accounts.py
  SITE_MODE=local python backend/scripts/create_simple_stripe_accounts.py
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

import stripe
import ulid
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.payment import StripeConnectedAccount


def main():
    # Load Stripe key
    stripe_key = os.getenv("stripe_secret_key") or os.getenv("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        print("❌ No Stripe key found in environment")
        return 1

    stripe.api_key = stripe_key
    mode = "TEST" if stripe_key.startswith("sk_test_") else "LIVE"
    print(f"🔑 Using Stripe {mode} mode\n")

    # Connect to database
    db_url = settings.get_database_url()
    engine = create_engine(db_url)

    with Session(engine) as session:
        # Find instructors without Stripe accounts (excluding Sarah who has a real one)
        query = text(
            """
            SELECT
                ip.id as profile_id,
                u.email,
                u.first_name,
                u.last_name
            FROM instructor_profiles ip
            JOIN users u ON ip.user_id = u.id
            LEFT JOIN stripe_connected_accounts sca ON sca.instructor_profile_id = ip.id
            WHERE sca.id IS NULL
                AND u.email LIKE '%@example.com'
            ORDER BY u.email
        """
        )

        instructors = session.execute(query).fetchall()

        if not instructors:
            print("✅ All instructors already have Stripe accounts!")
            return 0

        print(f"📊 Found {len(instructors)} instructors without Stripe accounts\n")

        created_count = 0
        failed_count = 0

        for profile_id, email, first_name, last_name in instructors:
            try:
                # Create minimal Stripe account
                account = stripe.Account.create(
                    type="express",
                    country="US",
                    email=email,
                    metadata={"instructor_name": f"{first_name} {last_name}", "created_by": "bulk_script"},
                )

                # Save to database
                stripe_account = StripeConnectedAccount(
                    id=str(ulid.ULID()),
                    instructor_profile_id=profile_id,
                    stripe_account_id=account.id,
                    onboarding_completed=False,  # They need to complete onboarding
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(stripe_account)
                session.commit()

                print(f"✅ {first_name} {last_name}: {account.id}")
                created_count += 1

            except stripe.error.StripeError as e:
                print(f"❌ {first_name} {last_name}: Stripe error - {str(e)[:100]}")
                failed_count += 1
                session.rollback()
            except Exception as e:
                print(f"❌ {first_name} {last_name}: Database error - {str(e)[:100]}")
                failed_count += 1
                session.rollback()

        print(f"\n📊 Summary:")
        print(f"  ✅ Created: {created_count} accounts")
        if failed_count > 0:
            print(f"  ❌ Failed: {failed_count} accounts")

        # Update mapping file
        if created_count > 0:
            print("\n📝 Updating mapping file...")
            import subprocess

            result = subprocess.run(["python", "scripts/update_stripe_mapping.py"], capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ Mapping file updated")
            else:
                print("❌ Failed to update mapping file")

        return 0


if __name__ == "__main__":
    sys.exit(main())
