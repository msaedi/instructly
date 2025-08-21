#!/usr/bin/env python3
"""
Create prefilled Stripe Connected accounts for instructors.

This creates "skeleton" accounts that instructors must complete manually.
This is closer to what happens in production - we create the account,
then redirect the instructor to Stripe to complete onboarding.

Usage:
  python backend/scripts/create_stripe_prefilled_accounts.py --email sarah.chen@example.com
  python backend/scripts/create_stripe_prefilled_accounts.py --all  # Create for all

  USE_STG_DATABASE=true python backend/scripts/create_stripe_prefilled_accounts.py --email ...
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import stripe
import ulid
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.payment import StripeConnectedAccount


def create_prefilled_account(email, first_name, last_name, profile_id, session):
    """Create a single prefilled Stripe account"""

    try:
        # Create minimal account - instructor must complete onboarding
        account = stripe.Account.create(
            type="express",
            country="US",
            email=email,
            metadata={"instructor_email": email, "instructor_name": f"{first_name} {last_name}"},
        )

        # Create onboarding link
        account_link = stripe.AccountLink.create(
            account=account.id,
            refresh_url=f"http://localhost:3000/dashboard/instructor?stripe_onboarding_return=true",
            return_url=f"http://localhost:3000/dashboard/instructor?stripe_onboarding_return=true",
            type="account_onboarding",
        )

        # Save to database (onboarding_completed=False since they need to complete it)
        stripe_account = StripeConnectedAccount(
            id=str(ulid.ULID()),
            instructor_profile_id=profile_id,
            stripe_account_id=account.id,
            onboarding_completed=False,  # Not completed yet
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(stripe_account)
        session.commit()

        return account.id, account_link.url

    except stripe.error.StripeError as e:
        raise Exception(f"Stripe error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Create prefilled Stripe accounts")
    parser.add_argument("--email", help="Create account for specific instructor")
    parser.add_argument("--all", action="store_true", help="Create for all instructors without accounts")
    parser.add_argument("--limit", type=int, default=5, help="Limit number of accounts to create (with --all)")
    args = parser.parse_args()

    if not args.email and not args.all:
        print("❌ Please specify --email or --all")
        return 1

    # Check Stripe key
    stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        print("❌ ERROR: STRIPE_SECRET_KEY not set in environment")
        return 1

    stripe.api_key = stripe_key
    mode = "TEST" if stripe_key.startswith("sk_test_") else "LIVE"
    print(f"🔑 Using Stripe {mode} mode\n")

    # Connect to database
    db_url = settings.get_database_url()
    engine = create_engine(db_url)

    with Session(engine) as session:
        if args.email:
            # Create for specific instructor
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
                WHERE u.email = :email AND sca.id IS NULL
            """
            )

            result = session.execute(query, {"email": args.email}).fetchone()

            if not result:
                print(f"❌ Instructor {args.email} not found or already has a Stripe account")
                return 1

            profile_id, email, first_name, last_name = result

            try:
                account_id, onboarding_url = create_prefilled_account(email, first_name, last_name, profile_id, session)

                print(f"✅ Created Stripe account for {first_name} {last_name}")
                print(f"   Account ID: {account_id}")
                print(f"\n📋 Onboarding URL (send this to the instructor):")
                print(f"   {onboarding_url}\n")

            except Exception as e:
                print(f"❌ Failed: {e}")
                return 1

        else:  # --all
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
                LIMIT :limit
            """
            )

            instructors = session.execute(query, {"limit": args.limit}).fetchall()

            if not instructors:
                print("✅ All instructors already have Stripe accounts!")
                return 0

            print(f"Creating accounts for {len(instructors)} instructors (limit: {args.limit})\n")

            created = []
            for profile_id, email, first_name, last_name in instructors:
                try:
                    account_id, onboarding_url = create_prefilled_account(
                        email, first_name, last_name, profile_id, session
                    )

                    created.append(
                        {
                            "name": f"{first_name} {last_name}",
                            "email": email,
                            "account_id": account_id,
                            "url": onboarding_url,
                        }
                    )

                    print(f"✅ {first_name} {last_name}: {account_id}")

                except Exception as e:
                    print(f"❌ {first_name} {last_name}: {e}")
                    session.rollback()

            if created:
                print(f"\n📊 Created {len(created)} accounts\n")
                print("📋 Onboarding URLs to send to instructors:\n")
                for item in created:
                    print(f"{item['name']} ({item['email']}):")
                    print(f"  {item['url']}\n")

    # Update mapping file
    if args.all and created:
        print("📝 Updating mapping file...")
        os.system("python scripts/update_stripe_mapping.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
