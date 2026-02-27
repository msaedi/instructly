# backend/app/services/bulk_operation_service.py
"""
Bulk Operation Service for InstaInstru Platform

Handles bulk availability operations including:
- Week validation and preview
- Validation of bulk changes against bitmap storage

All operations work with bitmap storage in availability_days table.
"""

from datetime import date, datetime, timedelta, timezone
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, TypedDict

from sqlalchemy.orm import Session

from ..core.timezone_utils import get_user_today_by_id
from ..repositories.factory import RepositoryFactory
from ..schemas.availability_window import (
    OperationResult,
    SlotOperation,
    ValidateWeekRequest,
    ValidationSlotDetail,
    ValidationSummary,
)
from .availability_service import AvailabilityService
from .base import BaseService
from .conflict_checker import ConflictChecker

if TYPE_CHECKING:
    from ..repositories.bulk_operation_repository import BulkOperationRepository
    from .cache_service import CacheServiceSyncAdapter

logger = logging.getLogger(__name__)


class WindowDict(TypedDict):
    """Window dictionary with start_time and end_time as strings."""

    start_time: str
    end_time: str


class BulkOperationService(BaseService):
    """
    Service for handling bulk availability operations.

    Provides week validation against bitmap-based availability storage.
    """

    def __init__(
        self,
        db: Session,
        conflict_checker: Optional[ConflictChecker] = None,
        cache_service: Optional["CacheServiceSyncAdapter"] = None,
        repository: Optional["BulkOperationRepository"] = None,
        availability_service: Optional[AvailabilityService] = None,
    ):
        """Initialize bulk operation service."""
        super().__init__(db, cache=cache_service)
        self.logger = logging.getLogger(__name__)
        self.conflict_checker = conflict_checker or ConflictChecker(db)
        self.cache_service = cache_service
        self.repository = repository or RepositoryFactory.create_bulk_operation_repository(db)
        self.availability_repository = RepositoryFactory.create_availability_repository(db)
        self.week_operation_repository = RepositoryFactory.create_week_operation_repository(db)
        self.availability_service = availability_service or AvailabilityService(db=db)

    @BaseService.measure_operation("validate_week")
    def validate_week_changes(
        self, instructor_id: str, validation_data: ValidateWeekRequest
    ) -> Dict[str, Any]:
        """
        Validate planned changes to week availability.

        Args:
            instructor_id: The instructor ID
            validation_data: Current and saved week states

        Returns:
            Comprehensive validation results
        """
        self.log_operation(
            "validate_week_changes",
            instructor_id=instructor_id,
            week_start=validation_data.week_start,
        )

        # Get actual current state from database (bitmap-based)
        existing_windows = self._get_existing_week_windows(
            instructor_id, validation_data.week_start
        )

        # Generate operations
        operations = self._generate_operations_from_states(
            existing_windows=existing_windows,
            current_week=validation_data.current_week,
            saved_week=validation_data.saved_week,
            week_start=validation_data.week_start,
        )

        # Validate each operation
        validation_results = self._validate_operations(
            instructor_id=instructor_id, operations=operations
        )

        # Generate summary
        summary = self._generate_validation_summary(validation_results)

        # Generate warnings
        warnings = self._generate_validation_warnings(validation_results, summary)

        return {
            "valid": summary.invalid_operations == 0,
            "summary": summary.model_dump(),
            "details": validation_results,
            "warnings": warnings,
        }

    # Private helper methods

    def _process_single_operation(
        self,
        instructor_id: str,
        operation: SlotOperation,
        operation_index: int,
        validate_only: bool,
    ) -> OperationResult:
        """Process a single operation."""
        if operation.action == "add":
            return self._process_add_operation(
                instructor_id=instructor_id,
                operation=operation,
                operation_index=operation_index,
                validate_only=validate_only,
            )
        elif operation.action == "remove":
            return self._process_remove_operation(
                instructor_id=instructor_id,
                operation=operation,
                operation_index=operation_index,
                validate_only=validate_only,
            )
        else:
            return OperationResult(
                operation_index=operation_index,
                action=operation.action,
                status="failed",
                reason=f"Unknown action '{operation.action}' - valid actions are: add, remove",
            )

    def _validate_add_operation_fields(self, operation: SlotOperation) -> Optional[str]:
        """Validate required fields for add operation."""
        if not all([operation.date, operation.start_time, operation.end_time]):
            missing_fields = []
            if not operation.date:
                missing_fields.append("date")
            if not operation.start_time:
                missing_fields.append("start_time")
            if not operation.end_time:
                missing_fields.append("end_time")

            return f"Missing required fields for add operation: {', '.join(missing_fields)}"
        return None

    def _validate_add_operation_timing(
        self, operation: SlotOperation, instructor_id: str
    ) -> Optional[str]:
        """Validate time constraints and alignment."""
        # Check for past dates using instructor's timezone
        try:
            instructor_today = get_user_today_by_id(instructor_id, self.db)
        except Exception:
            instructor_today = datetime.now(timezone.utc).date()
        operation_date = operation.date
        start_time = operation.start_time
        end_time = operation.end_time

        if operation_date is None:
            return "Missing date for add operation"
        if start_time is None or end_time is None:
            return "Missing start_time or end_time for add operation"

        if operation_date < instructor_today:
            return (
                f"Cannot add availability for past date {operation_date.isoformat()} "
                f"(today is {instructor_today.isoformat()} in your timezone)"
            )

        # Check if it's today and time has passed
        if operation_date == instructor_today:
            now = datetime.now(timezone.utc).time()
            if end_time <= now:
                return (
                    f"Cannot add availability for past time slot {start_time.strftime('%H:%M')}-"
                    f"{end_time.strftime('%H:%M')} (current time is {now.strftime('%H:%M')})"
                )

        return None

    def _check_add_operation_conflicts(
        self, instructor_id: str, operation: SlotOperation
    ) -> Optional[str]:
        """Check for booking conflicts and blackout dates."""
        operation_date = operation.date
        start_time = operation.start_time
        end_time = operation.end_time
        if operation_date is None or start_time is None or end_time is None:
            return "Missing date/start_time/end_time for add operation"

        from app.repositories.availability_day_repository import AvailabilityDayRepository

        bitmap_repo = AvailabilityDayRepository(self.db)
        existing_bits = bitmap_repo.get_day_bits(instructor_id, operation_date)
        if existing_bits and isinstance(existing_bits, (bytes, bytearray)):
            from app.utils.bitset import windows_from_bits

            existing_windows = windows_from_bits(existing_bits)
            new_window_str = (start_time.strftime("%H:%M:%S"), end_time.strftime("%H:%M:%S"))
            if new_window_str in existing_windows:
                return (
                    f"Time slot {start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')} "
                    f"already exists on {operation_date.isoformat()}"
                )
        return None

    @BaseService.measure_operation("process_add_operation")
    def _process_add_operation(
        self,
        instructor_id: str,
        operation: SlotOperation,
        operation_index: int,
        validate_only: bool,
    ) -> OperationResult:
        """
        Process add operation (validation only -- bitmap writes happen via availability service).
        """
        # 1. Field validation
        if error := self._validate_add_operation_fields(operation):
            return OperationResult(
                operation_index=operation_index,
                action="add",
                status="failed",
                reason=error,
            )

        # 2. Time validation
        if error := self._validate_add_operation_timing(operation, instructor_id):
            return OperationResult(
                operation_index=operation_index,
                action="add",
                status="failed",
                reason=error,
            )

        # 3. Conflict checking
        if error := self._check_add_operation_conflicts(instructor_id, operation):
            return OperationResult(
                operation_index=operation_index,
                action="add",
                status="failed",
                reason=error,
            )

        return OperationResult(
            operation_index=operation_index,
            action="add",
            status="success",
            reason="Validation passed - slot can be added",
        )

    def _validate_remove_operation(
        self, instructor_id: str, operation: SlotOperation
    ) -> Tuple[Optional[Any], Optional[str]]:
        """
        Validate window exists for remove operation.

        In bitmap world, remove operations use date + time instead of slot_id.
        """
        if not operation.date or not operation.start_time or not operation.end_time:
            return (
                None,
                "Missing date, start_time, or end_time for remove operation - cannot identify which window to remove",
            )

        # Check if window exists in database using bitmap
        operation_date = operation.date
        start_time = operation.start_time if hasattr(operation.start_time, "hour") else None
        end_time = operation.end_time if hasattr(operation.end_time, "hour") else None

        if not start_time or not end_time:
            # Handle string times
            from datetime import datetime

            if isinstance(operation.start_time, str):
                start_time = datetime.strptime(operation.start_time, "%H:%M:%S").time()
            if isinstance(operation.end_time, str):
                end_time = datetime.strptime(operation.end_time, "%H:%M:%S").time()

        # Guard against None before .strftime()
        if start_time is None or end_time is None:
            return None, "Invalid window time - start_time or end_time is None"

        # Get week start for the operation date
        week_start = operation_date - timedelta(days=operation_date.weekday())
        existing_windows = self._get_existing_week_windows(instructor_id, week_start)

        date_str = operation_date.isoformat()
        day_windows = existing_windows.get(date_str, [])

        start_str = start_time.strftime("%H:%M:%S")
        end_str = end_time.strftime("%H:%M:%S")

        window_exists = any(
            w.get("start_time") == start_str and w.get("end_time") == end_str for w in day_windows
        )

        if not window_exists:
            return (
                None,
                f"Window {start_str}-{end_str} on {date_str} not found for instructor {instructor_id}",
            )

        # Return a placeholder object to indicate validation passed
        return {"date": operation_date, "start_time": start_time, "end_time": end_time}, None

    @BaseService.measure_operation("process_remove_operation")
    def _process_remove_operation(
        self,
        instructor_id: str,
        operation: SlotOperation,
        operation_index: int,
        validate_only: bool,
    ) -> OperationResult:
        """
        Process remove operation (validation only -- bitmap writes happen via availability service).
        """
        # 1. Validate operation
        slot, error = self._validate_remove_operation(instructor_id, operation)
        if error:
            return OperationResult(
                operation_index=operation_index,
                action="remove",
                status="failed",
                reason=error,
            )

        return OperationResult(
            operation_index=operation_index,
            action="remove",
            status="success",
            reason="Validation passed - slot can be removed",
        )

    def _get_existing_week_windows(
        self, instructor_id: str, week_start: date
    ) -> Dict[str, List[WindowDict]]:
        """
        Return existing availability for the week as windows (bitmap -> windows).

        Returns:
            Dict mapping date strings to lists of window dicts with start_time/end_time.
            Example: {"YYYY-MM-DD": [{"start_time":"09:00:00","end_time":"10:00:00"}, ...], ...}
        """
        # Use AvailabilityService to get week availability (bitmap-based)
        week_map = self.availability_service.get_week_availability(
            instructor_id, week_start, use_cache=False
        )

        # Convert to the format expected by _generate_operations_from_states
        # week_map is already in the right format: {date_str: [{"start_time": "...", "end_time": "..."}, ...]}
        # The values from get_week_availability are already dicts with start_time/end_time keys
        # Convert them to WindowDict TypedDict for type safety
        result: Dict[str, List[WindowDict]] = {}
        for date_str, windows in week_map.items():
            result[date_str] = [
                WindowDict(start_time=str(w["start_time"]), end_time=str(w["end_time"]))
                for w in windows
            ]
        return result

    def _generate_operations_from_states(
        self,
        existing_windows: Optional[Dict[str, List[WindowDict]]] = None,
        current_week: Optional[Dict[str, List[Any]]] = None,
        saved_week: Optional[Dict[str, List[Any]]] = None,
        week_start: Optional[date] = None,
        *,
        existing_slots: Optional[Dict[str, List[WindowDict]]] = None,
    ) -> List[SlotOperation]:
        """
        Generate operations by comparing states.

        Note: In bitmap world, we don't have slot IDs, so remove operations
        are identified by date + time window. The validation will check if
        the window exists in the database.
        """
        if existing_windows is None and existing_slots is not None:
            existing_windows = existing_slots
        if existing_windows is None:
            existing_windows = {}
        if current_week is None:
            current_week = {}
        if saved_week is None:
            saved_week = {}
        if week_start is None:
            raise ValueError("week_start is required to generate operations")
        operations = []

        # Process each day
        for day_offset in range(7):
            check_date = week_start + timedelta(days=day_offset)
            date_str = check_date.isoformat()

            current_slots = current_week.get(date_str, [])
            saved_slots = saved_week.get(date_str, [])
            existing_db_windows = existing_windows.get(date_str, [])

            # Find windows to remove (saved but not in current)
            for saved_slot in saved_slots:
                still_exists = any(
                    s.start_time == saved_slot.start_time and s.end_time == saved_slot.end_time
                    for s in current_slots
                )

                if not still_exists:
                    # In bitmap world, we identify windows by date + time, not ID
                    # Check if this window exists in the database
                    saved_start = saved_slot.start_time
                    saved_end = saved_slot.end_time

                    # Convert to string if it's a time object
                    if hasattr(saved_start, "strftime"):
                        saved_start = saved_start.strftime("%H:%M:%S")
                    if hasattr(saved_end, "strftime"):
                        saved_end = saved_end.strftime("%H:%M:%S")

                    # Check if window exists in database
                    window_exists = any(
                        w.get("start_time") == saved_start and w.get("end_time") == saved_end
                        for w in existing_db_windows
                    )

                    if window_exists:
                        # In bitmap world, remove operations use date + time instead of slot_id
                        operations.append(
                            SlotOperation(
                                action="remove",
                                date=check_date,
                                start_time=saved_start,
                                end_time=saved_end,
                            )
                        )

            # Find windows to add
            for current_slot in current_slots:
                is_new = not any(
                    s.start_time == current_slot.start_time and s.end_time == current_slot.end_time
                    for s in saved_slots
                )

                if is_new:
                    operations.append(
                        SlotOperation(
                            action="add",
                            date=check_date,
                            start_time=current_slot.start_time,
                            end_time=current_slot.end_time,
                        )
                    )

        return operations

    def _validate_operations(
        self, instructor_id: str, operations: List[SlotOperation]
    ) -> List[ValidationSlotDetail]:
        """Validate a list of operations."""
        validation_details = []

        for idx, operation in enumerate(operations):
            # Process operation in validation mode
            result = self._process_single_operation(
                instructor_id=instructor_id,
                operation=operation,
                operation_index=idx,
                validate_only=True,
            )

            # Convert to validation detail
            detail = ValidationSlotDetail(
                operation_index=idx,
                action=operation.action,
                reason=result.reason,
                conflicts_with=result.conflicts if hasattr(result, "conflicts") else None,
            )

            # Add operation-specific details
            if operation.action == "add":
                detail.date = operation.date
                detail.start_time = operation.start_time
                detail.end_time = operation.end_time
            elif operation.action == "remove":
                detail.slot_id = operation.slot_id

            validation_details.append(detail)

        return validation_details

    def _generate_validation_summary(
        self, validation_results: List[ValidationSlotDetail]
    ) -> ValidationSummary:
        """Generate summary from validation results."""
        operations_by_type = {"add": 0, "remove": 0, "update": 0}
        valid_count = 0
        invalid_count = 0

        for detail in validation_results:
            operations_by_type[detail.action] += 1

            if "Valid" in (detail.reason or "") or "passed" in (detail.reason or ""):
                valid_count += 1
            else:
                invalid_count += 1

        estimated_changes = {
            "slots_added": sum(
                1 for d in validation_results if d.action == "add" and "Valid" in (d.reason or "")
            ),
            "slots_removed": sum(
                1
                for d in validation_results
                if d.action == "remove" and "Valid" in (d.reason or "")
            ),
            "conflicts": invalid_count,
        }

        return ValidationSummary(
            total_operations=len(validation_results),
            valid_operations=valid_count,
            invalid_operations=invalid_count,
            operations_by_type=operations_by_type,
            has_conflicts=invalid_count > 0,
            estimated_changes=estimated_changes,
        )

    def _generate_validation_warnings(
        self, validation_results: List[ValidationSlotDetail], summary: ValidationSummary
    ) -> List[str]:
        """Generate helpful warnings from validation results."""
        warnings = []

        if summary.invalid_operations > 0:
            warnings.append(f"{summary.invalid_operations} operations will fail")

        return warnings
