# backend/app/services/bulk_operation_service.py
"""
Bulk Operation Service for InstaInstru Platform

Handles bulk availability operations including:
- Multiple slot operations in a single transaction
- Validation of bulk changes
- Batch processing with rollback capability
- Week validation and preview

All operations work directly with AvailabilitySlot objects
using instructor_id + date.
"""

import logging
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from ..core.exceptions import BusinessRuleException
from ..repositories.factory import RepositoryFactory
from ..schemas.availability_window import (
    BulkUpdateRequest,
    OperationResult,
    SlotOperation,
    ValidateWeekRequest,
    ValidationSlotDetail,
    ValidationSummary,
)
from .base import BaseService
from .conflict_checker import ConflictChecker
from .slot_manager import SlotManager

if TYPE_CHECKING:
    from ..repositories.bulk_operation_repository import BulkOperationRepository
    from .cache_service import CacheService

logger = logging.getLogger(__name__)


class BulkOperationService(BaseService):
    """
    Service for handling bulk availability operations.

    Provides transactional bulk updates with validation
    and rollback capabilities.
    """

    def __init__(
        self,
        db: Session,
        slot_manager: Optional[SlotManager] = None,
        conflict_checker: Optional[ConflictChecker] = None,
        cache_service: Optional["CacheService"] = None,
        repository: Optional["BulkOperationRepository"] = None,
    ):
        """Initialize bulk operation service."""
        super().__init__(db, cache=cache_service)
        self.logger = logging.getLogger(__name__)
        self.slot_manager = slot_manager or SlotManager(db)
        self.conflict_checker = conflict_checker or ConflictChecker(db)
        self.cache_service = cache_service
        self.repository = repository or RepositoryFactory.create_bulk_operation_repository(db)
        self.availability_repository = RepositoryFactory.create_availability_repository(db)
        self.week_operation_repository = RepositoryFactory.create_week_operation_repository(db)

    @BaseService.measure_operation("bulk_update")
    async def process_bulk_update(self, instructor_id: int, update_data: BulkUpdateRequest) -> Dict[str, Any]:
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
            return await self._validate_bulk_operations(instructor_id, update_data)
        else:
            return await self._execute_bulk_operations(instructor_id, update_data)

    @BaseService.measure_operation("validate_bulk_operations")
    async def _validate_bulk_operations(
        self,
        instructor_id: int,
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
            results, successful, failed = await self._process_operations(
                instructor_id=instructor_id,
                operations=update_data.operations,
                validate_only=True,
            )

            # Always rollback for validation
            self.db.rollback()
            self.logger.info("Validation mode - rolling back all changes")

        # No cache invalidation for validation
        # But we can still show what would be affected
        self._extract_affected_dates(update_data.operations, results)

        return self._create_operation_summary(results, successful, failed, 0)

    @BaseService.measure_operation("execute_bulk_operations")
    async def _execute_bulk_operations(
        self,
        instructor_id: int,
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
                results, successful, failed = await self._process_operations(
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
            await self._invalidate_affected_cache(instructor_id, update_data.operations, results)

        return self._create_operation_summary(results, successful, failed, 0)

    @BaseService.measure_operation("process_operations")
    async def _process_operations(
        self,
        instructor_id: int,
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
                result = await self._process_single_operation(
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
                self.logger.error(f"Error processing operation {idx} for instructor {instructor_id}: {str(e)}")
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
    async def _invalidate_affected_cache(
        self,
        instructor_id: int,
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
            self.cache_service.invalidate_instructor_availability(instructor_id, list(affected_dates))
            self.logger.info(f"Invalidated cache for instructor {instructor_id}, dates: {len(affected_dates)}")

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
                # Query the slot's date using repository
                slots_data = self.repository.get_slots_by_ids([op.slot_id])
                for slot_id, slot_date, _, _ in slots_data:
                    affected_dates.add(slot_date)
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
    async def validate_week_changes(self, instructor_id: int, validation_data: ValidateWeekRequest) -> Dict[str, Any]:
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

        # Get actual current state from database
        existing_slots = self._get_existing_week_slots(instructor_id, validation_data.week_start)

        # Generate operations
        operations = self._generate_operations_from_states(
            existing_slots=existing_slots,
            current_week=validation_data.current_week,
            saved_week=validation_data.saved_week,
            week_start=validation_data.week_start,
        )

        # Validate each operation
        validation_results = await self._validate_operations(instructor_id=instructor_id, operations=operations)

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

    async def _process_single_operation(
        self,
        instructor_id: int,
        operation: SlotOperation,
        operation_index: int,
        validate_only: bool,
    ) -> OperationResult:
        """Process a single operation."""
        if operation.action == "add":
            return await self._process_add_operation(
                instructor_id=instructor_id,
                operation=operation,
                operation_index=operation_index,
                validate_only=validate_only,
            )
        elif operation.action == "remove":
            return await self._process_remove_operation(
                instructor_id=instructor_id,
                operation=operation,
                operation_index=operation_index,
                validate_only=validate_only,
            )
        elif operation.action == "update":
            return await self._process_update_operation(
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

    def _validate_add_operation_timing(self, operation: SlotOperation) -> Optional[str]:
        """Validate time constraints and alignment."""
        # Check for past dates
        if operation.date < date.today():
            return (
                f"Cannot add availability for past date {operation.date.isoformat()} "
                f"(today is {date.today().isoformat()})"
            )

        # Check if it's today and time has passed
        if operation.date == date.today():
            now = datetime.now().time()
            if operation.end_time <= now:
                return (
                    f"Cannot add availability for past time slot {operation.start_time.strftime('%H:%M')}-"
                    f"{operation.end_time.strftime('%H:%M')} (current time is {now.strftime('%H:%M')})"
                )

        return None

    async def _check_add_operation_conflicts(self, instructor_id: int, operation: SlotOperation) -> Optional[str]:
        """Check for booking conflicts and blackout dates."""
        # Check if slot already exists
        if self.availability_repository.slot_exists(
            instructor_id, target_date=operation.date, start_time=operation.start_time, end_time=operation.end_time
        ):
            return (
                f"Time slot {operation.start_time.strftime('%H:%M')}-{operation.end_time.strftime('%H:%M')} "
                f"already exists on {operation.date.isoformat()}"
            )
        return None

    async def _create_slot_for_operation(
        self, instructor_id: int, operation: SlotOperation, validate_only: bool
    ) -> Optional[Any]:
        """Create the actual slot if not validation only."""
        if validate_only:
            return None

        try:
            # Create slot directly using slot manager
            new_slot = self.slot_manager.create_slot(
                instructor_id=instructor_id,
                target_date=operation.date,
                start_time=operation.start_time,
                end_time=operation.end_time,
                auto_merge=True,
            )
            return new_slot
        except Exception as e:
            raise Exception(
                f"Failed to create slot {operation.start_time.strftime('%H:%M')}-"
                f"{operation.end_time.strftime('%H:%M')} on {operation.date.isoformat()}: {str(e)}"
            )

    @BaseService.measure_operation("process_add_operation")
    async def _process_add_operation(
        self,
        instructor_id: int,
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
        if error := self._validate_add_operation_timing(operation):
            return OperationResult(
                operation_index=operation_index,
                action="add",
                status="failed",
                reason=error,
            )

        # 3. Conflict checking
        if error := await self._check_add_operation_conflicts(instructor_id, operation):
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
            slot = await self._create_slot_for_operation(instructor_id, operation, validate_only)
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

    async def _validate_remove_operation(self, instructor_id: int, slot_id: int) -> Tuple[Optional[Any], Optional[str]]:
        """Validate slot exists and belongs to instructor."""
        if not slot_id:
            return None, "Missing slot_id for remove operation - cannot identify which slot to remove"

        # Find the slot using repository
        slot = self.repository.get_slot_for_instructor(slot_id, instructor_id)

        if not slot:
            return None, f"Slot {slot_id} not found or not owned by instructor {instructor_id}"

        return slot, None

    async def _check_remove_operation_bookings(self, slot_id: int) -> Optional[str]:
        """Check if slot has active bookings."""
        # With layer independence, we don't check bookings
        return None

    async def _execute_slot_removal(self, slot: Any, slot_id: int, validate_only: bool) -> bool:
        """Execute the removal if not validation only."""
        if validate_only:
            return True

        try:
            self.slot_manager.delete_slot(slot_id)
            return True
        except Exception as e:
            raise Exception(f"Failed to remove slot {slot_id}: {str(e)}")

    @BaseService.measure_operation("process_remove_operation")
    async def _process_remove_operation(
        self,
        instructor_id: int,
        operation: SlotOperation,
        operation_index: int,
        validate_only: bool,
    ) -> OperationResult:
        """
        Process remove slot operation.

        Allows removal regardless of bookings (layer independence).
        """
        # 1. Validate operation
        slot, error = await self._validate_remove_operation(instructor_id, operation.slot_id)
        if error:
            return OperationResult(
                operation_index=operation_index,
                action="remove",
                status="failed",
                reason=error,
            )

        # 2. Check bookings (not needed with layer independence)
        if error := await self._check_remove_operation_bookings(operation.slot_id):
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
            await self._execute_slot_removal(slot, operation.slot_id, validate_only)
            return OperationResult(
                operation_index=operation_index,
                action="remove",
                status="success",
                reason=f"Successfully removed slot {operation.slot_id}",
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

    async def _find_slot_for_update(self, instructor_id: int, slot_id: int) -> Tuple[Optional[Any], Optional[str]]:
        """Find the slot to update and verify ownership."""
        # Find the slot using repository
        slot = self.repository.get_slot_for_instructor(slot_id, instructor_id)

        if not slot:
            return None, f"Slot {slot_id} not found or not owned by instructor {instructor_id}"

        return slot, None

    async def _validate_update_timing_and_conflicts(
        self, instructor_id: int, operation: SlotOperation, existing_slot: Any
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

    async def _execute_slot_update(
        self, slot: Any, operation: SlotOperation, new_start: Any, new_end: Any, validate_only: bool
    ) -> Optional[Any]:
        """Execute the update if not validation only."""
        if validate_only:
            return None

        try:
            updated_slot = self.slot_manager.update_slot(
                slot_id=operation.slot_id,
                start_time=new_start,
                end_time=new_end,
            )
            return updated_slot
        except Exception as e:
            raise Exception(
                f"Failed to update slot {operation.slot_id} to {new_start.strftime('%H:%M')}-"
                f"{new_end.strftime('%H:%M')}: {str(e)}"
            )

    @BaseService.measure_operation("process_update_operation")
    async def _process_update_operation(
        self,
        instructor_id: int,
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
        slot, error = await self._find_slot_for_update(instructor_id, operation.slot_id)
        if error:
            return OperationResult(
                operation_index=operation_index,
                action="update",
                status="failed",
                reason=error,
            )

        # 3. Validate timing
        new_start = operation.start_time if operation.start_time else slot.start_time
        new_end = operation.end_time if operation.end_time else slot.end_time

        if error := await self._validate_update_timing_and_conflicts(instructor_id, operation, slot):
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
            await self._execute_slot_update(slot, operation, new_start, new_end, validate_only)
            return OperationResult(
                operation_index=operation_index,
                action="update",
                status="success",
                slot_id=operation.slot_id,
                reason=f"Successfully updated slot {operation.slot_id} to {new_start.strftime('%H:%M')}-{new_end.strftime('%H:%M')}",
            )
        except Exception as e:
            return OperationResult(
                operation_index=operation_index,
                action="update",
                status="failed",
                reason=str(e),
            )

    def _get_existing_week_slots(self, instructor_id: int, week_start: date) -> Dict[str, List[Dict]]:
        """Get existing slots for a week from database."""
        end_date = week_start + timedelta(days=6)

        # Use repository to get week slots
        slots = self.week_operation_repository.get_week_slots(instructor_id, week_start, end_date)

        # Organize by date
        slots_by_date = {}
        for slot in slots:
            date_str = slot.specific_date.isoformat()
            if date_str not in slots_by_date:
                slots_by_date[date_str] = []
            slots_by_date[date_str].append(
                {
                    "id": slot.id,
                    "start_time": slot.start_time.strftime("%H:%M:%S"),
                    "end_time": slot.end_time.strftime("%H:%M:%S"),
                }
            )

        return slots_by_date

    def _generate_operations_from_states(
        self,
        existing_slots: Dict[str, List[Dict]],
        current_week: Dict[str, List[Any]],
        saved_week: Dict[str, List[Any]],
        week_start: date,
    ) -> List[SlotOperation]:
        """Generate operations by comparing states."""
        operations = []

        # Process each day
        for day_offset in range(7):
            check_date = week_start + timedelta(days=day_offset)
            date_str = check_date.isoformat()

            current_slots = current_week.get(date_str, [])
            saved_slots = saved_week.get(date_str, [])
            existing_db_slots = existing_slots.get(date_str, [])

            # Find slots to remove
            for saved_slot in saved_slots:
                still_exists = any(
                    s.start_time == saved_slot.start_time and s.end_time == saved_slot.end_time for s in current_slots
                )

                if not still_exists:
                    # Find the DB slot ID
                    # Handle both string and time object formats
                    saved_start = saved_slot.start_time
                    saved_end = saved_slot.end_time

                    # Convert to string if it's a time object
                    if hasattr(saved_start, "strftime"):
                        saved_start = saved_start.strftime("%H:%M:%S")
                    if hasattr(saved_end, "strftime"):
                        saved_end = saved_end.strftime("%H:%M:%S")

                    db_slot = next(
                        (s for s in existing_db_slots if s["start_time"] == saved_start and s["end_time"] == saved_end),
                        None,
                    )

                    if db_slot:
                        operations.append(SlotOperation(action="remove", slot_id=db_slot["id"]))

            # Find slots to add
            for current_slot in current_slots:
                is_new = not any(
                    s.start_time == current_slot.start_time and s.end_time == current_slot.end_time for s in saved_slots
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

    async def _validate_operations(
        self, instructor_id: int, operations: List[SlotOperation]
    ) -> List[ValidationSlotDetail]:
        """Validate a list of operations."""
        validation_details = []

        for idx, operation in enumerate(operations):
            # Process operation in validation mode
            result = await self._process_single_operation(
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

    def _generate_validation_summary(self, validation_results: List[ValidationSlotDetail]) -> ValidationSummary:
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
            "slots_added": sum(1 for d in validation_results if d.action == "add" and "Valid" in (d.reason or "")),
            "slots_removed": sum(1 for d in validation_results if d.action == "remove" and "Valid" in (d.reason or "")),
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
    def _null_transaction(self):
        """Null context manager for validation-only mode."""
        yield self.db
