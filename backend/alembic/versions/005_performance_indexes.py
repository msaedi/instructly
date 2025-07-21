# backend/alembic/versions/005_performance_indexes.py
"""Performance indexes - Query optimization

Revision ID: 005_performance_indexes
Revises: 004_booking_system
Create Date: 2024-12-21 00:00:04.000000

This migration adds all performance-related indexes that weren't
created with their base tables. These are primarily composite
and partial indexes for common query patterns.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_performance_indexes"
down_revision: Union[str, None] = "004_booking_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create performance indexes for common query patterns."""
    print("Creating performance indexes...")

    # Booking performance indexes
    op.create_index(
        "idx_bookings_date_status",
        "bookings",
        ["booking_date", "status"],
    )

    # Availability performance indexes
    # This index is optimized for week view queries
    op.create_index(
        "idx_availability_week_lookup",
        "availability_slots",
        ["instructor_id", "specific_date", "start_time"],
    )

    # Partial index for future dates (common query)
    op.create_index(
        "idx_availability_future",
        "availability_slots",
        ["instructor_id", "specific_date"],
    )

    # Partial index for upcoming bookings (confirmed only)
    op.create_index(
        "idx_bookings_upcoming",
        "bookings",
        ["booking_date", "status"],
        postgresql_where=sa.text("status = 'CONFIRMED'"),
    )

    # Index for student's bookings by date
    op.create_index(
        "idx_bookings_student_date",
        "bookings",
        ["student_id", "booking_date"],
    )

    # Instructor search and filtering indexes
    print("Creating instructor search indexes...")

    # Text search index for user names (PostgreSQL GIN with fallback)
    try:
        # PostgreSQL GIN index for text search
        op.execute(
            """
            CREATE INDEX idx_users_full_name_gin
            ON users
            USING gin(to_tsvector('english', full_name))
        """
        )
        print("- Created GIN index for full_name text search (PostgreSQL)")
    except Exception:
        # Fallback to regular index for other databases
        op.create_index(
            "idx_users_full_name",
            "users",
            ["full_name"],
        )
        print("- Created regular index for full_name")

    # Text search index for instructor bio (PostgreSQL GIN with fallback)
    try:
        op.execute(
            """
            CREATE INDEX idx_instructor_profiles_bio_gin
            ON instructor_profiles
            USING gin(to_tsvector('english', bio))
        """
        )
        print("- Created GIN index for bio text search (PostgreSQL)")
    except Exception:
        # For non-PostgreSQL databases, we skip indexing TEXT columns
        print("- Skipped bio index (TEXT field, non-PostgreSQL)")

    # Case-insensitive index on service catalog name
    op.create_index(
        "idx_service_catalog_name_lower",
        "service_catalog",
        [sa.text("LOWER(name)")],
    )
    print("- Created case-insensitive index for service catalog search")

    # Composite index for price range queries with active instructor services
    op.create_index(
        "idx_instructor_services_active_price",
        "instructor_services",
        ["is_active", "hourly_rate"],
    )
    print("- Created composite index for price filtering")

    # Composite index for instructor profile lookups
    op.create_index(
        "idx_instructor_services_profile_active",
        "instructor_services",
        ["instructor_profile_id", "is_active"],
    )
    print("- Created composite index for instructor-service joins")

    # Index for category-based filtering
    op.create_index(
        "idx_service_catalog_category_active",
        "service_catalog",
        ["category_id", "is_active"],
    )
    print("- Created composite index for category filtering")

    # Note: The following indexes were already created in previous migrations:
    # - idx_bookings_instructor_date_status (composite index for instructor dashboard)
    # - idx_bookings_instructor_service_id (foreign key index)
    # - idx_instructor_services_instructor_profile_id (foreign key index)
    # - instructor_services.is_active (single column index)

    print("Performance indexes created successfully!")
    print("- Added composite indexes for common query patterns")
    print("- Added partial index for upcoming bookings")
    print("- Added text search indexes for instructor filtering")
    print("- Added specialized indexes for price and skill queries")


def downgrade() -> None:
    """Drop performance indexes."""
    print("Dropping performance indexes...")

    # Drop instructor search indexes
    print("Dropping instructor search indexes...")
    op.drop_index("idx_service_catalog_category_active", table_name="service_catalog")
    op.drop_index("idx_instructor_services_profile_active", table_name="instructor_services")
    op.drop_index("idx_instructor_services_active_price", table_name="instructor_services")
    op.drop_index("idx_service_catalog_name_lower", table_name="service_catalog")

    # Drop text search indexes with try/except for database compatibility
    try:
        op.execute("DROP INDEX IF EXISTS idx_instructor_profiles_bio_gin")
        print("- Dropped GIN index for bio text search")
    except Exception:
        pass

    try:
        op.execute("DROP INDEX IF EXISTS idx_users_full_name_gin")
        print("- Dropped GIN index for full_name text search")
    except Exception:
        # Try to drop the regular index fallback
        try:
            op.drop_index("idx_users_full_name", table_name="users")
            print("- Dropped regular index for full_name")
        except Exception:
            pass

    # Drop booking and availability indexes
    op.drop_index("idx_bookings_student_date", table_name="bookings")
    op.drop_index("idx_bookings_upcoming", table_name="bookings")
    op.drop_index("idx_availability_future", table_name="availability_slots")
    op.drop_index("idx_availability_week_lookup", table_name="availability_slots")
    op.drop_index("idx_bookings_date_status", table_name="bookings")

    print("Performance indexes dropped successfully!")
