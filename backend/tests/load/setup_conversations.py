#!/usr/bin/env python3
"""
Setup script for load testing - discovers conversation IDs from the target environment.

This script queries the API to find valid conversation and booking IDs for the
configured test users, then writes them to conversations.json for use by locust.

Run this BEFORE running the load test:
    python setup_conversations.py
    locust -f locustfile.py --headless -u 50 -r 5 -t 2m

Or use the wrapper script:
    ./run_loadtest.sh -u 50 -r 5 -t 2m
"""

import json
import os
from pathlib import Path
import sys

import requests

# Configuration from environment (same as locustfile.py)
BASE_URL = os.getenv("LOADTEST_BASE_URL", "https://preview-api.instainstru.com")
FRONTEND_ORIGIN = os.getenv("LOADTEST_FRONTEND_ORIGIN", "https://preview.instainstru.com")
PASSWORD = os.getenv("LOADTEST_PASSWORD", "TestPassword123!")
USERS = [
    u.strip()
    for u in os.getenv("LOADTEST_USERS", "sarah.chen@example.com,emma.johnson@example.com").split(",")
    if u.strip()
]

# Output file
CONVERSATIONS_FILE = Path(__file__).parent / "config" / "conversations.json"


def login(email: str, password: str) -> str | None:
    """Login and return access token."""
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        data={"username": email, "password": password},
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Referer": f"{FRONTEND_ORIGIN}/",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=30,
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    print(f"  ERROR: Login failed for {email}: {response.status_code} - {response.text[:200]}")
    return None


def get_conversations(token: str) -> list[dict]:
    """Get all conversations for authenticated user."""
    response = requests.get(
        f"{BASE_URL}/api/v1/conversations",
        headers={
            "Authorization": f"Bearer {token}",
            "Origin": FRONTEND_ORIGIN,
            "Referer": f"{FRONTEND_ORIGIN}/",
        },
        timeout=30,
    )
    if response.status_code == 200:
        data = response.json()
        # Handle both list and paginated response formats
        if isinstance(data, list):
            return data
        return data.get("items", data.get("conversations", []))
    print(f"  ERROR: Failed to get conversations: {response.status_code}")
    return []


def get_bookings(token: str) -> list[dict]:
    """Get bookings for authenticated user."""
    response = requests.get(
        f"{BASE_URL}/api/v1/bookings",
        headers={
            "Authorization": f"Bearer {token}",
            "Origin": FRONTEND_ORIGIN,
            "Referer": f"{FRONTEND_ORIGIN}/",
        },
        timeout=30,
    )
    if response.status_code == 200:
        data = response.json()
        if isinstance(data, list):
            return data
        return data.get("items", data.get("bookings", []))
    print(f"  ERROR: Failed to get bookings: {response.status_code}")
    return []


def find_shared_conversation(user_conversations: dict[str, list[dict]]) -> str | None:
    """Find a conversation ID that appears in multiple users' conversation lists."""
    if len(user_conversations) < 2:
        return None

    # Get conversation IDs for each user
    user_conv_ids = {
        email: {c.get("id") or c.get("conversation_id") for c in convs}
        for email, convs in user_conversations.items()
    }

    # Find intersection
    all_ids = list(user_conv_ids.values())
    shared = all_ids[0]
    for ids in all_ids[1:]:
        shared = shared & ids

    if shared:
        return next(iter(shared))
    return None


def find_booking_for_conversation(
    conversations: list[dict],
    bookings: list[dict],
    conversation_id: str
) -> str | None:
    """Find a booking ID associated with a conversation."""
    # First check if conversation has booking info
    for conv in conversations:
        if (conv.get("id") or conv.get("conversation_id")) == conversation_id:
            if conv.get("booking_id"):
                return conv["booking_id"]
            # Some APIs include booking in conversation
            if conv.get("booking", {}).get("id"):
                return conv["booking"]["id"]

    # Fall back to first confirmed booking
    for booking in bookings:
        if booking.get("status") in ("CONFIRMED", "confirmed", "COMPLETED", "completed"):
            return booking.get("id") or booking.get("booking_id")

    # Last resort: any booking
    if bookings:
        return bookings[0].get("id") or bookings[0].get("booking_id")

    return None


def main() -> int:
    """Discover conversation IDs and write to config file."""
    print("=== Load Test Setup ===")
    print(f"Target: {BASE_URL}")
    print(f"Users: {USERS}")
    print()

    if len(USERS) < 2:
        print("ERROR: Need at least 2 users for E2E messaging test")
        return 1

    # Login all users and get their conversations
    user_tokens: dict[str, str] = {}
    user_conversations: dict[str, list[dict]] = {}
    user_bookings: dict[str, list[dict]] = {}

    for email in USERS:
        print(f"Logging in as {email}...")
        token = login(email, PASSWORD)
        if not token:
            print("  FAILED - skipping user")
            continue

        user_tokens[email] = token
        print("  OK - fetching conversations...")

        conversations = get_conversations(token)
        user_conversations[email] = conversations
        print(f"  Found {len(conversations)} conversations")

        bookings = get_bookings(token)
        user_bookings[email] = bookings
        print(f"  Found {len(bookings)} bookings")

    if len(user_tokens) < 2:
        print("\nERROR: Could not login at least 2 users")
        return 1

    # Find shared conversation
    print("\nLooking for shared conversation...")
    shared_conv_id = find_shared_conversation(user_conversations)

    if not shared_conv_id:
        print("ERROR: No shared conversation found between users")
        print("  Users need to have at least one conversation together for E2E testing")
        return 1

    print(f"  Found shared conversation: {shared_conv_id}")

    # Find a booking for context
    first_user = USERS[0]
    booking_id = find_booking_for_conversation(
        user_conversations[first_user],
        user_bookings[first_user],
        shared_conv_id,
    )

    if booking_id:
        print(f"  Found booking: {booking_id}")
    else:
        print("  WARNING: No booking found (messages may fail if booking is required)")

    # Build config
    config = {
        "_comment": f"Auto-generated by setup_conversations.py for {BASE_URL}",
    }
    for email in USERS:
        if email in user_tokens:
            config[email] = {
                "conversation_id": shared_conv_id,
                "booking_id": booking_id,
            }

    # Write config
    CONVERSATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONVERSATIONS_FILE, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\nWrote config to: {CONVERSATIONS_FILE}")
    print(json.dumps(config, indent=2))
    print("\nSetup complete! You can now run the load test.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
