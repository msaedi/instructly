"""add booking system with instant booking

Revision ID: c7b9713e4d33
Revises: 3c104525bb35
Create Date: 2025-06-11 23:58:17.127227

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c7b9713e4d33"
down_revision: Union[str, None] = "3c104525bb35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create bookings table
    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("instructor_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("availability_slot_id", sa.Integer(), nullable=True),
        # Booking details (duplicated for historical record)
        sa.Column("booking_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("service_name", sa.String(), nullable=False),
        sa.Column("hourly_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        # Status - simple string with check constraint
        sa.Column("status", sa.String(20), nullable=False, server_default="CONFIRMED"),
        # Location details
        sa.Column("service_area", sa.String(), nullable=True),
        sa.Column("meeting_location", sa.Text(), nullable=True),
        # Messages
        sa.Column("student_note", sa.Text(), nullable=True),
        sa.Column("instructor_note", sa.Text(), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        # Cancellation details
        sa.Column("cancelled_by_id", sa.Integer(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        # Foreign keys
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["instructor_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
        ),
        sa.ForeignKeyConstraint(
            ["availability_slot_id"],
            ["availability_slots.id"],
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("idx_bookings_student_id", "bookings", ["student_id"])
    op.create_index("idx_bookings_instructor_id", "bookings", ["instructor_id"])
    op.create_index("idx_bookings_date", "bookings", ["booking_date"])
    op.create_index("idx_bookings_status", "bookings", ["status"])
    op.create_index("idx_bookings_created_at", "bookings", ["created_at"])
    op.create_index(
        "idx_bookings_instructor_date_status",
        "bookings",
        ["instructor_id", "booking_date", "status"],
    )
    op.create_index("idx_bookings_student_status", "bookings", ["student_id", "status"])

    # Add check constraint for status values
    op.create_check_constraint(
        "ck_bookings_status",
        "bookings",
        "status IN ('PENDING', 'CONFIRMED', 'COMPLETED', 'CANCELLED', 'NO_SHOW')",
    )

    # Add booking_id to availability_slots
    op.add_column("availability_slots", sa.Column("booking_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_availability_slots_booking",
        "availability_slots",
        "bookings",
        ["booking_id"],
        ["id"],
    )
    op.create_index("idx_availability_slots_booking_id", "availability_slots", ["booking_id"])

    # Add instructor settings
    op.add_column(
        "instructor_profiles",
        sa.Column(
            "min_advance_booking_hours",
            sa.Integer(),
            nullable=False,
            server_default="2",
        ),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("buffer_time_minutes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("auto_accept_bookings", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    # Remove instructor settings
    op.drop_column("instructor_profiles", "auto_accept_bookings")
    op.drop_column("instructor_profiles", "buffer_time_minutes")
    op.drop_column("instructor_profiles", "min_advance_booking_hours")

    # Remove booking_id from availability_slots
    op.drop_index("idx_availability_slots_booking_id", "availability_slots")
    op.drop_constraint("fk_availability_slots_booking", "availability_slots", type_="foreignkey")
    op.drop_column("availability_slots", "booking_id")

    # Drop constraint and indexes
    op.drop_constraint("ck_bookings_status", "bookings", type_="check")
    op.drop_index("idx_bookings_student_status", "bookings")
    op.drop_index("idx_bookings_instructor_date_status", "bookings")
    op.drop_index("idx_bookings_created_at", "bookings")
    op.drop_index("idx_bookings_status", "bookings")
    op.drop_index("idx_bookings_date", "bookings")
    op.drop_index("idx_bookings_instructor_id", "bookings")
    op.drop_index("idx_bookings_student_id", "bookings")

    # Drop table
    op.drop_table("bookings")
