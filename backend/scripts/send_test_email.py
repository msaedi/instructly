# backend/scripts/send_test_email.py
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.models.booking import Booking, BookingStatus
from app.services.notification_service import notification_service as new_service


async def send_test():
    db = SessionLocal()

    # Get a booking
    booking = db.query(Booking).filter(Booking.status == BookingStatus.CONFIRMED).first()

    if not booking:
        print("No bookings found!")
        return

    print(f"Using booking #{booking.id}")
    print(f"Student: {booking.student.full_name} ({booking.student.email})")
    print(f"Instructor: {booking.instructor.full_name} ({booking.instructor.email})")

    test_email = input("\nEnter email address for test (or press Enter to use student email): ")
    if not test_email:
        test_email = booking.student.email

    # Temporarily change emails
    original_student = booking.student.email
    original_instructor = booking.instructor.email
    booking.student.email = test_email
    booking.instructor.email = test_email

    print(f"\nSending test emails to: {test_email}")
    result = await new_service.send_booking_confirmation(booking)

    # Restore
    booking.student.email = original_student
    booking.instructor.email = original_instructor

    if result:
        print("✅ Emails sent! Check your inbox for 2 emails.")
    else:
        print("❌ Failed to send")

    db.close()


if __name__ == "__main__":
    asyncio.run(send_test())
