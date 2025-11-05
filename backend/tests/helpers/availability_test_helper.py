# backend/tests/helpers/availability_test_helper.py
"""
Test helper layer to provide a clean, simple API for availability tests.

UPDATED FOR WORK STREAM #10: Single-table availability design.

This abstracts away the complexity of the actual service APIs and provides
the simple interface that tests expect, making tests more readable and maintainable.
"""

import asyncio
from datetime import date, time, timedelta
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.schemas.availability_window import WeekSpecificScheduleCreate
from app.services.availability_service import AvailabilityService
from app.services.bulk_operation_service import BulkOperationService
from app.services.week_operation_service import WeekOperationService
from app.utils.bitset import windows_from_bits


class AvailabilityTestHelper:
    """
    Helper class that provides a simple API for tests while handling the
    complexity of the actual service implementations.
    """

    def __init__(self, db: Session):
        self.db = db
        self.availability_service = AvailabilityService(db)
        self.week_operation_service = WeekOperationService(db)
        self.bulk_operation_service = BulkOperationService(db)

    def set_day_availability(
        self, instructor_id: int, date: date, slots: List[Dict[str, Any]], clear_existing: bool = True
    ) -> Dict[str, Any]:
        """
        Set availability for a specific day with multiple slots.

        UPDATED: Works directly with AvailabilitySlot objects.

        Args:
            instructor_id: The instructor ID
            date: The date to set availability for
            slots: List of slot dicts with start_time and end_time
            clear_existing: Whether to clear existing slots first

        Returns:
            Dict with the saved slots and success status
        """
        week_start = date - timedelta(days=date.weekday())
        windows_by_day = {date: [(slot["start_time"], slot["end_time"]) for slot in slots]}

        save_result = self.availability_service.save_week_bits(
            instructor_id=instructor_id,
            week_start=week_start,
            windows_by_day=windows_by_day,
            base_version=None,
            override=True,
            clear_existing=False,
        )

        day_bits = save_result.bits_by_day.get(date)
        saved_slots = [
            {"start_time": start, "end_time": end}
            for start, end in windows_from_bits(day_bits) if day_bits is not None
        ]

        return {"success": True, "date": date.isoformat(), "slots": saved_slots}

    def get_day_availability(self, instructor_id: int, date: date) -> Dict[str, Any]:
        """
        Get availability for a specific day.

        Returns a dict with date and slots.
        """
        # Get the week that contains this date
        week_start = date - timedelta(days=date.weekday())
        week_data = self.availability_service.get_week_availability(
            instructor_id=instructor_id,
            start_date=week_start,
            include_empty=True,
        )

        # Extract just the requested day
        date_str = date.isoformat()
        slots = week_data.get(date_str, [])

        return {"date": date_str, "slots": slots}

    def get_week_availability(self, instructor_id: int, week_start: date) -> Dict[str, Any]:
        """
        Get availability for a week.

        Returns week data in a format that tests expect.
        """
        week_data = self.availability_service.get_week_availability(
            instructor_id=instructor_id,
            start_date=week_start,
            include_empty=True,
        )

        # Convert to test-friendly format
        days = []
        for i in range(7):
            day_date = week_start + timedelta(days=i)
            day_str = day_date.isoformat()
            days.append({"date": day_str, "slots": week_data.get(day_str, [])})

        return {"week_start": week_start.isoformat(), "days": days}

    def copy_week(self, instructor_id: int, from_week_start: date, to_week_start: date) -> Dict[str, Any]:
        """
        Copy availability from one week to another.

        Synchronous wrapper around the async service method.
        """
        # Check if the method exists and is async
        if hasattr(self.week_operation_service, "copy_week_availability"):
            # Use the async method
            result = asyncio.run(
                self.week_operation_service.copy_week_availability(
                    instructor_id=instructor_id, from_week_start=from_week_start, to_week_start=to_week_start
                )
            )
        else:
            # Fallback to manual copying
            from_data = self.get_week_availability(instructor_id, from_week_start)

            slots_created = 0
            days_created = 0

            for day_data in from_data["days"]:
                if day_data["slots"]:
                    day_date = date.fromisoformat(day_data["date"])
                    # Calculate corresponding day in target week
                    day_offset = (day_date - from_week_start).days
                    target_date = to_week_start + timedelta(days=day_offset)

                    result = self.set_day_availability(
                        instructor_id=instructor_id, date=target_date, slots=day_data["slots"], clear_existing=True
                    )

                    if result.get("success"):
                        slots_created += len(result.get("slots", []))
                        days_created += 1

            result = {"success": True, "slots_created": slots_created, "days_created": days_created}

        return {
            "success": result.get("success", True),
            "slots_created": result.get("slots_created", 0),
            "days_created": result.get("days_created", 0),
            "from_week": from_week_start.isoformat(),
            "to_week": to_week_start.isoformat(),
        }

    def apply_week_pattern(
        self, instructor_id: int, from_week_start: date, start_date: date, end_date: date
    ) -> Dict[str, Any]:
        """
        Apply a week's pattern to a date range.

        Synchronous wrapper around the async service method.
        """
        if hasattr(self.week_operation_service, "apply_pattern_to_date_range"):
            result = asyncio.run(
                self.week_operation_service.apply_pattern_to_date_range(
                    instructor_id=instructor_id,
                    from_week_start=from_week_start,
                    start_date=start_date,
                    end_date=end_date,
                )
            )

            return {
                "success": bool(result),
                "total_slots_created": result.get("slots_created", 0),
                "message": result.get("message", ""),
            }
        else:
            # Fallback implementation
            return {"success": False, "total_slots_created": 0, "message": "Method not implemented"}

    def save_week_availability(
        self, instructor_id: int, week_data: Dict[str, List[Dict[str, Any]]], clear_existing: bool = True
    ) -> Dict[str, Any]:
        """
        Save availability for an entire week.

        Converts the simple dict format to the complex schema required.
        """
        # Find the Monday of the week from the dates
        dates = [date.fromisoformat(date_str) for date_str in week_data.keys()]
        if dates:
            min_date = min(dates)
            week_start = min_date - timedelta(days=min_date.weekday())
        else:
            week_start = date.today() - timedelta(days=date.today().weekday())

        # Convert to the schema format
        schedule = []
        for date_str, slots in week_data.items():
            slot_date = date.fromisoformat(date_str)
            for slot in slots:
                # Create a dict that matches what WeekSpecificScheduleCreate expects
                schedule.append(
                    {
                        "date": slot_date,
                        "start_time": self._parse_time(slot["start_time"]),
                        "end_time": self._parse_time(slot["end_time"]),
                    }
                )

        week_schedule = WeekSpecificScheduleCreate(
            week_start=week_start, clear_existing=clear_existing, schedule=schedule
        )

        # Run the async method
        result = asyncio.run(
            self.availability_service.save_week_availability(instructor_id=instructor_id, week_data=week_schedule)
        )

        return result

    def _parse_time(self, time_str: Any) -> time:
        """Parse time from string or return if already a time object."""
        if isinstance(time_str, time):
            return time_str
        if isinstance(time_str, str):
            parts = time_str.split(":")
            return time(int(parts[0]), int(parts[1]))
        raise ValueError(f"Cannot parse time from {time_str}")


# Convenience function for tests
def get_availability_helper(db: Session) -> AvailabilityTestHelper:
    """Get an instance of the availability test helper."""
    return AvailabilityTestHelper(db)
