"""Admin bookings and payments endpoints (v1)."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_booking_service
from app.api.dependencies.auth import get_current_user, require_admin
from app.api.dependencies.database import get_db
from app.core.booking_lock import booking_lock
from app.core.enums import PermissionName
from app.core.exceptions import ServiceException
from app.dependencies.permissions import require_permission
from app.models.booking import BookingStatus
from app.models.user import User
from app.schemas.admin_bookings import (
    AdminAuditLogResponse,
    AdminBookingDetailResponse,
    AdminBookingListResponse,
    AdminBookingStatsResponse,
    AdminBookingStatusUpdateRequest,
    AdminBookingStatusUpdateResponse,
    AdminCancelBookingRequest,
    AdminCancelBookingResponse,
    AdminNoShowResolutionRequest,
    AdminNoShowResolutionResponse,
)
from app.services.admin_booking_service import AdminBookingService
from app.services.booking_service import BookingService

router = APIRouter(tags=["admin-bookings"])


@router.get(
    "/bookings",
    response_model=AdminBookingListResponse,
    dependencies=[
        Depends(require_admin),
        Depends(require_permission(PermissionName.VIEW_FINANCIALS)),
    ],
)
async def list_admin_bookings(
    search: Annotated[Optional[str], Query(max_length=100)] = None,
    status_filters: Annotated[Optional[list[str]], Query(alias="status")] = None,
    payment_filters: Annotated[Optional[list[str]], Query(alias="payment_status")] = None,
    date_from: Annotated[Optional[date], Query()] = None,
    date_to: Annotated[Optional[date], Query()] = None,
    needs_action: Annotated[Optional[bool], Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=200)] = 20,
    db: Session = Depends(get_db),
) -> AdminBookingListResponse:
    service = AdminBookingService(db)
    return await asyncio.to_thread(
        service.list_bookings,
        search=search,
        statuses=status_filters,
        payment_statuses=payment_filters,
        date_from=date_from,
        date_to=date_to,
        needs_action=needs_action,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/bookings/stats",
    response_model=AdminBookingStatsResponse,
    dependencies=[
        Depends(require_admin),
        Depends(require_permission(PermissionName.VIEW_FINANCIALS)),
    ],
)
async def get_admin_booking_stats(
    db: Session = Depends(get_db),
) -> AdminBookingStatsResponse:
    service = AdminBookingService(db)
    return await asyncio.to_thread(service.get_booking_stats)


@router.get(
    "/bookings/{booking_id}",
    response_model=AdminBookingDetailResponse,
    dependencies=[
        Depends(require_admin),
        Depends(require_permission(PermissionName.VIEW_FINANCIALS)),
    ],
)
async def get_admin_booking_detail(
    booking_id: str,
    db: Session = Depends(get_db),
) -> AdminBookingDetailResponse:
    service = AdminBookingService(db)
    detail = await asyncio.to_thread(service.get_booking_detail, booking_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    return detail


@router.get(
    "/audit-log",
    response_model=AdminAuditLogResponse,
    dependencies=[
        Depends(require_admin),
        Depends(require_permission(PermissionName.VIEW_FINANCIALS)),
    ],
)
async def list_admin_audit_log(
    action: Annotated[Optional[list[str]], Query()] = None,
    admin_id: Annotated[Optional[str], Query()] = None,
    date_from: Annotated[Optional[date], Query()] = None,
    date_to: Annotated[Optional[date], Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=200)] = 20,
    db: Session = Depends(get_db),
) -> AdminAuditLogResponse:
    service = AdminBookingService(db)
    return await asyncio.to_thread(
        service.list_audit_log,
        actions=action,
        admin_id=admin_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        per_page=per_page,
    )


@router.post(
    "/bookings/{booking_id}/cancel",
    response_model=AdminCancelBookingResponse,
    dependencies=[
        Depends(require_admin),
        Depends(require_permission(PermissionName.MANAGE_FINANCIALS)),
    ],
)
async def admin_cancel_booking(
    booking_id: str,
    request: AdminCancelBookingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AdminCancelBookingResponse:
    service = AdminBookingService(db)
    try:
        async with booking_lock(booking_id) as acquired:
            if not acquired:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Operation in progress",
                )
            booking, refund_id = await asyncio.to_thread(
                service.cancel_booking,
                booking_id=booking_id,
                reason=request.reason,
                note=request.note,
                refund=request.refund,
                actor=current_user,
            )
    except ServiceException as exc:
        if exc.code == "stripe_error":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    return AdminCancelBookingResponse(
        success=True,
        booking_id=booking.id,
        booking_status=booking.status.value
        if hasattr(booking.status, "value")
        else str(booking.status),
        refund_issued=bool(request.refund),
        refund_id=refund_id,
    )


@router.post(
    "/bookings/{booking_id}/complete",
    response_model=AdminBookingStatusUpdateResponse,
    dependencies=[
        Depends(require_admin),
        Depends(require_permission(PermissionName.MANAGE_FINANCIALS)),
    ],
)
async def admin_update_booking_status(
    booking_id: str,
    request: AdminBookingStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AdminBookingStatusUpdateResponse:
    service = AdminBookingService(db)
    try:
        booking = await asyncio.to_thread(
            service.update_booking_status,
            booking_id=booking_id,
            status=BookingStatus(request.status.value),
            note=request.note,
            actor=current_user,
        )
    except ServiceException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    return AdminBookingStatusUpdateResponse(
        success=True,
        booking_id=booking.id,
        booking_status=booking.status.value
        if hasattr(booking.status, "value")
        else str(booking.status),
    )


@router.post(
    "/bookings/{booking_id}/no-show/resolve",
    response_model=AdminNoShowResolutionResponse,
    dependencies=[
        Depends(require_admin),
        Depends(require_permission(PermissionName.MANAGE_FINANCIALS)),
    ],
)
async def resolve_no_show(
    booking_id: str,
    request: AdminNoShowResolutionRequest,
    booking_service: BookingService = Depends(get_booking_service),
    current_user: User = Depends(get_current_user),
) -> AdminNoShowResolutionResponse:
    """Resolve a disputed no-show report."""
    try:
        async with booking_lock(booking_id) as acquired:
            if not acquired:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Operation in progress",
                )
            result = await asyncio.to_thread(
                booking_service.resolve_no_show,
                booking_id=booking_id,
                resolution=request.resolution.value,
                resolved_by=current_user,
                admin_notes=request.admin_notes,
            )
    except ServiceException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return AdminNoShowResolutionResponse(
        success=bool(result.get("success")),
        booking_id=result.get("booking_id", booking_id),
        resolution=result.get("resolution", request.resolution.value),
        settlement_outcome=result.get("settlement_outcome"),
    )
