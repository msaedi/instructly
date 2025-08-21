#!/usr/bin/env python3
"""
Fully onboard Stripe test accounts using test mode tokens.

This ONLY works in Stripe TEST mode and uses special test tokens
to bypass verification requirements.

Usage:
  python backend/scripts/fully_onboard_test_accounts.py
  python backend/scripts/fully_onboard_test_accounts.py --limit 5
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

import stripe
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings


def fully_onboard_test_account(account_id):
    """Fully onboard a test account using Stripe test tokens"""

    try:
        # Update account with test data that Stripe accepts in test mode
        # These are special test values that work in test mode
        account = stripe.Account.modify(
            account_id,
            business_type="individual",
            individual={
                "first_name": "Test",
                "last_name": "Instructor",
                "email": "test@example.com",
                "phone": "+15555551234",
                "dob": {"day": 1, "month": 1, "year": 1901},  # Special test year that Stripe accepts
                "address": {
                    "line1": "address_full_match",  # Special test address
                    "city": "San Francisco",
                    "state": "CA",
                    "postal_code": "94107",
                    "country": "US",
                },
                "ssn_last_4": "0000",  # Test SSN
                "id_number": "000000000",  # Full test SSN
                "verification": {
                    "document": {
                        "front": "file_identity_document_success",  # Special test token
                    }
                },
            },
            business_profile={
                "mcc": "8299",
                "product_description": "Test instruction services",
            },
            external_account={
                "object": "bank_account",
                "country": "US",
                "currency": "usd",
                "routing_number": "110000000",  # Test routing number
                "account_number": "000123456789",  # Test account
            },
            settings={"payouts": {"schedule": {"interval": "manual"}}},  # Manual payouts for testing
            # This is key - we need to request the capabilities
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
        )

        # The account should now be fully functional in test mode
        return account

    except stripe.error.StripeError as e:
        print(f"Stripe error: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Fully onboard test Stripe accounts")
    parser.add_argument("--limit", type=int, help="Limit number of accounts to onboard")
    parser.add_argument("--email", help="Onboard specific instructor by email")
    args = parser.parse_args()

    # Check Stripe key
    stripe_key = os.getenv("stripe_secret_key") or os.getenv("STRIPE_SECRET_KEY", "")
    if not stripe_key.startswith("sk_test_"):
        print("❌ This script ONLY works with Stripe TEST keys!")
        print("   Your key must start with 'sk_test_'")
        return 1

    stripe.api_key = stripe_key
    print("🔑 Using Stripe TEST mode\n")

    # Connect to database
    db_url = settings.get_database_url()
    engine = create_engine(db_url)

    with Session(engine) as session:
        if args.email:
            # Onboard specific instructor
            query = text(
                """
                SELECT sca.stripe_account_id, u.first_name, u.last_name
                FROM stripe_connected_accounts sca
                JOIN instructor_profiles ip ON sca.instructor_profile_id = ip.id
                JOIN users u ON ip.user_id = u.id
                WHERE u.email = :email
                    AND sca.onboarding_completed = false
            """
            )
            result = session.execute(query, {"email": args.email}).fetchone()

            if not result:
                print(f"❌ {args.email} not found or already onboarded")
                return 1

            stripe_id, first_name, last_name = result
            print(f"Onboarding {first_name} {last_name}...")

            account = fully_onboard_test_account(stripe_id)
            if account and account.charges_enabled:
                # Update database
                session.execute(
                    text(
                        """
                    UPDATE stripe_connected_accounts
                    SET onboarding_completed = true, updated_at = :now
                    WHERE stripe_account_id = :account_id
                """
                    ),
                    {"account_id": stripe_id, "now": datetime.now(timezone.utc)},
                )
                session.commit()
                print(f"✅ Fully onboarded {first_name} {last_name}")
            else:
                print(f"❌ Failed to onboard {first_name} {last_name}")

        else:
            # Onboard multiple accounts
            query = text(
                """
                SELECT sca.stripe_account_id, u.first_name, u.last_name, u.email
                FROM stripe_connected_accounts sca
                JOIN instructor_profiles ip ON sca.instructor_profile_id = ip.id
                JOIN users u ON ip.user_id = u.id
                WHERE sca.onboarding_completed = false
                    AND u.email LIKE '%@example.com'
                ORDER BY u.email
            """
            )

            if args.limit:
                query = text(str(query) + " LIMIT :limit")
                results = session.execute(query, {"limit": args.limit}).fetchall()
            else:
                results = session.execute(query).fetchall()

            if not results:
                print("✅ All accounts already onboarded!")
                return 0

            print(f"Found {len(results)} accounts to onboard\n")

            success_count = 0
            for stripe_id, first_name, last_name, email in results:
                print(f"Processing {first_name} {last_name}...", end=" ")

                account = fully_onboard_test_account(stripe_id)
                if account and account.charges_enabled:
                    # Update database
                    session.execute(
                        text(
                            """
                        UPDATE stripe_connected_accounts
                        SET onboarding_completed = true, updated_at = :now
                        WHERE stripe_account_id = :account_id
                    """
                        ),
                        {"account_id": stripe_id, "now": datetime.now(timezone.utc)},
                    )
                    session.commit()
                    print("✅")
                    success_count += 1
                else:
                    print("❌")

            print(f"\n📊 Summary:")
            print(f"  ✅ Successfully onboarded: {success_count}/{len(results)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
