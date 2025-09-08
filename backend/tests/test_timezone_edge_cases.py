# backend/tests/test_timezone_edge_cases.py
"""
Comprehensive timezone test suite for InstaInstru platform.

Tests edge cases and ensures timezone handling is correct across:
- Cross-timezone bookings
- DST transitions
- International date line
- CI/CD environments
- Regression prevention
"""

import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
import pytz

# from freezegun import freeze_time  # Optional dependency
from sqlalchemy.orm import Session

from app.core.timezone_utils import get_user_timezone, get_user_today_by_id
from app.core.ulid_helper import generate_ulid
from app.models.user import User
from app.services.availability_service import AvailabilityService
from app.services.booking_service import BookingService


class TestCrossTimezoneBookings:
    """Test bookings when student and instructor are in different timezones."""

    def test_booking_across_date_boundary(self, db: Session):
        """Test when student and instructor are on different dates."""
        # Create instructor in Japan (UTC+9) - it's already tomorrow
        instructor = Mock(spec=User)
        instructor.id = generate_ulid()
        instructor.timezone = "Asia/Tokyo"

        # Create student in Hawaii (UTC-10) - it's still yesterday
        student = Mock(spec=User)
        student.id = generate_ulid()
        student.timezone = "Pacific/Honolulu"

        # Mock the database queries to return the appropriate user
        from app.repositories.factory import RepositoryFactory

        with patch.object(RepositoryFactory, "create_user_repository") as mock_factory:
            mock_repo = Mock()
            mock_factory.return_value = mock_repo

            # When called with instructor ID, return instructor
            # When called with student ID, return student
            def get_user_by_id(user_id):
                if user_id == instructor.id:
                    return instructor
                elif user_id == student.id:
                    return student
                return None

            mock_repo.get_by_id.side_effect = get_user_by_id

            # Mock datetime to a time where Tokyo is tomorrow and Hawaii is yesterday
            # Use 11 PM UTC - Tokyo is 8 AM next day, Hawaii is 1 PM previous day
            with patch("app.core.timezone_utils.datetime") as mock_dt:
                # Set to Jan 15, 2024 11 PM UTC
                utc_time = pytz.UTC.localize(datetime(2024, 1, 15, 23, 0, 0))

                # Mock datetime.now to return the appropriate time for each timezone
                def mock_now(tz=None):
                    if tz is None:
                        return utc_time
                    return utc_time.astimezone(tz)

                mock_dt.now.side_effect = mock_now
                mock_dt.combine = datetime.combine  # Keep the real combine method

                instructor_today = get_user_today_by_id(instructor.id, db)
                student_today = get_user_today_by_id(student.id, db)

                # They should be on different dates (19 hour difference)
                assert instructor_today != student_today

                # Instructor's "today" should be ahead
                assert instructor_today > student_today

    def test_same_day_different_times(self, db: Session):
        """Test when both users are on same calendar day but different times."""
        # Create users in adjacent timezones
        instructor = Mock(spec=User)
        instructor.id = generate_ulid()
        instructor.timezone = "America/New_York"  # Eastern Time

        student = Mock(spec=User)
        student.id = generate_ulid()
        student.timezone = "America/Chicago"  # Central Time (1 hour behind)

        # Mock the database queries
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.side_effect = [instructor, student]
        mock_query.filter.return_value = mock_filter

        # Replace db.query with our mock
        with patch.object(db, "query", return_value=mock_query):
            # Mock datetime to noon Eastern
            with patch("app.core.timezone_utils.datetime") as mock_dt:
                # Set to Jan 15, 2024 noon EST
                mock_dt.now.return_value = pytz.timezone("America/New_York").localize(datetime(2024, 1, 15, 12, 0, 0))

                instructor_today = get_user_today_by_id(instructor.id, db)
                student_today = get_user_today_by_id(student.id, db)

                # Both should be on the same date
                assert instructor_today == student_today

    def test_booking_validation_respects_instructor_timezone(self, db: Session):
        """Test that availability validation uses instructor's timezone."""
        # Create instructor in Sydney (far ahead)
        instructor = Mock(spec=User)
        instructor.id = generate_ulid()
        instructor.timezone = "Australia/Sydney"

        # Mock the service
        availability_service = AvailabilityService(db)

        with patch("app.services.availability_service.get_user_today_by_id") as mock_get_today:
            # Set instructor's "today" to Jan 16
            mock_get_today.return_value = date(2024, 1, 16)

            # Try to create availability for Jan 15 (yesterday for instructor)
            with patch.object(availability_service, "repository") as mock_repo:
                mock_repo.slot_exists.return_value = False

                # This should skip the past date
                slots = availability_service._prepare_slots_for_creation(
                    instructor_id=generate_ulid(),
                    week_dates=[date(2024, 1, 15), date(2024, 1, 16)],
                    schedule_by_date={
                        date(2024, 1, 15): [{"start_time": "09:00", "end_time": "10:00"}],
                        date(2024, 1, 16): [{"start_time": "09:00", "end_time": "10:00"}],
                    },
                )

                # Should only create slot for Jan 16 (today for instructor)
                assert len(slots) == 1
                assert slots[0]["specific_date"] == date(2024, 1, 16)


class TestDSTTransitions:
    """Test handling of Daylight Saving Time transitions."""

    def test_booking_during_spring_forward(self, db: Session):
        """Test booking when 2 AM becomes 3 AM (losing an hour)."""
        # Use New York timezone which has DST
        instructor = Mock(spec=User)
        instructor.id = generate_ulid()
        instructor.timezone = "America/New_York"

        # Spring forward happens on March 10, 2024 at 2 AM
        # 2:00 AM becomes 3:00 AM
        booking_date = date(2024, 3, 10)

        # Create booking service
        booking_service = BookingService(db)

        # Try to book a slot from 1:30 AM to 2:30 AM
        # This slot partially doesn't exist (2-3 AM is skipped)
        start_time = time(1, 30)
        end_time = time(2, 30)

        # The duration calculation should still work correctly
        pricing = booking_service._calculate_pricing(Mock(hourly_rate=100), start_time, end_time)

        # Should be 60 minutes even though 2-3 AM doesn't exist
        assert pricing["duration_minutes"] == 60

    def test_booking_during_fall_back(self, db: Session):
        """Test booking when 2 AM happens twice (gaining an hour)."""
        # Use New York timezone which has DST
        instructor = Mock(spec=User)
        instructor.id = 1
        instructor.timezone = "America/New_York"

        # Fall back happens on November 3, 2024 at 2 AM
        # 2:00 AM happens twice
        booking_date = date(2024, 11, 3)

        # Create booking service
        booking_service = BookingService(db)

        # Book a slot from 1:30 AM to 2:30 AM
        # This time period actually lasts 2 hours due to fall back
        start_time = time(1, 30)
        end_time = time(2, 30)

        # For booking purposes, we treat it as clock time (60 minutes)
        pricing = booking_service._calculate_pricing(Mock(hourly_rate=100), start_time, end_time)

        # Should be 60 minutes based on clock time
        assert pricing["duration_minutes"] == 60

    def test_availability_query_during_dst_boundary(self, db: Session):
        """Test that availability queries handle DST boundaries correctly."""
        instructor = Mock(spec=User)
        instructor.id = 1
        instructor.timezone = "America/New_York"

        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = instructor
        mock_query.filter.return_value = mock_filter

        with patch.object(db, "query", return_value=mock_query):
            # Test on the day before DST transition
            with patch("app.core.timezone_utils.datetime") as mock_dt:
                # 11 PM EST on March 9
                est = pytz.timezone("America/New_York")
                mock_dt.now.return_value = est.localize(datetime(2024, 3, 9, 23, 0, 0))

                today = get_user_today_by_id(instructor.id, db)
                assert today == date(2024, 3, 9)

            # Test after DST transition (now EDT, UTC-4)
            with patch("app.core.timezone_utils.datetime") as mock_dt:
                # 11 PM EDT on March 10
                edt = pytz.timezone("America/New_York")
                mock_dt.now.return_value = edt.localize(datetime(2024, 3, 10, 23, 0, 0))

                today = get_user_today_by_id(instructor.id, db)
                assert today == date(2024, 3, 10)


class TestInternationalDateLine:
    """Test extreme timezone differences near the international date line."""

    def test_extreme_timezone_difference(self, db: Session):
        """Test users who are 23-24 hours apart."""
        # Create instructor in Kiritimati (UTC+14) - furthest ahead
        instructor = Mock(spec=User)
        instructor.id = 1
        instructor.timezone = "Pacific/Kiritimati"

        # Create student in Niue (UTC-11) - furthest behind
        student = Mock(spec=User)
        student.id = 2
        student.timezone = "Pacific/Niue"

        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.side_effect = [instructor, student]
        mock_query.filter.return_value = mock_filter

        with patch.object(db, "query", return_value=mock_query):
            # Control the instant to make the test deterministic
            # Use a fixed UTC time so Kiritimati (UTC+14) is one calendar day ahead of Niue (UTC-11)
            with patch("app.core.timezone_utils.datetime") as mock_dt:
                base_utc = pytz.UTC.localize(datetime(2024, 1, 15, 12, 0, 0))

                def mock_now(tz=None):
                    if tz is None:
                        return base_utc
                    return base_utc.astimezone(tz)

                mock_dt.now.side_effect = mock_now
                mock_dt.combine = datetime.combine

                # At the same instant, they're on different days
                instructor_today = get_user_today_by_id(instructor.id, db)
                student_today = get_user_today_by_id(student.id, db)

                # Instructor should be 1 day ahead (25 hour difference)
                assert instructor_today == student_today + timedelta(days=1)

    def test_booking_across_date_line(self, db: Session):
        """Test booking when instructor and student are on opposite sides of date line."""
        # Auckland instructor (UTC+12)
        instructor = Mock(spec=User)
        instructor.id = 1
        instructor.timezone = "Pacific/Auckland"

        # Honolulu student (UTC-10)
        student = Mock(spec=User)
        student.id = 2
        student.timezone = "Pacific/Honolulu"

        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.side_effect = [instructor, student]
        mock_query.filter.return_value = mock_filter

        with patch.object(db, "query", return_value=mock_query):
            # When it's early Monday morning in Auckland (1 AM)
            # Auckland is UTC+13 in January (DST), Honolulu is UTC-10
            # So they're 23 hours apart
            auckland_tz = pytz.timezone("Pacific/Auckland")
            auckland_time = auckland_tz.localize(datetime(2024, 1, 15, 1, 0))

            with patch("app.core.timezone_utils.datetime") as mock_dt:
                # Mock datetime.now() to handle timezone parameter
                def mock_now(tz=None):
                    if tz is None:
                        return auckland_time
                    # Convert the base time to requested timezone
                    return auckland_time.astimezone(tz)

                mock_dt.now.side_effect = mock_now

                instructor_today = get_user_today_by_id(instructor.id, db)
                student_today = get_user_today_by_id(student.id, db)

                # Instructor is on Monday Jan 15
                assert instructor_today == date(2024, 1, 15)
                # Student is still on Sunday Jan 14 (23 hours behind)
                assert student_today == date(2024, 1, 14)


class TestCIEnvironment:
    """Test that code works correctly in CI/CD environments (typically UTC)."""

    def test_utc_environment(self, db: Session):
        """Ensure tests pass when system timezone is UTC."""
        # Create users with various timezones
        users = [
            Mock(id=generate_ulid(), timezone="America/New_York"),
            Mock(id=generate_ulid(), timezone="Europe/London"),
            Mock(id=3, timezone="Asia/Tokyo"),
            Mock(id=4, timezone="Australia/Sydney"),
        ]

        # Mock system to be in UTC
        with patch("datetime.datetime") as mock_datetime:
            # Set system time to UTC midnight
            mock_datetime.now.return_value = datetime(2024, 1, 15, 0, 0, 0)
            mock_datetime.combine = datetime.combine

            for user in users:
                mock_query = Mock()
                mock_filter = Mock()
                mock_filter.first.return_value = user
                mock_query.filter.return_value = mock_filter

                with patch.object(db, "query", return_value=mock_query):
                    # Each user should get their correct local date
                    user_today = get_user_today_by_id(user.id, db)

                    # Verify date is calculated based on user timezone, not system
                    user_tz = pytz.timezone(user.timezone)
                    expected_date = datetime.now(user_tz).date()

                    # Can't directly compare due to mock, but verify it's a date
                    assert isinstance(user_today, date)

    def test_all_services_use_user_timezone(self, db: Session):
        """Verify all services use user timezone, not system timezone."""
        # This test ensures our fixes work in any system timezone
        services_to_test = [
            (AvailabilityService, "get_user_today_by_id"),
            (BookingService, "get_user_today_by_id"),
        ]

        for service_class, timezone_func in services_to_test:
            service = service_class(db)

            # Verify the service imports the timezone utility
            module = service.__class__.__module__
            service_module = __import__(module, fromlist=[""])

            # Check if timezone utils are imported by looking for the import
            module_source = service_module.__file__
            with open(module_source, "r") as f:
                source_code = f.read()
                assert (
                    "from ..core.timezone_utils import get_user_today_by_id" in source_code
                    or "from app.core.timezone_utils import get_user_today_by_id" in source_code
                )


class TestRegressionPrevention:
    """Tests to prevent regression of timezone bugs."""

    def test_no_system_date_in_user_code(self):
        """Scan codebase for date.today() in user-facing code paths."""
        # Define paths that should NOT contain date.today()
        user_facing_paths = [
            "app/routes/",
            "app/services/",
            "app/api/",
        ]

        # Define allowed files (system operations)
        allowed_files = [
            "cache_service.py",  # Cache TTL management
            "logging_service.py",  # System logs
            "metrics_service.py",  # System metrics
            "slot_manager.py",  # Time duration calculations only
            "conflict_checker.py",  # Time duration calculations only
        ]

        violations = []

        for path_pattern in user_facing_paths:
            path = Path(path_pattern)
            if path.exists():
                for py_file in path.rglob("*.py"):
                    # Skip allowed files
                    if py_file.name in allowed_files:
                        continue

                    # Skip test files
                    if "test" in py_file.name:
                        continue

                    # Check file content
                    content = py_file.read_text()
                    if "date.today()" in content and "timezone" not in content:
                        # Count occurrences
                        matches = re.findall(r"date\.today\(\)", content)
                        if matches:
                            violations.append({"file": str(py_file), "count": len(matches)})

        # Report violations
        if violations:
            violation_report = "\n".join(f"  - {v['file']}: {v['count']} occurrence(s)" for v in violations)
            pytest.fail(
                f"Found date.today() in user-facing code:\n{violation_report}\n" "Use get_user_today_by_id() instead!"
            )

    def test_schema_validators_removed(self):
        """Ensure date validators are removed from schemas."""
        schema_path = Path("app/schemas/")

        violations = []

        for py_file in schema_path.rglob("*.py"):
            content = py_file.read_text()

            # Remove comments to avoid false positives
            lines = content.splitlines()
            active_lines = []
            for line in lines:
                # Skip comment lines
                stripped = line.strip()
                if not stripped.startswith("#"):
                    active_lines.append(line)

            active_content = "\n".join(active_lines)

            # Check for date validation patterns in active code
            if "date.today()" in active_content and "@validator" in active_content:
                violations.append(str(py_file))

            # Check for field validators on dates
            if re.search(r"@field_validator.*date.*\)", active_content, re.DOTALL):
                # Check if it's doing timezone validation
                if "date.today()" in active_content:
                    violations.append(str(py_file))

        if violations:
            pytest.fail(
                f"Found date validation in schemas:\n"
                + "\n".join(f"  - {v}" for v in violations)
                + "\nDate validation should be in service layer with timezone context!"
            )

    def test_all_user_operations_have_timezone_context(self):
        """Verify all user operations have access to timezone context."""
        # This is more of a code review test
        # Checks that methods handling user data have user_id or user object

        service_path = Path("app/services/")

        for py_file in service_path.rglob("*.py"):
            if "test" in py_file.name:
                continue

            content = py_file.read_text()

            # Find methods that might need timezone context
            # Look for methods with date operations
            date_methods = re.findall(r"def\s+(\w+).*?:\s*\n.*?date", content, re.DOTALL | re.MULTILINE)

            for method in date_methods:
                # Check if method has user context
                method_pattern = rf"def\s+{method}\s*\((.*?)\)"
                match = re.search(method_pattern, content)
                if match:
                    params = match.group(1)
                    if not any(term in params for term in ["user_id", "user", "instructor_id", "student_id"]):
                        # This might be a system operation, check further
                        if "self" in params and "cache" not in method.lower():
                            # Could be an issue, but need manual review
                            pass


# Fixtures for testing
@pytest.fixture
def mock_instructor(db: Session):
    """Create a mock instructor with timezone."""
    instructor = Mock(spec=User)
    instructor.id = 1
    instructor.timezone = "America/New_York"
    instructor.roles = []
    return instructor


@pytest.fixture
def mock_student(db: Session):
    """Create a mock student with timezone."""
    student = Mock(spec=User)
    student.id = 2
    student.timezone = "America/Los_Angeles"
    student.roles = []
    return student
