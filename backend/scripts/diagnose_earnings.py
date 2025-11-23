#!/usr/bin/env python3
"""
Read-only diagnostic script for instructor earnings investigation.
Queries database to verify PaymentIntent and Booking data for Sarah C.
"""

from pathlib import Path
import sys

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text

from app.database import SessionLocal

# Sarah's user_id
SARAH_USER_ID = "01KANWZH8KAZSKYH3NPQZ82ARW"

def main():
    session = SessionLocal()

    try:
        print("=" * 80)
        print("DIAGNOSTIC REPORT: Instructor Earnings Investigation")
        print("=" * 80)
        print("\nInstructor: Sarah C.")
        print(f"User ID: {SARAH_USER_ID}\n")

        # 1. Get instructor profile ID
        print("1. INSTRUCTOR PROFILE LOOKUP")
        print("-" * 80)
        profile_query = text("""
            SELECT id, user_id, created_at
            FROM instructor_profiles
            WHERE user_id = :user_id
        """)
        profile_result = session.execute(profile_query, {"user_id": SARAH_USER_ID}).fetchone()
        if profile_result:
            profile_id = profile_result[0]
            print("✓ Found instructor profile:")
            print(f"  Profile ID: {profile_id}")
            print(f"  User ID: {profile_result[1]}")
            print(f"  Created: {profile_result[2]}")
        else:
            print("✗ No instructor profile found!")
            profile_id = None

        # 2. Get bookings for Sarah
        print("\n2. BOOKINGS FOR SARAH")
        print("-" * 80)
        bookings_query = text("""
            SELECT id, booking_date, start_time, end_time, status, total_price, student_id
            FROM bookings
            WHERE instructor_id = :instructor_id
            ORDER BY booking_date, start_time
        """)
        bookings = session.execute(bookings_query, {"instructor_id": SARAH_USER_ID}).fetchall()
        print(f"Total bookings found: {len(bookings)}")
        if bookings:
            print("\nSample bookings:")
            for i, booking in enumerate(bookings[:5], 1):
                print(f"  {i}. Booking ID: {booking[0]}")
                print(f"     Date: {booking[1]}, Time: {booking[2]} - {booking[3]}")
                print(f"     Status: {booking[4]}, Price: ${booking[5]}")
                print(f"     Student ID: {booking[6]}")
        else:
            print("  No bookings found!")

        # 3. Get payment intents joined to bookings
        print("\n3. PAYMENT INTENTS FOR SARAH'S BOOKINGS")
        print("-" * 80)
        payments_query = text("""
            SELECT
                pi.id as payment_intent_id,
                pi.status,
                pi.amount,
                pi.application_fee,
                pi.created_at,
                pi.booking_id,
                b.booking_date,
                b.status as booking_status
            FROM payment_intents pi
            JOIN bookings b ON pi.booking_id = b.id
            WHERE b.instructor_id = :instructor_id
            ORDER BY pi.created_at DESC
        """)
        payments = session.execute(payments_query, {"instructor_id": SARAH_USER_ID}).fetchall()
        print(f"Total payment intents found: {len(payments)}")

        succeeded_count = 0
        if payments:
            print("\nAll payment intents:")
            for i, payment in enumerate(payments, 1):
                status = payment[1]
                if status == "succeeded":
                    succeeded_count += 1
                print(f"  {i}. PaymentIntent ID: {payment[0]}")
                print(f"     Status: {status}")
                print(f"     Amount: ${payment[2] / 100 if payment[2] else 0:.2f}")
                print(f"     Application Fee: ${payment[3] / 100 if payment[3] else 0:.2f}")
                print(f"     Booking ID: {payment[5]}")
                print(f"     Booking Date: {payment[6]}, Status: {payment[7]}")
                print(f"     Created: {payment[4]}")
                print()
        else:
            print("  No payment intents found!")

        print(f"\nPayment intents with status='succeeded': {succeeded_count}")

        # 4. Check what get_instructor_earnings would return
        print("\n4. SIMULATING get_instructor_earnings() QUERY")
        print("-" * 80)
        print("Query filters:")
        print("  - PaymentIntent.status = 'succeeded'")
        print(f"  - Booking.instructor_id = '{SARAH_USER_ID}' (user_id)")
        print()

        earnings_query = text("""
            SELECT
                COALESCE(SUM(pi.amount - pi.application_fee), 0) as total_earned,
                COALESCE(SUM(pi.application_fee), 0) as total_fees,
                COUNT(pi.id) as booking_count,
                COALESCE(AVG(pi.amount - pi.application_fee), 0) as average_earning
            FROM payment_intents pi
            JOIN bookings b ON pi.booking_id = b.id
            WHERE pi.status = 'succeeded'
              AND b.instructor_id = :instructor_id
        """)
        earnings_result = session.execute(earnings_query, {"instructor_id": SARAH_USER_ID}).fetchone()
        print("Results (using user_id filter):")
        print(f"  Total earned: ${earnings_result[0] / 100 if earnings_result[0] else 0:.2f}")
        print(f"  Total fees: ${earnings_result[1] / 100 if earnings_result[1] else 0:.2f}")
        print(f"  Booking count: {earnings_result[2]}")
        print(f"  Average earning: ${earnings_result[3] / 100 if earnings_result[3] else 0:.2f}")

        # 5. Check what would happen if we used profile_id (WRONG)
        if profile_id:
            print("\n5. SIMULATING get_instructor_earnings() WITH PROFILE_ID (WRONG)")
            print("-" * 80)
            print("Query filters:")
            print("  - PaymentIntent.status = 'succeeded'")
            print(f"  - Booking.instructor_id = '{profile_id}' (profile_id - WRONG!)")
            print()

            wrong_earnings_query = text("""
                SELECT
                    COALESCE(SUM(pi.amount - pi.application_fee), 0) as total_earned,
                    COALESCE(SUM(pi.application_fee), 0) as total_fees,
                    COUNT(pi.id) as booking_count
                FROM payment_intents pi
                JOIN bookings b ON pi.booking_id = b.id
                WHERE pi.status = 'succeeded'
                  AND b.instructor_id = :profile_id
            """)
            wrong_result = session.execute(wrong_earnings_query, {"profile_id": profile_id}).fetchone()
            print("Results (using profile_id filter - WRONG):")
            print(f"  Total earned: ${wrong_result[0] / 100 if wrong_result[0] else 0:.2f}")
            print(f"  Total fees: ${wrong_result[1] / 100 if wrong_result[1] else 0:.2f}")
            print(f"  Booking count: {wrong_result[2]}")
            print("  ⚠️  This would return 0 because Booking.instructor_id stores user_id, not profile_id!")

        # 6. Check what get_instructor_payment_history would return
        print("\n6. SIMULATING get_instructor_payment_history() QUERY")
        print("-" * 80)
        print("Query filters:")
        print("  - PaymentIntent.status = 'succeeded'")
        print(f"  - Booking.instructor_id = '{SARAH_USER_ID}' (user_id)")
        print()

        history_query = text("""
            SELECT
                pi.id,
                pi.status,
                pi.amount,
                pi.application_fee,
                pi.created_at,
                pi.booking_id
            FROM payment_intents pi
            JOIN bookings b ON pi.booking_id = b.id
            WHERE pi.status = 'succeeded'
              AND b.instructor_id = :instructor_id
            ORDER BY pi.created_at DESC
            LIMIT 100
        """)
        history_results = session.execute(history_query, {"instructor_id": SARAH_USER_ID}).fetchall()
        print(f"Results: {len(history_results)} payment intents found")
        if history_results:
            print("\nSample payment intents:")
            for i, payment in enumerate(history_results[:3], 1):
                print(f"  {i}. PaymentIntent ID: {payment[0]}")
                print(f"     Status: {payment[1]}")
                print(f"     Amount: ${payment[2] / 100 if payment[2] else 0:.2f}")
                print(f"     Booking ID: {payment[5]}")
        else:
            print("  No payment intents found!")

        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"✓ Bookings found: {len(bookings)}")
        print(f"✓ Payment intents found: {len(payments)}")
        print(f"✓ Payment intents with status='succeeded': {succeeded_count}")
        print(f"✓ get_instructor_earnings() would return {earnings_result[2]} bookings (using user_id)")
        print(f"✓ get_instructor_payment_history() would return {len(history_results)} payment intents")
        if profile_id:
            print("⚠️  If get_instructor_earnings() used profile_id, it would return 0 bookings")

    finally:
        session.close()

if __name__ == "__main__":
    main()
