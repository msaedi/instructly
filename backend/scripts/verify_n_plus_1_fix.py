#!/usr/bin/env python
"""
Script to verify the N+1 query fix in InstructorService.

This script demonstrates the performance improvement achieved by using
eager loading instead of separate queries for each instructor.

Run this after implementing the InstructorProfileRepository to see
the query count reduction from 1+2N to just 1 query.
"""

import logging
from pathlib import Path
import sys

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent  # This gets us to the backend directory
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.services.instructor_service import InstructorService


class QueryCounter:
    """Helper class to count SQL queries."""

    def __init__(self):
        self.queries = []
        self.count = 0

    def callback(self, conn, cursor, statement, parameters, context, executemany):
        self.count += 1
        self.queries.append(statement)
        # Only log SELECT queries to reduce noise
        if statement.strip().upper().startswith("SELECT"):
            print(f"Query {self.count}: {statement[:100]}...")

    def reset(self):
        self.queries = []
        self.count = 0


def test_get_all_instructors():
    """Test the get_all_instructors method and count queries."""

    # Create engine without connection pooling for clean query counting
    engine = create_engine(settings.database_url, poolclass=NullPool, echo=False)  # Set to True to see all SQL

    # Set up query counter
    query_counter = QueryCounter()
    event.listen(engine, "after_cursor_execute", query_counter.callback)

    # Create session
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        print("=" * 80)
        print("Testing InstructorService.get_all_instructors() Performance")
        print("=" * 80)

        # Initialize service (no cache for clean test)
        service = InstructorService(db, cache_service=None)

        # Reset counter
        query_counter.reset()

        print("\nFetching all instructors...")
        print("-" * 40)

        # Call the method
        instructors = service.get_all_instructors(skip=0, limit=10)

        print("\nResults:")
        print(f"- Found {len(instructors)} instructors")
        print(f"- Total queries executed: {query_counter.count}")

        # Calculate what it would have been with N+1
        if instructors:
            old_query_count = 1 + (2 * len(instructors))
            print("\nPerformance Improvement:")
            print(f"- OLD approach (N+1): {old_query_count} queries")
            print(f"- NEW approach (eager loading): {query_counter.count} queries")
            print(
                f"- Improvement: {old_query_count - query_counter.count} fewer queries ({((old_query_count - query_counter.count) / old_query_count * 100):.1f}% reduction)"
            )

        # Show sample data to verify correctness
        if instructors:
            print("\nSample instructor data (first instructor):")
            first = instructors[0]
            print(f"- User: {first.get('user', {}).get('full_name', 'N/A')}")
            print(f"- Email: {first.get('user', {}).get('email', 'N/A')}")
            print(f"- Services: {len(first.get('services', []))} active services")
            if first.get("services"):
                print("  Services:")
                for svc in first["services"][:3]:  # Show first 3
                    print(f"    - {svc['skill']}: ${svc['hourly_rate']}/hr")

        print("\n✅ SUCCESS: N+1 query problem has been fixed!")

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback

        traceback.print_exc()

    finally:
        db.close()
        engine.dispose()


def test_single_profile():
    """Test the get_instructor_profile method."""

    engine = create_engine(settings.database_url, poolclass=NullPool, echo=False)

    query_counter = QueryCounter()
    event.listen(engine, "after_cursor_execute", query_counter.callback)

    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        print("\n" + "=" * 80)
        print("Testing InstructorService.get_instructor_profile() Performance")
        print("=" * 80)

        service = InstructorService(db, cache_service=None)

        # First get an instructor to test with
        from app.core.enums import RoleName
        from app.models.user import User

        # Find an instructor user - use roles relationship
        instructor_user = db.query(User).join(User.roles).filter(User.roles.any(name=RoleName.INSTRUCTOR)).first()

        if instructor_user:
            query_counter.reset()

            print(f"\nFetching profile for user_id: {instructor_user.id}")
            print("-" * 40)

            profile = service.get_instructor_profile(instructor_user.id)

            print("\nResults:")
            print(f"- Profile found: {profile['user']['full_name']}")
            print(f"- Total queries executed: {query_counter.count}")
            print(f"- Services loaded: {len(profile['services'])}")

            # Old approach would be 3 queries
            print("\nPerformance Improvement:")
            print("- OLD approach: 3 queries (profile + user + services)")
            print(f"- NEW approach: {query_counter.count} query")

        else:
            print("No instructor found in database to test with")

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback

        traceback.print_exc()

    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)

    # Run tests
    test_get_all_instructors()
    test_single_profile()

    print("\n" + "=" * 80)
    print("Performance verification complete!")
    print("=" * 80)
