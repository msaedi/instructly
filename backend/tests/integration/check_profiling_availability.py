# backend/scripts/check_profiling_availability.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from app.database import get_db
from app.models.user import User
from app.models.availability import InstructorAvailability

db = next(get_db())

# Find profiling user
user = db.query(User).filter(User.email == "profiling@instainstru.com").first()
if user:
    print(f"Found profiling user: ID={user.id}")
    
    # Count availability
    count = db.query(InstructorAvailability).filter(
        InstructorAvailability.instructor_id == user.id
    ).count()
    
    print(f"Total availability entries: {count}")
    
    # Check for current week
    today = date.today()
    week_avail = db.query(InstructorAvailability).filter(
        InstructorAvailability.instructor_id == user.id,
        InstructorAvailability.date >= today,
        InstructorAvailability.date <= date(2025, 6, 25)
    ).all()
    
    print(f"This week availability: {len(week_avail)}")
    for avail in week_avail[:5]:  # Show first 5
        print(f"  - {avail.date}: {len(avail.time_slots)} slots")
else:
    print("Profiling user not found!")

db.close()