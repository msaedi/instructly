# backend/scripts/test_email_notifications.py
"""
Test script for email notifications.

Run this script to test the email notification system without creating actual bookings.

Usage:
    python scripts/test_email_notifications.py
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, date, time, timedelta

# Add the parent directory to the path
sys.path.append(str(Path(__file__).parent.parent))

from app.database import SessionLocal, engine
from app.models.booking import Booking, BookingStatus
from app.models.user import User
from app.models.service import Service
from app.services.notification_service import NotificationService


def create_test_booking():
    """Create a test booking object for email testing."""
    # Create mock user objects
    # Using Resend's test email or replace with your actual email
    student = User(
        id=1,
        email="delivered@resend.dev",  # Resend's test email OR use your real email
        full_name="Test Student",
        role="student"
    )
    
    instructor = User(
        id=2,
        email="delivered@resend.dev",  # Resend's test email OR use your real email
        full_name="Test Instructor",
        role="instructor"
    )
    
    # Create a mock booking
    booking = Booking(
        id=999,
        student=student,
        instructor=instructor,
        service_name="Piano Lessons",
        booking_date=date.today() + timedelta(days=1),  # Tomorrow
        start_time=time(14, 0),  # 2:00 PM
        end_time=time(15, 0),    # 3:00 PM
        duration_minutes=60,
        total_price=75.00,
        status=BookingStatus.CONFIRMED,
        location_type="instructor_location",
        meeting_location="123 Music Studio, New York, NY",
        student_note="First time learning piano, excited to start!",
        service_area="Manhattan, Upper West Side"
    )
    
    # Manually set the relationships (for testing only)
    booking.student_id = student.id
    booking.instructor_id = instructor.id
    
    return booking


async def test_booking_confirmation():
    """Test booking confirmation emails."""
    print("\n=== Testing Booking Confirmation Emails ===")
    
    booking = create_test_booking()
    notification_service = NotificationService()
    
    try:
        success = await notification_service.send_booking_confirmation(booking)
        if success:
            print("✅ Booking confirmation emails sent successfully!")
        else:
            print("❌ Failed to send booking confirmation emails")
    except Exception as e:
        print(f"❌ Error: {str(e)}")


async def test_cancellation_notification():
    """Test cancellation notification emails."""
    print("\n=== Testing Cancellation Notification Emails ===")
    
    booking = create_test_booking()
    notification_service = NotificationService()
    
    # Test student cancellation
    print("\n1. Testing student cancellation...")
    try:
        success = await notification_service.send_cancellation_notification(
            booking=booking,
            cancelled_by=booking.student,
            reason="Schedule conflict"
        )
        if success:
            print("✅ Student cancellation emails sent successfully!")
        else:
            print("❌ Failed to send student cancellation emails")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    
    # Test instructor cancellation
    print("\n2. Testing instructor cancellation...")
    try:
        success = await notification_service.send_cancellation_notification(
            booking=booking,
            cancelled_by=booking.instructor,
            reason="Emergency came up"
        )
        if success:
            print("✅ Instructor cancellation emails sent successfully!")
        else:
            print("❌ Failed to send instructor cancellation emails")
    except Exception as e:
        print(f"❌ Error: {str(e)}")


async def test_reminder_emails():
    """Test reminder emails."""
    print("\n=== Testing Reminder Emails ===")
    
    # For reminder emails, we need a database session
    db = SessionLocal()
    
    try:
        # Create a test booking for tomorrow
        booking = create_test_booking()
        
        # We'll test the private methods directly since the public method queries the DB
        notification_service = NotificationService(db)
        
        print("\n1. Testing student reminder...")
        try:
            success = await notification_service._send_student_reminder(booking)
            if success:
                print("✅ Student reminder email sent successfully!")
            else:
                print("❌ Failed to send student reminder email")
        except Exception as e:
            print(f"❌ Error: {str(e)}")
        
        print("\n2. Testing instructor reminder...")
        try:
            success = await notification_service._send_instructor_reminder(booking)
            if success:
                print("✅ Instructor reminder email sent successfully!")
            else:
                print("❌ Failed to send instructor reminder email")
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            
    finally:
        db.close()


async def main():
    """Run all email notification tests."""
    print("\n🚀 Starting Email Notification Tests")
    print("=" * 50)
    print("\nNOTE: Update the test email addresses in create_test_booking()")
    print("\nOptions:")
    print("1. Use 'delivered@resend.dev' for Resend's test inbox")
    print("2. Use your real email address to see actual emails")
    print("\nCurrent test configuration:")
    booking = create_test_booking()
    print(f"- Student email: {booking.student.email}")
    print(f"- Instructor email: {booking.instructor.email}")
    print("\nPress Enter to continue or Ctrl+C to cancel...")
    input()
    
    # Run all tests
    await test_booking_confirmation()
    await asyncio.sleep(3)  # Increased delay to respect rate limits (2 req/sec)
    
    await test_cancellation_notification()
    await asyncio.sleep(3)  # Increased delay
    
    await test_reminder_emails()
    
    print("\n✅ All tests completed!")
    print("\nCheck the email inboxes for the test addresses.")
    print("Also check the application logs for any errors.")


if __name__ == "__main__":
    asyncio.run(main())