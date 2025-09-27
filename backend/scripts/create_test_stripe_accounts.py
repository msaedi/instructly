#!/usr/bin/env python3
"""
Create test Stripe Connected accounts for all instructors programmatically.

NOTE: This only works with Stripe TEST mode (not production).
Test accounts are fully functional for development but don't handle real money.

Usage:
  Default (INT database): python backend/scripts/create_test_stripe_accounts.py
  Staging database: SITE_MODE=local python backend/scripts/create_test_stripe_accounts.py

  Dry run (see what would be created):
    python backend/scripts/create_test_stripe_accounts.py --dry-run
"""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
import stripe
import ulid

from app.core.config import settings
from app.models.payment import StripeConnectedAccount


def create_test_stripe_accounts(dry_run=False):
    """Create test Stripe accounts for all instructors"""

    # Ensure we're using TEST keys (check both uppercase and lowercase)
    stripe_key = os.getenv("STRIPE_SECRET_KEY") or os.getenv("stripe_secret_key", "")
    if not stripe_key.startswith("sk_test_"):
        print("❌ ERROR: This script only works with Stripe TEST keys!")
        print("   Your STRIPE_SECRET_KEY must start with 'sk_test_'")
        print(f"   Current key: {stripe_key[:10] if stripe_key else 'NOT SET'}")
        return 1

    stripe.api_key = stripe_key

    # Connect to database
    db_url = settings.get_database_url()
    engine = create_engine(db_url)

    with Session(engine) as session:
        # Find all instructors without Stripe accounts
        query = text(
            """
            SELECT
                ip.id as profile_id,
                u.id as user_id,
                u.email,
                u.first_name,
                u.last_name,
                u.phone
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

        print(f"Found {len(instructors)} instructors without Stripe accounts\n")

        if dry_run:
            print("🔍 DRY RUN MODE - No accounts will be created\n")
            for instructor in instructors[:10]:  # Show first 10 in dry run
                _, _, email, first_name, last_name, _ = instructor
                print(f"  Would create account for: {first_name} {last_name} ({email})")
            if len(instructors) > 10:
                print(f"  ... and {len(instructors) - 10} more")
            return 0

        created_count = 0
        failed_count = 0

        for instructor in instructors:
            profile_id, user_id, email, first_name, last_name, phone = instructor

            try:
                # Create a Stripe Express account
                # We can't accept TOS on their behalf, but we can prefill data
                account = stripe.Account.create(
                    type="express",
                    country="US",
                    email=email,
                    capabilities={
                        "card_payments": {"requested": True},
                        "transfers": {"requested": True},
                    },
                    business_type="individual",
                    business_profile={
                        "mcc": "8299",  # Educational services
                        "name": f"{first_name} {last_name} - Instructor",
                        "product_description": "Private instruction and tutoring services",
                    },
                    # Request immediate verification in test mode
                    metadata={"instructor_id": str(user_id), "test_account": "true", "auto_created": "true"},
                )

                # In test mode, we can update the account to mark it as fully onboarded
                # by using special test tokens
                if stripe_key.startswith("sk_test_"):
                    # Update account with test data to complete onboarding
                    account = stripe.Account.modify(
                        account.id,
                        individual={
                            "first_name": first_name,
                            "last_name": last_name,
                            "email": email,
                            "phone": phone or "+12025551234",
                            "dob": {"day": 1, "month": 1, "year": 1990},
                            "address": {
                                "line1": "123 Test Street",
                                "city": "New York",
                                "state": "NY",
                                "postal_code": "10001",
                                "country": "US",
                            },
                            "ssn_last_4": "0000",
                            "id_number": "000000000",  # Test SSN
                        },
                    )

                # Check if the account has charges_enabled (fully onboarded)
                is_onboarded = hasattr(account, "charges_enabled") and account.charges_enabled

                # Save to database
                stripe_account = StripeConnectedAccount(
                    id=str(ulid.ULID()),
                    instructor_profile_id=profile_id,
                    stripe_account_id=account.id,
                    onboarding_completed=is_onboarded,  # Only true if charges are enabled
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(stripe_account)
                session.commit()

                print(f"✅ Created test account for {first_name} {last_name}: {account.id}")
                created_count += 1

            except stripe.error.StripeError as e:
                print(f"❌ Failed to create account for {first_name} {last_name}: {e}")
                failed_count += 1
                continue
            except Exception as e:
                print(f"❌ Database error for {first_name} {last_name}: {e}")
                failed_count += 1
                session.rollback()
                continue

        print("\n📊 Summary:")
        print(f"  ✅ Successfully created: {created_count} accounts")
        if failed_count > 0:
            print(f"  ❌ Failed: {failed_count} accounts")

        # Now update the mapping file
        if created_count > 0:
            print("\n📝 Updating mapping file...")
            os.system("python scripts/update_stripe_mapping.py")

        return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create test Stripe accounts for instructors")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without actually creating")
    args = parser.parse_args()

    sys.exit(create_test_stripe_accounts(dry_run=args.dry_run))
