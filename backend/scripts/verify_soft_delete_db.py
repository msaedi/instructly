#!/usr/bin/env python3
# backend/scripts/verify_soft_delete_db.py
"""
Verify soft delete implementation in the database
Run from backend directory: python scripts/verify_soft_delete_db.py
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.booking import Booking
from app.models.service import Service
from app.models.user import User


def verify_soft_delete():
    """Check the database state for soft deleted services"""
    db = SessionLocal()

    print("🔍 VERIFYING SOFT DELETE IN DATABASE\n")

    # 1. Check all services
    print("1. All Services in Database:")
    all_services = db.query(Service).all()

    for service in all_services:
        status = "ACTIVE" if service.is_active else "INACTIVE"
        booking_count = db.query(Booking).filter(Booking.service_id == service.id).count()
        print(f"   - {service.skill}: {status} (ID: {service.id}, Bookings: {booking_count})")

    # 2. Check inactive services specifically
    print("\n2. Inactive Services:")
    inactive_services = db.query(Service).filter(Service.is_active == False).all()

    if inactive_services:
        for service in inactive_services:
            bookings = db.query(Booking).filter(Booking.service_id == service.id).all()
            print(f"   - {service.skill} (ID: {service.id})")
            print(f"     Bookings: {len(bookings)}")
            if bookings:
                print("     Sample bookings:")
                for booking in bookings[:3]:  # Show first 3
                    print(f"       - Booking {booking.id}: {booking.booking_date} - {booking.service_name}")
    else:
        print("   No inactive services found")

    # 3. Check Sarah Chen's services
    print("\n3. Sarah Chen's Services:")
    sarah = db.query(User).filter(User.email == "sarah.chen@example.com").first()
    if sarah and sarah.instructor_profile:
        print(f"   Total services: {len(sarah.instructor_profile.services)}")
        print(f"   Active services: {len(sarah.instructor_profile.active_services)}")
        for service in sarah.instructor_profile.services:
            status = "ACTIVE" if service.is_active else "INACTIVE"
            print(f"     - {service.skill}: {status}")

    # 4. Check if bookings reference inactive services
    print("\n4. Bookings Referencing Inactive Services:")
    bookings_with_inactive = db.query(Booking).join(Service).filter(Service.is_active == False).count()
    print(f"   Total bookings with inactive services: {bookings_with_inactive}")

    db.close()

    print("\n✅ Verification complete!")


if __name__ == "__main__":
    verify_soft_delete()
