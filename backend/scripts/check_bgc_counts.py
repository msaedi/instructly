#!/usr/bin/env python3
"""Quick script to check BGC case counts in the database."""

from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal
from app.models.instructor import InstructorProfile

db = SessionLocal()
try:
    total = db.query(InstructorProfile).count()
    review = db.query(InstructorProfile).filter(InstructorProfile.bgc_status.in_(['review', 'consider'])).count()
    pending = db.query(InstructorProfile).filter(InstructorProfile.bgc_status == 'pending').count()
    all_with_status = db.query(InstructorProfile).filter(InstructorProfile.bgc_status.in_(['review', 'consider', 'pending'])).count()

    print(f'Total instructor profiles: {total}')
    print(f'Review/Consider status: {review}')
    print(f'Pending status: {pending}')
    print(f'All (review+consider+pending): {all_with_status}')
finally:
    db.close()
