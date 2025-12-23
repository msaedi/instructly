# backend/app/services/bulk_operation_service.py
"""
Bulk Operation Service for InstaInstru Platform

Handles bulk availability operations including:
- Multiple slot operations in a single transaction
- Validation of bulk changes
- Batch processing with rollback capability
- Week validation and preview

All operations work with bitmap storage in availability_days table.
"""

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import logging
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Set, Tuple, TypedDict, cast

from sqlalchemy.orm import Session

from ..core.exceptions import BusinessRuleException
from ..core.timezone_utils import get_user_today_by_id
from ..repositories.factory import RepositoryFactory
from ..schemas.availability_window import (
    BulkUpdateRequest,
    OperationResult,
    SlotOperation,
    ValidateWeekRequest,
    ValidationSlotDetail,
    ValidationSummary,
)
from .availability_service import AvailabilityService
from .base import BaseService
from .conflict_checker import ConflictChecker
from .search.cache_invalidation import invalidate_on_availability_change

# SlotManager removed - bitmap-only storage now

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

    Provides transactional bulk updates with validation
    and rollback capabilities.
    """

    def __init__(
        self,
        db: Session,
        slot_manager: Optional[Any] = None,  # DEPRECATED: Not used, kept for compatibility
        conflict_checker: Optional[ConflictChecker] = None,
        cache_service: Optional["CacheServiceSyncAdapter"] = None,
        repository: Optional["BulkOperationRepository"] = None,
        availability_service: Optional[AvailabilityService] = None,
    ):
        """Initialize bulk operation service."""
        super().__init__(db, cache=cache_service)
        self.logger = logging.getLogger(__name__)
        # slot_manager removed - bitmap-only storage now
        self.conflict_checker = conflict_checker or ConflictChecker(db)
        self.cache_service = cache_service
        self.repository = repository or RepositoryFactory.create_bulk_operation_repository(db)
        self.availability_repository = RepositoryFactory.create_availability_repository(db)
        self.week_operation_repository = RepositoryFactory.create_week_operation_repository(db)
        self.availability_service = availability_service or AvailabilityService(db=db)
        self.slot_manager = slot_manager

    @BaseService.measure_operation("bulk_update")
    def process_bulk_update(
        self, instructor_id: str, update_data: BulkUpdateRequest
    ) -> Dict[str, Any]:
        """
        Process bulk update operations.

        Routes to validation or execution based on mode.

        Args:
            instructor_id: The instructor ID
            update_data: Bulk update request data

        Returns:
            Summary of operations with results
        """
        self.log_operation(
            "process_bulk_update",
            instructor_id=instructor_id,
            operations_count=len(update_data.operations),
            validate_only=update_data.validate_only,
        )

        if update_data.validate_only:
            return self._validate_bulk_operations(instructor_id, update_data)
        else:
            return self._execute_bulk_operations(instructor_id, update_data)

    @BaseService.measure_operation("validate_bulk_operations")
    def _validate_bulk_operations(
        self,
        instructor_id: str,
        update_data: BulkUpdateRequest,
    ) -> Dict[str, Any]:
        """
        Validate operations without persisting (always rollback).

        Args:
            instructor_id: The instructor ID
            update_data: Bulk update request with operations

        Returns:
            Summary of validation results
        """
        with self.transaction():
            # Process operations in validation mode
            results, successful, failed = self._process_operations(
                instructor_id=instructor_id,
                operations=update_data.operations,
                validate_only=True,
            )

            # Always rollback for validation
            # repo-pattern-ignore: Rollback on error belongs in service layer for transaction control
            self.db.rollback()
            self.logger.info("Validation mode - rolling back all changes")

        # No cache invalidation for validation
        # But we can still show what would be affected
        self._extract_affected_dates(update_data.operations, results)

        return self._create_operation_summary(results, successful, failed, 0)

    @BaseService.measure_operation("execute_bulk_operations")
    def _execute_bulk_operations(
        self,
        instructor_id: str,
        update_data: BulkUpdateRequest,
    ) -> Dict[str, Any]:
        """
        Execute operations with conditional commit.

        Args:
            instructor_id: The instructor ID
            update_data: Bulk update request with operations

        Returns:
            Summary of execution results
        """
        # Store results outside transaction for return
        results = None
        successful = 0
        failed = 0

        try:
            with self.transaction():
                # Process operations
                results, successful, failed = self._process_operations(
                    instructor_id=instructor_id,
                    operations=update_data.operations,
                    validate_only=False,
                )

                # Raise exception if nothing succeeded to trigger rollback
                if successful == 0:
                    raise BusinessRuleException(
                        f"No successful operations out of {len(update_data.operations)} - rolling back"
                    )
        except BusinessRuleException as e:
            # Expected case when no operations succeed
            self.logger.info(str(e))
            return self._create_operation_summary(results or [], successful, failed, 0)

        # Invalidate cache after successful commit
        if successful > 0:
            self._invalidate_affected_cache(instructor_id, update_data.operations, results)

            # Invalidate search cache (fire-and-forget via asyncio.create_task)
            invalidate_on_availability_change(instructor_id)

        return self._create_operation_summary(results, successful, failed, 0)

    @BaseService.measure_operation("process_operations")
    def _process_operations(
        self,
        instructor_id: str,
        operations: List[SlotOperation],
        validate_only: bool,
    ) -> Tuple[List[OperationResult], int, int]:
        """
        Process all operations and return results with counters.

        Args:
            instructor_id: The instructor ID
            operations: List of operations to process
            validate_only: Whether this is validation only

        Returns:
            Tuple of (results, successful_count, failed_count)
        """
        results = []
        successful = 0
        failed = 0

        for idx, operation in enumerate(operations):
            try:
                result = self._process_single_operation(
                    instructor_id=instructor_id,
                    operation=operation,
                    operation_index=idx,
                    validate_only=validate_only,
                )

                # Update counters
                if result.status == "success":
                    successful += 1
                elif result.status == "failed":
                    failed += 1

                results.append(result)

            except Exception as e:
                self.logger.error(
                    f"Error processing operation {idx} for instructor {instructor_id}: {str(e)}"
                )
                result = OperationResult(
                    operation_index=idx,
                    action=operation.action,
                    status="failed",
                    reason=f"Unexpected error in operation {idx}: {str(e)}",
                )
                results.append(result)
                failed += 1

        return results, successful, failed

    @BaseService.measure_operation("invalidate_affected_cache")
    def _invalidate_affected_cache(
        self,
        instructor_id: str,
        operations: List[SlotOperation],
        results: List[OperationResult],
    ) -> None:
        """
        Invalidate cache for all affected dates.

        Args:
            instructor_id: The instructor ID
            operations: List of operations performed
            results: Results of the operations
        """
        if not self.cache_service:
            return

        affected_dates = self._extract_affected_dates(operations, results)

        # If we had remove operations but no dates, invalidate the entire week's cache
        if len(affected_dates) == 0:
            # Check if there were any successful remove operations
            has_successful_removes = any(
                op.action == "remove" and results[idx].status == "success"
                for idx, op in enumerate(operations)
                if idx < len(results)
            )

            if has_successful_removes:
                self.cache_service.delete_pattern(f"*{instructor_id}*")
                self.logger.info(
                    f"Invalidated all cache for instructor {instructor_id} due to remove operations without specific dates"
                )
        elif affected_dates:
            self.cache_service.invalidate_instructor_availability(
                instructor_id, list(affected_dates)
            )
            self.logger.info(
                f"Invalidated cache for instructor {instructor_id}, dates: {len(affected_dates)}"
            )

    @BaseService.measure_operation("extract_affected_dates")
    def _extract_affected_dates(
        self,
        operations: List[SlotOperation],
        results: List[OperationResult],
    ) -> Set[date]:
        """
        Extract unique dates affected by successful operations.

        Args:
            operations: List of operations
            results: Results of operations

        Returns:
            Set of affected dates
        """
        affected_dates = set()

        for idx, (op, result) in enumerate(zip(operations, results)):
            # Only consider successful operations
            if result.status != "success":
                continue

            if op.action == "remove" and op.slot_id:
                # DEPRECATED: Slot-based operations removed - bitmap-only storage now
                # Cannot query slot date directly - skip this check
                # Affected dates will be determined from operation.date if present
                pass
            elif op.date:
                # Handle both string and date objects
                if isinstance(op.date, str):
                    affected_dates.add(date.fromisoformat(op.date))
                elif isinstance(op.date, date):
                    affected_dates.add(op.date)

        return affected_dates

    @BaseService.measure_operation("create_operation_summary")
    def _create_operation_summary(
        self,
        results: List[OperationResult],
        successful: int,
        failed: int,
        skipped: int,
    ) -> Dict[str, Any]:
        """
        Create summary of bulk operation results.

        Args:
            results: List of operation results
            successful: Number of successful operations
            failed: Number of failed operations
            skipped: Number of skipped operations

        Returns:
            Summary dictionary
        """
        return {
            "successful": successful,
            "failed": failed,
            "skipped": skipped,
            "results": results,
        }

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
        elif operation.action == "update":
            return self._process_update_operation(
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
                reason=f"Unknown action '{operation.action}' - valid actions are: add, remove, update",
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
            now = datetime.now().time()
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

        # DEPRECATED: slot_exists removed - bitmap-only storage now
        # Check overlap using bitmap data instead
        from app.repositories.availability_day_repository import AvailabilityDayRepository

        bitmap_repo = AvailabilityDayRepository(self.db)
        assert operation_date is not None
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

    def _create_slot_for_operation(
        self, instructor_id: str, operation: SlotOperation, validate_only: bool
    ) -> Optional[Any]:
        """Create the actual slot if not validation only."""
        if validate_only:
            return None
        start_label = "unknown"
        end_label = "unknown"
        date_label = "unknown-date"
        try:
            # Create slot directly using slot manager
            operation_date = operation.date
            start_time = operation.start_time
            end_time = operation.end_time
            if operation_date is None or start_time is None or end_time is None:
                raise ValueError("Missing date/start_time/end_time for slot operation")
            assert start_time is not None and end_time is not None
            assert operation_date is not None
            start_label = start_time.strftime("%H:%M")
            end_label = end_time.strftime("%H:%M")
            date_label = operation_date.isoformat()
            if self.slot_manager:
                return self.slot_manager.create_slot(
                    instructor_id=instructor_id,
                    target_date=operation_date,
                    start_time=start_time,
                    end_time=end_time,
                    auto_merge=True,
                )
            raise NotImplementedError("Slot manager not configured for slot creation")
        except Exception as e:
            raise Exception(
                f"Failed to create slot {start_label}-{end_label} on {date_label}: {str(e)}"
            )

    @BaseService.measure_operation("process_add_operation")
    def _process_add_operation(
        self,
        instructor_id: str,
        operation: SlotOperation,
        operation_index: int,
        validate_only: bool,
    ) -> OperationResult:
        """
        Process add slot operation.

        Creates slot directly without any conflict validation.
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

        # 4. Create slot
        if validate_only:
            return OperationResult(
                operation_index=operation_index,
                action="add",
                status="success",
                reason="Validation passed - slot can be added",
            )

        try:
            slot = self._create_slot_for_operation(instructor_id, operation, validate_only)
            if slot is None:
                raise ValueError("Slot creation returned None for add operation")
            return OperationResult(
                operation_index=operation_index,
                action="add",
                status="success",
                slot_id=slot.id,
            )
        except Exception as e:
            return OperationResult(
                operation_index=operation_index,
                action="add",
                status="failed",
                reason=str(e),
            )

    def _validate_remove_operation(
        self, instructor_id: str, operation: SlotOperation
    ) -> Tuple[Optional[Any], Optional[str]]:
        """
        Validate window exists for remove operation.

        In bitmap world, remove operations use date + time instead of slot_id.
        """
        if operation.slot_id:
            repo = cast(Any, self.repository)
            slot = repo.get_slot_for_instructor(operation.slot_id, instructor_id)
            if not slot:
                return (
                    None,
                    f"Slot {operation.slot_id} not found or not owned by instructor {instructor_id}",
                )
            return slot, None

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

    def _check_remove_operation_bookings(self, slot_id: str) -> Optional[str]:
        """Check if slot has active bookings."""
        # With layer independence, we don't check bookings
        return None

    def _execute_slot_removal(self, slot: Any, slot_id: str, validate_only: bool) -> bool:
        """Execute the removal if not validation only."""
        if validate_only:
            return True

        try:
            if self.slot_manager:
                self.slot_manager.delete_slot(getattr(slot, "id", slot_id))
                return True
            raise NotImplementedError("Slot manager not configured for slot removal")
        except Exception as e:
            raise Exception(f"Failed to remove slot {slot_id}: {str(e)}")

    @BaseService.measure_operation("process_remove_operation")
    def _process_remove_operation(
        self,
        instructor_id: str,
        operation: SlotOperation,
        operation_index: int,
        validate_only: bool,
    ) -> OperationResult:
        """
        Process remove slot operation.

        Allows removal regardless of bookings (layer independence).
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

        # In bitmap world, we use date + time as identifier
        slot_id = operation.slot_id or (
            f"{operation.date}_{operation.start_time}_{operation.end_time}"
            if operation.date
            else "unknown"
        )

        # 2. Check bookings (not needed with layer independence)
        if error := self._check_remove_operation_bookings(slot_id):
            return OperationResult(
                operation_index=operation_index,
                action="remove",
                status="failed",
                reason=error,
            )

        # 3. Execute removal
        if validate_only:
            return OperationResult(
                operation_index=operation_index,
                action="remove",
                status="success",
                reason="Validation passed - slot can be removed",
            )

        try:
            self._execute_slot_removal(slot, slot_id, validate_only)
            return OperationResult(
                operation_index=operation_index,
                action="remove",
                status="success",
                reason=f"Successfully removed slot {slot_id}",
            )
        except Exception as e:
            return OperationResult(
                operation_index=operation_index,
                action="remove",
                status="failed",
                reason=str(e),
            )

    def _validate_update_operation_fields(self, operation: SlotOperation) -> Optional[str]:
        """Validate required fields for update operation."""
        if not operation.slot_id:
            return "Missing slot_id for update operation - cannot identify which slot to update"
        return None

    def _find_slot_for_update(
        self, instructor_id: str, slot_id: str
    ) -> Tuple[Optional[Any], Optional[str]]:
        """Find the slot to update and verify ownership."""
        repo = cast(Any, self.repository)
        slot = repo.get_slot_for_instructor(slot_id, instructor_id)
        if not slot:
            return None, f"Slot {slot_id} not found or not owned by instructor {instructor_id}"
        return slot, None

    def _validate_update_timing_and_conflicts(
        self, instructor_id: str, operation: SlotOperation, existing_slot: Any
    ) -> Optional[str]:
        """Validate new times and check for conflicts."""
        # Determine new times
        new_start = operation.start_time if operation.start_time else existing_slot.start_time
        new_end = operation.end_time if operation.end_time else existing_slot.end_time

        # Validate time order
        if new_end <= new_start:
            return (
                f"End time ({new_end.strftime('%H:%M')}) must be after start time "
                f"({new_start.strftime('%H:%M')}) for slot {operation.slot_id}"
            )

        return None

    def _execute_slot_update(
        self, slot: Any, operation: SlotOperation, new_start: Any, new_end: Any, validate_only: bool
    ) -> Optional[Any]:
        """Execute the update if not validation only."""
        if validate_only:
            return None

        try:
            slot_id = cast(str, operation.slot_id)  # validated upstream
            if self.slot_manager:
                return self.slot_manager.update_slot(slot_id, new_start, new_end)
            raise NotImplementedError("Slot manager not configured for slot updates")
        except Exception as e:
            raise Exception(
                f"Failed to update slot {slot_id} to {new_start.strftime('%H:%M')}-"
                f"{new_end.strftime('%H:%M')}: {str(e)}"
            )

    @BaseService.measure_operation("process_update_operation")
    def _process_update_operation(
        self,
        instructor_id: str,
        operation: SlotOperation,
        operation_index: int,
        validate_only: bool,
    ) -> OperationResult:
        """
        Process update slot operation.

        Allows updates regardless of bookings (layer independence).
        """
        # 1. Field validation
        if error := self._validate_update_operation_fields(operation):
            return OperationResult(
                operation_index=operation_index,
                action="update",
                status="failed",
                reason=error,
            )

        # 2. Find slot
        slot_id = cast(str, operation.slot_id)

        slot, error = self._find_slot_for_update(instructor_id, slot_id)
        if error:
            return OperationResult(
                operation_index=operation_index,
                action="update",
                status="failed",
                reason=error,
            )
        if slot is None:
            return OperationResult(
                operation_index=operation_index,
                action="update",
                status="failed",
                reason=f"Slot {slot_id} could not be loaded for update",
            )

        # 3. Validate timing
        new_start = operation.start_time if operation.start_time else slot.start_time
        new_end = operation.end_time if operation.end_time else slot.end_time

        if error := self._validate_update_timing_and_conflicts(instructor_id, operation, slot):
            return OperationResult(
                operation_index=operation_index,
                action="update",
                status="failed",
                reason=error,
            )

        # 4. Execute update
        if validate_only:
            return OperationResult(
                operation_index=operation_index,
                action="update",
                status="success",
                reason="Validation passed - slot can be updated",
            )

        try:
            self._execute_slot_update(slot, operation, new_start, new_end, validate_only)
            return OperationResult(
                operation_index=operation_index,
                action="update",
                status="success",
                slot_id=slot_id,
                reason=f"Successfully updated slot {slot_id} to {new_start.strftime('%H:%M')}-{new_end.strftime('%H:%M')}",
            )
        except Exception as e:
            return OperationResult(
                operation_index=operation_index,
                action="update",
                status="failed",
                reason=str(e),
            )

    def _get_existing_week_windows(
        self, instructor_id: str, week_start: date
    ) -> Dict[str, List[WindowDict]]:
        """
        Return existing availability for the week as windows (bitmap → windows).

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
                        slot_id_value = None
                        for w in existing_db_windows:
                            if (
                                w.get("start_time") == saved_start
                                and w.get("end_time") == saved_end
                            ):
                                slot_id_value = w.get("id")
                                break
                        # In bitmap world, remove operations use date + time instead of slot_id
                        # We'll use a synthetic identifier or handle it in validation
                        operations.append(
                            SlotOperation(
                                action="remove",
                                date=check_date,
                                start_time=saved_start,
                                end_time=saved_end,
                                slot_id=slot_id_value,
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
            elif operation.action in ["remove", "update"]:
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

    @contextmanager
    def _null_transaction(self) -> Iterator[Session]:
        """Null context manager for validation-only mode."""
        yield self.db
