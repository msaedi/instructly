#!/usr/bin/env python3
"""
Update Stripe test account mappings from database.

This script reads the current stripe_connected_accounts table and updates
the config/stripe_test_accounts.json file with any new account associations.

Usage:
  Default (INT database): python backend/scripts/update_stripe_mapping.py
  Staging database: SITE_MODE=local python backend/scripts/update_stripe_mapping.py
  Production: SITE_MODE=prod python backend/scripts/update_stripe_mapping.py (requires confirmation)
"""

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings


def update_stripe_mapping():
    """Update the Stripe mapping file from database"""
    # Connect to database
    db_url = settings.get_database_url()
    engine = create_engine(db_url)

    # Load existing mapping
    mapping_file = Path(__file__).parent.parent / "config" / "stripe_test_accounts.json"
    existing_mapping = {}

    if mapping_file.exists():
        try:
            with open(mapping_file) as f:
                existing_mapping = json.load(f)
                print(f"📖 Loaded existing mapping with {len(existing_mapping)} entries")
        except Exception as e:
            print(f"⚠️  Could not load existing mapping: {e}")

    # Query database for current Stripe accounts
    with Session(engine) as session:
        query = text(
            """
            SELECT
                u.email,
                sca.stripe_account_id,
                sca.onboarding_completed,
                u.first_name,
                u.last_name
            FROM stripe_connected_accounts sca
            JOIN instructor_profiles ip ON sca.instructor_profile_id = ip.id
            JOIN users u ON ip.user_id = u.id
            WHERE u.email LIKE '%@example.com'
            ORDER BY u.email
        """
        )

        results = session.execute(query).fetchall()

        if not results:
            print("ℹ️  No Stripe connected accounts found in database")
            return

        print(f"\n📊 Found {len(results)} Stripe connected accounts in database:")

        # Update mapping with all Stripe accounts found
        updated_count = 0
        for row in results:
            email, stripe_id, onboarding_completed, first_name, last_name = row

            # Check if this is a new entry or update
            if email not in existing_mapping or existing_mapping[email] != stripe_id:
                existing_mapping[email] = stripe_id
                updated_count += 1
                status = "✅" if onboarding_completed else "⏳"
                print(f"  {status} {first_name} {last_name} ({email}): {stripe_id[:20]}...")

        # IMPORTANT: Also add ALL instructors from the database (even without Stripe accounts)
        # This ensures any new instructor can have their account preserved
        all_instructors_query = text(
            """
            SELECT DISTINCT u.email
            FROM users u
            JOIN instructor_profiles ip ON ip.user_id = u.id
            WHERE u.email LIKE '%@example.com'
            ORDER BY u.email
        """
        )

        all_instructors = session.execute(all_instructors_query).fetchall()

        # Add all instructors to the mapping (preserve null for those without Stripe)
        for (email,) in all_instructors:
            if email not in existing_mapping:
                existing_mapping[email] = None
                print(f"  📝 Added new instructor to mapping: {email}")

        # Sort the mapping by email for readability
        sorted_mapping = dict(sorted(existing_mapping.items()))

        # Add comment back
        final_mapping = {"_comment": "Test Stripe Connected Account mappings - DO NOT COMMIT with real account IDs"}
        final_mapping.update(sorted_mapping)

        # Write updated mapping
        try:
            with open(mapping_file, "w") as f:
                json.dump(final_mapping, f, indent=2)
                f.write("\n")  # Add trailing newline

            if updated_count > 0:
                print(f"\n✅ Updated mapping file with {updated_count} new/changed entries")
            else:
                print(f"\n✅ No changes needed - mapping file is up to date")

            # Show summary
            connected_count = sum(1 for v in sorted_mapping.values() if v is not None)
            print(f"\n📈 Summary:")
            print(f"  - Total instructors: {len(sorted_mapping)}")
            print(f"  - Connected to Stripe: {connected_count}")
            print(f"  - Not connected: {len(sorted_mapping) - connected_count}")

        except Exception as e:
            print(f"❌ Error writing mapping file: {e}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(update_stripe_mapping())
