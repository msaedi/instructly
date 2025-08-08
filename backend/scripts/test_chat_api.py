#!/usr/bin/env python3
"""
Test chat functionality via API.

This script allows you to:
1. Send messages as either student or instructor
2. View message history
3. Listen to real-time messages via SSE
4. Mark messages as read

Usage:
    python scripts/test_chat_api.py
"""

import json
import sys
import threading
import time
from datetime import datetime
from typing import Optional

import requests
import sseclient  # You may need to: pip install sseclient-py

# API Configuration
API_URL = "http://localhost:8000"
HEADERS = {"Content-Type": "application/json"}

# Test credentials
STUDENT_EMAIL = "john.smith@example.com"
INSTRUCTOR_EMAIL = "sarah.chen.instructor@example.com"
DEFAULT_PASSWORD = "Test1234"


def login(email: str, password: str) -> Optional[str]:
    """Login and return access token."""
    # Login endpoint expects form-encoded OAuth2 fields: username and password
    response = requests.post(
        f"{API_URL}/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Logged in as: {email}")
        return data["access_token"]
    else:
        print(f"❌ Login failed for {email}: {response.text}")
        return None


def get_user_info(token: str) -> dict:
    """Get current user information."""
    headers = {**HEADERS, "Authorization": f"Bearer {token}"}
    response = requests.get(f"{API_URL}/auth/me", headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"❌ Failed to get user info: {response.text}")
        return {}


def send_message(token: str, booking_id: int, content: str) -> bool:
    """Send a message in a booking chat."""
    headers = {**HEADERS, "Authorization": f"Bearer {token}"}
    response = requests.post(
        f"{API_URL}/api/messages/send",
        json={"booking_id": booking_id, "content": content},
        headers=headers,
    )

    if response.status_code == 201:
        data = response.json()
        message = data["message"]
        print(f"✅ Message sent: [{message['id']}] {content[:50]}...")
        return True
    else:
        print(f"❌ Failed to send message: {response.text}")
        return False


def get_message_history(token: str, booking_id: int, limit: int = 50) -> list:
    """Get message history for a booking."""
    headers = {**HEADERS, "Authorization": f"Bearer {token}"}
    response = requests.get(
        f"{API_URL}/api/messages/history/{booking_id}?limit={limit}",
        headers=headers,
    )

    if response.status_code == 200:
        data = response.json()
        return data["messages"]
    else:
        print(f"❌ Failed to get message history: {response.text}")
        return []


def mark_messages_as_read(token: str, booking_id: int) -> bool:
    """Mark all messages in a booking as read."""
    headers = {**HEADERS, "Authorization": f"Bearer {token}"}
    response = requests.post(
        f"{API_URL}/api/messages/mark-read",
        json={"booking_id": booking_id},
        headers=headers,
    )

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Marked {data['messages_marked']} messages as read")
        return True
    else:
        print(f"❌ Failed to mark messages as read: {response.text}")
        return False


def get_unread_count(token: str) -> int:
    """Get unread message count."""
    headers = {**HEADERS, "Authorization": f"Bearer {token}"}
    response = requests.get(f"{API_URL}/api/messages/unread-count", headers=headers)

    if response.status_code == 200:
        data = response.json()
        return data["unread_count"]
    else:
        print(f"❌ Failed to get unread count: {response.text}")
        return 0


def listen_to_sse(token: str, booking_id: int, duration: int = 30):
    """Listen to SSE stream for real-time messages."""
    print(f"\n📡 Listening to real-time messages for {duration} seconds...")

    url = f"{API_URL}/api/messages/stream/{booking_id}?token={token}"

    try:
        response = requests.get(url, stream=True, headers={"Accept": "text/event-stream"})
        client = sseclient.SSEClient(response)

        start_time = time.time()

        for event in client.events():
            if time.time() - start_time > duration:
                print("⏱️ Listening period ended")
                break

            if event.event == "message":
                data = json.loads(event.data)
                print(f"\n📨 New message received:")
                print(f"   From: User {data.get('sender_id')}")
                print(f"   Content: {data.get('content')}")
                print(f"   Time: {data.get('created_at')}")
            elif event.event == "connected":
                print("✅ Connected to SSE stream")
            elif event.event == "heartbeat":
                print("💓 Heartbeat received")

    except Exception as e:
        print(f"❌ SSE Error: {e}")


def display_message_history(messages: list, current_user_id: int):
    """Display message history in a readable format."""
    print("\n" + "=" * 60)
    print("📜 MESSAGE HISTORY")
    print("=" * 60)

    if not messages:
        print("No messages yet")
        return

    for msg in messages:
        is_mine = msg["sender_id"] == current_user_id
        sender = "You" if is_mine else f"User {msg['sender_id']}"

        # Format timestamp
        created_at = datetime.fromisoformat(msg["created_at"].replace("Z", "+00:00"))
        time_str = created_at.strftime("%H:%M")

        # Display message
        if is_mine:
            print(f"\n  [{time_str}] {sender} ➡️")
            print(f"  {msg['content']}")
        else:
            print(f"\n  [{time_str}] ⬅️ {sender}")
            print(f"  {msg['content']}")

        if msg.get("is_deleted"):
            print("  (deleted)")

    print("\n" + "=" * 60)


def get_user_bookings(token: str) -> list:
    """Get bookings for the current user."""
    headers = {**HEADERS, "Authorization": f"Bearer {token}"}
    # New bookings API returns a paginated list at /bookings/
    response = requests.get(f"{API_URL}/bookings/?page=1&per_page=50", headers=headers)

    if response.status_code == 200:
        data = response.json()
        # PaginatedResponse shape: { items: [...], total, page, per_page, has_next, has_prev }
        return data.get("items", [])
    else:
        print(f"❌ Failed to get bookings: {response.text}")
        return []


def list_available_users():
    """List some available test users from the seeded database."""
    print("\n📋 Available Test Users (all use password: Test1234)")
    print("-" * 50)
    print("\n👨‍🎓 STUDENTS:")
    students = [
        "john.smith@example.com - John Smith",
        "emma.johnson@example.com - Emma Johnson",
        "alex.williams@example.com - Alex Williams",
        "sophia.brown@example.com - Sophia Brown",
        "david.miller@example.com - David Miller",
        "emma.fresh@example.com - Emma Fresh",
    ]
    for student in students:
        print(f"  • {student}")

    print("\n👩‍🏫 INSTRUCTORS (sample):")
    instructors = [
        "sarah.chen.instructor@example.com - Sarah Chen (Piano)",
        "michael.rodriguez.instructor@example.com - Michael Rodriguez (Spanish)",
        "jason.park.instructor@example.com - Jason Park (Personal Training)",
        "carlos.garcia.instructor@example.com - Carlos Garcia (Soccer)",
        "amanda.johnson.instructor@example.com - Amanda Johnson (Yoga)",
        "yuki.tanaka.instructor@example.com - Yuki Tanaka (Japanese)",
        "marcus.williams.instructor@example.com - Marcus Williams (Basketball)",
        "david.thompson.instructor@example.com - David Thompson (Math/Physics/Chemistry)",
    ]
    for instructor in instructors:
        print(f"  • {instructor}")

    print("\n👤 ADMIN:")
    print("  • admin@example.com - Admin User")
    print("-" * 50)


def interactive_chat_test():
    """Interactive chat testing interface."""
    print("\n🎭 CHAT API TESTER")
    print("=" * 60)

    # Choose login method
    print("\nLogin options:")
    print("1. Quick login - Student (John Smith)")
    print("2. Quick login - Instructor (Sarah Chen)")
    print("3. Custom login - Enter any email")
    print("4. Show available test users")
    choice = input("Enter choice (1-4): ").strip()

    if choice == "1":
        email = STUDENT_EMAIL
        password = DEFAULT_PASSWORD
        role = "Student"
    elif choice == "2":
        email = INSTRUCTOR_EMAIL
        password = DEFAULT_PASSWORD
        role = "Instructor"
    elif choice == "4":
        # Show available users and restart
        list_available_users()
        return interactive_chat_test()
    else:
        # Custom login
        print("\n📧 Custom Login")
        email = input("Enter email: ").strip()
        password_input = input(f"Enter password (press Enter for default '{DEFAULT_PASSWORD}'): ").strip()
        password = password_input if password_input else DEFAULT_PASSWORD

        # Determine role from email
        if "instructor" in email.lower():
            role = "Instructor"
        elif "student" in email.lower() or "@example.com" in email.lower():
            role = "Student"
        else:
            role = "User"

    # Login
    print(f"\n🔐 Attempting to login as: {email}")
    token = login(email, password)
    if not token:
        print("Failed to login. Exiting.")
        return

    # Get user info
    user_info = get_user_info(token)
    current_user_id = user_info.get("id")
    print(f"👤 Logged in as: {user_info.get('full_name')} (ID: {current_user_id})")

    # Get bookings
    bookings = get_user_bookings(token)
    if not bookings:
        print("\n⚠️ No bookings found. You need an active booking to test chat.")
        print("Create a booking first through the UI or API.")
        return

    print(f"\n📅 Found {len(bookings)} booking(s):")
    for i, booking in enumerate(bookings, 1):
        status = booking.get("status", "UNKNOWN")
        # BookingResponse uses booking_date
        date = booking.get("booking_date", "N/A")
        print(f"{i}. Booking #{booking['id']} - {date} - Status: {status}")

    # Select booking
    if len(bookings) == 1:
        booking_id = bookings[0]["id"]
        print(f"\n✅ Using booking #{booking_id}")
    else:
        choice = input(f"\nSelect booking (1-{len(bookings)}): ").strip()
        try:
            booking_id = bookings[int(choice) - 1]["id"]
        except (ValueError, IndexError):
            print("Invalid choice. Using first booking.")
            booking_id = bookings[0]["id"]

    # Main menu loop
    while True:
        print(f"\n📱 CHAT MENU (Booking #{booking_id})")
        print("=" * 40)
        print("1. View message history")
        print("2. Send a message")
        print("3. Mark all as read")
        print("4. Check unread count")
        print("5. Listen to real-time messages (30s)")
        print("6. Send multiple test messages")
        print("7. Switch booking")
        print("0. Exit")

        choice = input("\nEnter choice: ").strip()

        if choice == "0":
            print("👋 Goodbye!")
            break

        elif choice == "1":
            messages = get_message_history(token, booking_id)
            display_message_history(messages, current_user_id)

        elif choice == "2":
            content = input("Enter message: ").strip()
            if content:
                send_message(token, booking_id, content)

        elif choice == "3":
            mark_messages_as_read(token, booking_id)

        elif choice == "4":
            count = get_unread_count(token)
            print(f"📬 You have {count} unread message(s)")

        elif choice == "5":
            # Listen in a separate thread so we can continue
            print("\n🎧 Starting SSE listener in background...")
            sse_thread = threading.Thread(target=listen_to_sse, args=(token, booking_id, 30))
            sse_thread.daemon = True
            sse_thread.start()
            print("You can continue using the menu while listening...")

        elif choice == "6":
            # Send multiple test messages
            test_messages = [
                f"Test message from {role} at {datetime.now().strftime('%H:%M:%S')}",
                "How are you doing today? 😊",
                "This is a longer message to test how the chat handles multiple lines of text. "
                "It should wrap properly and display correctly in the chat window.",
                "Quick test!",
                "Final message in this batch 🎉",
            ]

            print(f"\n📤 Sending {len(test_messages)} test messages...")
            for msg in test_messages:
                if send_message(token, booking_id, msg):
                    time.sleep(0.5)  # Small delay between messages

        elif choice == "7":
            # Switch to different booking
            bookings = get_user_bookings(token)
            print(f"\n📅 Available bookings:")
            for i, booking in enumerate(bookings, 1):
                print(f"{i}. Booking #{booking['id']}")

            choice = input(f"Select booking (1-{len(bookings)}): ").strip()
            try:
                booking_id = bookings[int(choice) - 1]["id"]
                print(f"✅ Switched to booking #{booking_id}")
            except (ValueError, IndexError):
                print("Invalid choice. Keeping current booking.")


if __name__ == "__main__":
    # Check if sseclient is installed
    try:
        import sseclient
    except ImportError:
        print("⚠️ sseclient-py not installed. Installing...")
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "sseclient-py"])
        import sseclient

    try:
        interactive_chat_test()
    except KeyboardInterrupt:
        print("\n\n👋 Chat tester terminated by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
