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

from alembic import op
import sqlalchemy as sa

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
    # Note: Availability is now stored in availability_days table (bitmap format)
    # No indexes needed here - bitmap queries use availability_days indexes from migration 006

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

    # Index for student's bookings by status (for history queries)
    op.create_index(
        "idx_bookings_student_status",
        "bookings",
        ["student_id", "status", "booking_date"],
    )

    # Index for instructor's bookings by status
    op.create_index(
        "idx_bookings_instructor_status",
        "bookings",
        ["instructor_id", "status", "booking_date"],
    )

    # Index for time-based conflict checking
    op.create_index(
        "idx_bookings_time_conflicts",
        "bookings",
        ["instructor_id", "booking_date", "start_time", "end_time"],
    )

    # Note: Availability overlap queries now use availability_days bitmap table
    # No index needed here - bitmap queries use availability_days indexes from migration 006

    # Instructor search and filtering indexes
    print("Creating instructor search indexes...")

    # Text search index for user names (PostgreSQL GIN with fallback)
    try:
        # PostgreSQL GIN index for text search on combined name fields
        op.execute(
            """
            CREATE INDEX idx_users_name_gin
            ON users
            USING gin(to_tsvector('english', first_name || ' ' || last_name))
        """
        )
        print("- Created GIN index for name text search (PostgreSQL)")
    except Exception:
        # Fallback to regular indexes for other databases
        op.create_index(
            "idx_users_last_name",
            "users",
            ["last_name"],
        )
        op.create_index(
            "idx_users_first_name",
            "users",
            ["first_name"],
        )
        print("- Created regular indexes for names")

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

    # Search history and analytics indexes
    print("Creating search and analytics indexes...")

    # NOTE: Search history indexes already created in 001_initial_schema.py:
    # - idx_search_history_user_last_searched
    # - idx_search_history_guest_session
    # - idx_search_history_normalized_query

    # Index for blackout dates lookup
    op.create_index(
        "idx_blackout_dates_instructor",
        "blackout_dates",
        ["instructor_id", "date"],
    )

    # Index for service catalog search terms (GIN index for array search)
    try:
        op.execute(
            """
            CREATE INDEX idx_service_catalog_search_terms_gin
            ON service_catalog
            USING gin(search_terms)
        """
        )
        print("- Created GIN index for search_terms array (PostgreSQL)")
    except Exception:
        print("- Skipped search_terms GIN index (non-PostgreSQL)")

    # Index for instructor services by catalog ID (for filtering)
    op.create_index(
        "idx_instructor_services_catalog_active",
        "instructor_services",
        ["service_catalog_id", "is_active"],
    )

    print("- Created search history and analytics indexes")

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
        op.execute("DROP INDEX IF EXISTS idx_users_name_gin")
        print("- Dropped GIN index for name text search")
    except Exception:
        # Try to drop the regular index fallback
        try:
            op.drop_index("idx_users_last_name", table_name="users")
            op.drop_index("idx_users_first_name", table_name="users")
            print("- Dropped regular indexes for names")
        except Exception:
            pass

    # Drop search and analytics indexes
    print("Dropping search and analytics indexes...")

    # Use DROP INDEX IF EXISTS for all indexes to handle cases where they don't exist
    try:
        op.execute("DROP INDEX IF EXISTS idx_instructor_services_catalog_active")
        print("- Dropped idx_instructor_services_catalog_active")
    except Exception:
        pass

    try:
        op.execute("DROP INDEX IF EXISTS idx_service_catalog_search_terms_gin")
        print("- Dropped GIN index for search_terms")
    except Exception:
        pass

    try:
        op.execute("DROP INDEX IF EXISTS idx_blackout_dates_instructor")
        print("- Dropped idx_blackout_dates_instructor")
    except Exception:
        pass

    # Drop booking and availability indexes (use IF EXISTS for safety)
    try:
        op.execute("DROP INDEX IF EXISTS idx_bookings_time_conflicts")
        op.execute("DROP INDEX IF EXISTS idx_bookings_instructor_status")
        op.execute("DROP INDEX IF EXISTS idx_bookings_student_status")
        op.execute("DROP INDEX IF EXISTS idx_bookings_student_date")
        op.execute("DROP INDEX IF EXISTS idx_bookings_upcoming")
        op.execute("DROP INDEX IF EXISTS idx_bookings_date_status")
        print("- Dropped booking and availability indexes")
    except Exception as e:
        print(f"- Some indexes may not exist: {e}")

    print("Performance indexes dropped successfully!")
