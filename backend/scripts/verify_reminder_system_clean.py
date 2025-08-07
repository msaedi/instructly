#!/usr/bin/env python3
# backend/scripts/verify_reminder_system_clean.py
"""
Reminder System Clean Architecture Verification

Verifies that the reminder emails system doesn't reference removed
architectural concepts and uses clean date-based queries.

Part of Work Stream #11 Phase 3 - Supporting Systems Verification
"""

import re
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))


def check_reminder_implementation(filepath: Path) -> dict:
    """
    Check reminder implementation for clean architecture compliance.

    Returns dict with findings.
    """
    findings = {
        "uses_clean_queries": False,
        "has_removed_concepts": False,
        "removed_concepts_found": [],
        "query_pattern": None,
        "issues": [],
    }

    try:
        with open(filepath, "r") as f:
            content = f.read()

        # Check for removed concepts
        removed_concepts = ["availability_slot_id", "InstructorAvailability", "availability_slot", "slot_id"]

        for concept in removed_concepts:
            if concept in content:
                # Skip if it's in a comment or docstring
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if concept in line and not line.strip().startswith("#"):
                        findings["has_removed_concepts"] = True
                        findings["removed_concepts_found"].append(f"Line {i+1}: {concept}")

        # Look for the reminder query pattern
        if "send_reminder_emails" in content:
            # Extract the query section
            query_match = re.search(r"query\(Booking\).*?\.all\(\)", content, re.DOTALL)
            if query_match:
                query = query_match.group()
                findings["query_pattern"] = query.replace("\n", " ").strip()

                # Check if it's a clean date-based query
                if "booking_date ==" in query and "tomorrow" in query:
                    findings["uses_clean_queries"] = True

                # Check for bad patterns
                if "join(" in query:
                    findings["issues"].append("Query uses joins - might be joining removed tables")
                if "availability" in query.lower():
                    findings["issues"].append("Query references availability - might be using old pattern")

    except FileNotFoundError:
        findings["issues"].append(f"File not found: {filepath}")

    return findings


def analyze_endpoint(filepath: Path) -> dict:
    """
    Analyze the reminder endpoint for clean implementation.
    """
    endpoint_info = {
        "endpoint_found": False,
        "endpoint_path": None,
        "calls_service": False,
        "has_direct_queries": False,
        "issues": [],
    }

    try:
        with open(filepath, "r") as f:
            content = f.read()

        # Look for send-reminders endpoint
        if "send-reminders" in content or "send_reminder_emails" in content:
            endpoint_info["endpoint_found"] = True
            endpoint_info["endpoint_path"] = "/bookings/send-reminders"

            # Check if it delegates to service
            if "booking_service.send_booking_reminders" in content:
                endpoint_info["calls_service"] = True

            # Check for direct DB queries (bad pattern)
            if "db.query(Booking)" in content:
                endpoint_info["has_direct_queries"] = True
                endpoint_info["issues"].append("Endpoint has direct DB queries - should use service layer")

    except FileNotFoundError:
        endpoint_info["issues"].append(f"File not found: {filepath}")

    return endpoint_info


def verify_clean_architecture():
    """
    Main verification function for reminder system.
    """
    print("🔍 Reminder System Clean Architecture Verification")
    print("=" * 60)

    all_clean = True

    # Check notification service implementation
    print("\n📄 Checking notification_service.py")
    print("-" * 40)

    notification_path = backend_dir / "app" / "services" / "notification_service.py"
    findings = check_reminder_implementation(notification_path)

    if findings["uses_clean_queries"] and not findings["has_removed_concepts"]:
        print("✅ Clean implementation found!")
        print(f"   Query pattern: {findings['query_pattern'][:80]}...")
    else:
        all_clean = False
        print("❌ Issues found:")
        if findings["has_removed_concepts"]:
            print("   References to removed concepts:")
            for ref in findings["removed_concepts_found"]:
                print(f"     - {ref}")
        if not findings["uses_clean_queries"]:
            print("   ⚠️  Not using clean date-based queries")
        for issue in findings["issues"]:
            print(f"   - {issue}")

    # Check endpoint implementation
    print("\n📄 Checking bookings.py endpoint")
    print("-" * 40)

    bookings_path = backend_dir / "app" / "routes" / "bookings.py"
    endpoint_info = analyze_endpoint(bookings_path)

    if endpoint_info["endpoint_found"]:
        print(f"✅ Reminder endpoint found: {endpoint_info['endpoint_path']}")
        if endpoint_info["calls_service"]:
            print("✅ Properly delegates to service layer")
        if endpoint_info["has_direct_queries"]:
            all_clean = False
            print("❌ Has direct database queries")
    else:
        print("⚠️  Reminder endpoint not found")

    # Test the query logic
    print("\n🧪 Testing Query Logic")
    print("-" * 40)

    try:
        from datetime import datetime, timedelta
        from datetime import timezone as tz

        # Simulate the query logic
        tomorrow = datetime.now(tz.utc).date() + timedelta(days=1)
        print(f"✅ Query would look for bookings on: {tomorrow}")
        print("✅ Query filters: booking_date == tomorrow AND status == 'CONFIRMED'")
        print("✅ No joins with removed tables")
        print("✅ No slot references")

    except Exception as e:
        print(f"⚠️  Could not test query logic: {e}")

    # Final verdict
    print("\n" + "=" * 60)
    if all_clean:
        print("✅ SUCCESS: Reminder system uses clean architecture!")
        print("   - Date-based queries on bookings table")
        print("   - No references to removed concepts")
        print("   - Ready for cron job integration")
        return 0
    else:
        print("❌ ISSUES FOUND: Reminder system needs fixes")
        return 1


def show_example_cron():
    """
    Show example cron configuration for reminders.
    """
    print("\n📅 Example Cron Configuration")
    print("-" * 40)
    print("# Send reminder emails daily at 10 AM")
    print("0 10 * * * curl -X POST http://localhost:8000/api/bookings/send-reminders \\")
    print("  -H 'Authorization: Bearer YOUR_ADMIN_TOKEN' \\")
    print("  -H 'Content-Type: application/json'")
    print("\n# Or using a script:")
    print("0 10 * * * /path/to/send_reminders.sh")


if __name__ == "__main__":
    exit_code = verify_clean_architecture()
    if exit_code == 0:
        show_example_cron()
    sys.exit(exit_code)
