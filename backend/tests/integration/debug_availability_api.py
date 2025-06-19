# backend/scripts/debug_availability_api.py
import sys
import os
import requests
from datetime import date

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Your token
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJwcm9maWxpbmdAaW5zdGFpbnN0cnUuY29tIiwiZXhwIjoxNzUwMzAwNzc2fQ.fu9EndopTlf7PRIXx8zHc28w1whdi-PXZC5r1LAVBeE"

# Test the API
monday = "2025-06-16"
url = f"http://localhost:8000/instructors/availability-windows/week?start_date={monday}"
headers = {"Authorization": f"Bearer {token}"}

response = requests.get(url, headers=headers)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

# Also check the database directly
from app.database import get_db
from app.models.availability import InstructorAvailability

db = next(get_db())
avail = db.query(InstructorAvailability).filter(
    InstructorAvailability.instructor_id == 208,
    InstructorAvailability.date >= date(2025, 6, 16),
    InstructorAvailability.date <= date(2025, 6, 22)
).all()

print(f"\nDirect DB query found {len(avail)} entries")
for a in avail:
    print(f"  {a.date}: cleared={a.is_cleared}, slots={len(a.time_slots)}")