"""
Check if availability data exists in the database.
"""

from datetime import date, timedelta

from app.database import SessionLocal
from app.models.availability import AvailabilitySlot
from app.models.user import User

db = SessionLocal()

# Check for instructor 1
instructor_id = 1
instructor = db.query(User).filter(User.id == instructor_id).first()
print(f"Instructor {instructor_id}: {instructor.full_name if instructor else 'NOT FOUND'}")

if instructor:
    # Check availability slots
    today = date.today()
    end_date = today + timedelta(days=30)

    slots = (
        db.query(AvailabilitySlot)
        .filter(
            AvailabilitySlot.instructor_id == instructor_id,
            AvailabilitySlot.specific_date >= today,
            AvailabilitySlot.specific_date <= end_date,
        )
        .limit(10)
        .all()
    )

    print(f"\nAvailability slots found: {len(slots)}")
    for slot in slots[:5]:
        print(f"  Date: {slot.specific_date}, Time: {slot.start_time} - {slot.end_time}")

    # Check total slots for this instructor
    total_slots = db.query(AvailabilitySlot).filter(AvailabilitySlot.instructor_id == instructor_id).count()
    print(f"\nTotal slots for instructor: {total_slots}")

db.close()
