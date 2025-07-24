# backend/alembic/versions/006_final_constraints.py
"""Final constraints - Schema completion and documentation

Revision ID: 006_final_constraints
Revises: 005_performance_indexes
Create Date: 2024-12-21 00:00:05.000000

This migration adds any remaining constraints and finalizes the schema.
It ensures all business rules are enforced at the database level.
Also adds monitoring infrastructure tables.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_final_constraints"
down_revision: Union[str, None] = "005_performance_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add final constraints and schema adjustments."""
    print("Adding final constraints and adjustments...")

    # Add alert history table for monitoring
    print("Creating alert_history table...")
    op.create_table(
        "alert_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("email_sent", sa.Boolean(), nullable=False, default=False),
        sa.Column("github_issue_created", sa.Boolean(), nullable=False, default=False),
        sa.Column("github_issue_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add indexes for alert history
    op.create_index("ix_alert_history_created_at", "alert_history", ["created_at"])
    op.create_index("ix_alert_history_alert_type", "alert_history", ["alert_type"])
    op.create_index("ix_alert_history_severity", "alert_history", ["severity"])

    # Add any remaining check constraints that weren't in earlier migrations

    # Ensure bookings have positive duration
    op.create_check_constraint(
        "check_duration_positive",
        "bookings",
        "duration_minutes > 0",
    )

    # Ensure bookings have non-negative price
    op.create_check_constraint(
        "check_price_non_negative",
        "bookings",
        "total_price >= 0",
    )

    # Ensure bookings have positive hourly rate
    op.create_check_constraint(
        "check_rate_positive",
        "bookings",
        "hourly_rate > 0",
    )

    # Ensure time order is correct
    op.create_check_constraint(
        "check_time_order",
        "bookings",
        "start_time < end_time",
    )

    # Add schema documentation
    print("Schema finalization complete!")
    print("")
    print("=== FINAL SCHEMA SUMMARY ===")
    print("Tables created:")
    print("  - users (authentication and roles)")
    print("  - instructor_profiles (instructor details)")
    print("  - service_categories (organize services)")
    print("  - service_catalog (predefined services)")
    print("  - instructor_services (instructor offerings with soft delete)")
    print("  - availability_slots (single-table design with date/time)")
    print("  - blackout_dates (vacation tracking)")
    print("  - bookings (instant booking system)")
    print("  - password_reset_tokens (password recovery)")
    print("  - alert_history (monitoring alerts and notifications)")
    print("")
    print("Key design decisions implemented:")
    print("  - Single-table availability design (no instructor_availability)")
    print("  - Service catalog system with categories")
    print("  - Soft delete on instructor_services via is_active flag")
    print("  - Areas of service as VARCHAR (not ARRAY)")
    print("  - Location type support for bookings")
    print("  - Instant booking (default status = CONFIRMED)")
    print("")
    print("Performance optimizations:")
    print("  - Composite indexes for common queries")
    print("  - Partial indexes for active records")
    print("  - Foreign key indexes")
    print("")
    print("Schema is ready for production use!")


def downgrade() -> None:
    """Drop final constraints and monitoring tables."""
    print("Dropping final constraints...")

    op.drop_constraint("check_time_order", "bookings", type_="check")
    op.drop_constraint("check_rate_positive", "bookings", type_="check")
    op.drop_constraint("check_price_non_negative", "bookings", type_="check")
    op.drop_constraint("check_duration_positive", "bookings", type_="check")

    # Drop alert history table
    print("Dropping alert_history table...")
    op.drop_index("ix_alert_history_severity", "alert_history")
    op.drop_index("ix_alert_history_alert_type", "alert_history")
    op.drop_index("ix_alert_history_created_at", "alert_history")
    op.drop_table("alert_history")

    print("Final constraints and monitoring tables dropped successfully!")
