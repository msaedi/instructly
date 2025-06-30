# backend/app/services/bulk_operation_service.py
"""
Bulk Operation Service for InstaInstru Platform

Handles bulk availability operations including:
- Multiple slot operations in a single transaction
- Validation of bulk changes
- Batch processing with rollback capability
- Week validation and preview
"""

import logging
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..models.availability import AvailabilitySlot, InstructorAvailability
from ..models.booking import Booking, BookingStatus
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
    ):
        """Initialize bulk operation service."""
        super().__init__(db, cache=cache_service)
        self.logger = logging.getLogger(__name__)
        self.slot_manager = slot_manager or SlotManager(db)
        self.conflict_checker = conflict_checker or ConflictChecker(db)
        self.cache_service = cache_service

    async def process_bulk_update(self, instructor_id: int, update_data: BulkUpdateRequest) -> Dict[str, Any]:
        """
        Process bulk update operations.

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

        results = []
        successful = 0
        failed = 0
        skipped = 0

        # Use transaction for all operations
        with self.transaction() if not update_data.validate_only else self._null_transaction():
            for idx, operation in enumerate(update_data.operations):
                try:
                    result = await self._process_single_operation(
                        instructor_id=instructor_id,
                        operation=operation,
                        operation_index=idx,
                        validate_only=update_data.validate_only,
                    )

                    # Update counters
                    if result.status == "success":
                        successful += 1
                    elif result.status == "failed":
                        failed += 1
                    else:
                        skipped += 1

                    results.append(result)

                except Exception as e:
                    self.logger.error(f"Error processing operation {idx}: {str(e)}")
                    result = OperationResult(
                        operation_index=idx,
                        action=operation.action,
                        status="failed",
                        reason=str(e),
                    )
                    results.append(result)
                    failed += 1

            # Rollback if validation only or if all operations failed
            if update_data.validate_only:
                self.db.rollback()
                self.logger.info("Validation mode - rolling back all changes")
            elif successful == 0:
                self.db.rollback()
                self.logger.info("No successful operations - rolling back")

        # CRITICAL FIX: Invalidate cache after successful operations
        if successful > 0 and not update_data.validate_only:
            # Get unique dates from operations
            affected_dates = set()

            # For remove operations, we need to look up the dates from the slot IDs
            for op in update_data.operations:
                if op.action == "remove" and op.slot_id:
                    # Query the slot's date before it was deleted
                    slot = self.db.query(AvailabilitySlot).filter_by(id=op.slot_id).first()
                    if slot and slot.availability:
                        affected_dates.add(slot.availability.date)
                elif op.date:
                    # Handle both string and date objects
                    if isinstance(op.date, str):
                        affected_dates.add(date.fromisoformat(op.date))
                    elif isinstance(op.date, date):
                        affected_dates.add(op.date)

            # If we had remove operations but no dates, invalidate the entire week's cache
            if successful > 0 and len(affected_dates) == 0:
                # Get the current week's dates and invalidate all of them
                # This is a broader invalidation but ensures consistency
                if self.cache_service:
                    self.cache_service.delete_pattern(f"*{instructor_id}*")
                    self.logger.info(f"Invalidated all cache for instructor {instructor_id} due to remove operations")
            elif affected_dates and self.cache_service:
                self.cache_service.invalidate_instructor_availability(instructor_id, list(affected_dates))
                self.logger.info(f"Invalidated cache for instructor {instructor_id}, dates: {len(affected_dates)}")

        return {
            "successful": successful,
            "failed": failed,
            "skipped": skipped,
            "results": results,
        }

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
            "summary": summary.dict(),
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
                reason=f"Unknown action: {operation.action}",
            )

    async def _process_add_operation(
        self,
        instructor_id: int,
        operation: SlotOperation,
        operation_index: int,
        validate_only: bool,
    ) -> OperationResult:
        """Process add slot operation."""
        # Validate required fields
        if not all([operation.date, operation.start_time, operation.end_time]):
            return OperationResult(
                operation_index=operation_index,
                action="add",
                status="failed",
                reason="Missing required fields for add operation",
            )

        # Check for past dates
        if operation.date < date.today():
            return OperationResult(
                operation_index=operation_index,
                action="add",
                status="failed",
                reason="Cannot add availability for past dates",
            )

        # Check if it's today and time has passed
        if operation.date == date.today():
            now = datetime.now().time()
            if operation.end_time <= now:
                return OperationResult(
                    operation_index=operation_index,
                    action="add",
                    status="failed",
                    reason="Cannot add availability for past time slots",
                )

        # Check for booking conflicts
        conflicts = self.conflict_checker.check_booking_conflicts(
            instructor_id, operation.date, operation.start_time, operation.end_time
        )

        if conflicts:
            return OperationResult(
                operation_index=operation_index,
                action="add",
                status="failed",
                reason=f"Conflicts with {len(conflicts)} existing bookings",
                conflicts=conflicts,
            )

        if validate_only:
            return OperationResult(
                operation_index=operation_index,
                action="add",
                status="success",
                reason="Validation passed - slot can be added",
            )

        # Actually add the slot
        try:
            # Get or create availability entry
            availability = (
                self.db.query(InstructorAvailability)
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date == operation.date,
                )
                .first()
            )

            if not availability:
                availability = InstructorAvailability(
                    instructor_id=instructor_id, date=operation.date, is_cleared=False
                )
                self.db.add(availability)
                self.db.flush()
            else:
                availability.is_cleared = False

            # Create slot
            new_slot = self.slot_manager.create_slot(
                availability_id=availability.id,
                start_time=operation.start_time,
                end_time=operation.end_time,
                validate_conflicts=False,  # Already validated
                auto_merge=not self._has_bookings_on_date(availability),
            )

            return OperationResult(
                operation_index=operation_index,
                action="add",
                status="success",
                slot_id=new_slot.id,
            )

        except Exception as e:
            return OperationResult(
                operation_index=operation_index,
                action="add",
                status="failed",
                reason=str(e),
            )

    async def _process_remove_operation(
        self,
        instructor_id: int,
        operation: SlotOperation,
        operation_index: int,
        validate_only: bool,
    ) -> OperationResult:
        """Process remove slot operation."""
        if not operation.slot_id:
            return OperationResult(
                operation_index=operation_index,
                action="remove",
                status="failed",
                reason="Missing slot_id for remove operation",
            )

        # Find the slot
        slot = (
            self.db.query(AvailabilitySlot)
            .join(InstructorAvailability)
            .filter(
                AvailabilitySlot.id == operation.slot_id,
                InstructorAvailability.instructor_id == instructor_id,
            )
            .first()
        )

        if not slot:
            return OperationResult(
                operation_index=operation_index,
                action="remove",
                status="failed",
                reason="Slot not found or not owned by instructor",
            )

        # Check if slot has bookings (FIXED: query bookings table for one-way relationship)
        booking = (
            self.db.query(Booking)
            .filter(
                Booking.availability_slot_id == slot.id,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .first()
        )

        if booking:
            return OperationResult(
                operation_index=operation_index,
                action="remove",
                status="failed",
                reason=f"Cannot remove slot with {booking.status} booking",
            )

        if validate_only:
            return OperationResult(
                operation_index=operation_index,
                action="remove",
                status="success",
                reason="Validation passed - slot can be removed",
            )

        # Actually remove the slot
        try:
            self.slot_manager.delete_slot(operation.slot_id)
            return OperationResult(operation_index=operation_index, action="remove", status="success")
        except Exception as e:
            return OperationResult(
                operation_index=operation_index,
                action="remove",
                status="failed",
                reason=str(e),
            )

    async def _process_update_operation(
        self,
        instructor_id: int,
        operation: SlotOperation,
        operation_index: int,
        validate_only: bool,
    ) -> OperationResult:
        """Process update slot operation."""
        if not operation.slot_id:
            return OperationResult(
                operation_index=operation_index,
                action="update",
                status="failed",
                reason="Missing slot_id for update operation",
            )

        # Find the slot
        slot = (
            self.db.query(AvailabilitySlot)
            .join(InstructorAvailability)
            .filter(
                AvailabilitySlot.id == operation.slot_id,
                InstructorAvailability.instructor_id == instructor_id,
            )
            .first()
        )

        if not slot:
            return OperationResult(
                operation_index=operation_index,
                action="update",
                status="failed",
                reason="Slot not found or not owned by instructor",
            )

        # Determine new times
        new_start = operation.start_time if operation.start_time else slot.start_time
        new_end = operation.end_time if operation.end_time else slot.end_time

        # Validate time order
        if new_end <= new_start:
            return OperationResult(
                operation_index=operation_index,
                action="update",
                status="failed",
                reason="End time must be after start time",
            )

        # Check conflicts
        availability = slot.availability
        conflicts = self.conflict_checker.check_booking_conflicts(
            instructor_id,
            availability.date,
            new_start,
            new_end,
            exclude_slot_id=operation.slot_id,
        )

        if conflicts:
            return OperationResult(
                operation_index=operation_index,
                action="update",
                status="failed",
                reason=f"New time range conflicts with {len(conflicts)} bookings",
            )

        if validate_only:
            return OperationResult(
                operation_index=operation_index,
                action="update",
                status="success",
                reason="Validation passed - slot can be updated",
            )

        # Actually update the slot
        try:
            updated_slot = self.slot_manager.update_slot(
                slot_id=operation.slot_id,
                start_time=new_start,
                end_time=new_end,
                validate_conflicts=False,  # Already validated
            )

            return OperationResult(
                operation_index=operation_index,
                action="update",
                status="success",
                slot_id=updated_slot.id,
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

        slots = (
            self.db.query(
                AvailabilitySlot.id,
                InstructorAvailability.date,
                AvailabilitySlot.start_time,
                AvailabilitySlot.end_time,
            )
            .join(
                InstructorAvailability,
                AvailabilitySlot.availability_id == InstructorAvailability.id,
            )
            .filter(
                InstructorAvailability.instructor_id == instructor_id,
                InstructorAvailability.date >= week_start,
                InstructorAvailability.date <= end_date,
            )
            .all()
        )

        # Organize by date
        slots_by_date = {}
        for slot in slots:
            date_str = slot.date.isoformat()
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
                    db_slot = next(
                        (
                            s
                            for s in existing_db_slots
                            if s["start_time"] == saved_slot.start_time.strftime("%H:%M:%S")
                            and s["end_time"] == saved_slot.end_time.strftime("%H:%M:%S")
                        ),
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
            warnings.append(f"{summary.invalid_operations} operations will fail due to conflicts")

        # Find dates with booking conflicts
        booked_dates = set()
        for detail in validation_results:
            if detail.conflicts_with or "bookings" in (detail.reason or ""):
                if detail.date:
                    booked_dates.add(detail.date.strftime("%A"))

        if booked_dates:
            warnings.append(f"Operations affect days with bookings: {', '.join(sorted(booked_dates))}")

        return warnings

    def _has_bookings_on_date(self, availability: InstructorAvailability) -> bool:
        """Check if any slots for this availability have bookings."""
        return (
            self.db.query(Booking)
            .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
            .filter(
                AvailabilitySlot.availability_id == availability.id,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .count()
            > 0
        )

    @contextmanager
    def _null_transaction(self):
        """Null context manager for validation-only mode."""
        yield self.db
