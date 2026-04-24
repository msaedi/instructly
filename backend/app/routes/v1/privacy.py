# backend/app/routes/v1/privacy.py
"""
V1 Privacy API endpoints for GDPR compliance.

Provides user data export, deletion, and privacy management endpoints.
"""

import asyncio
from collections.abc import Callable
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ...api.dependencies.services import get_auth_service, get_notification_service
from ...auth import get_current_user as auth_get_current_user
from ...core.enums import PermissionName
from ...database import get_db
from ...dependencies.permissions import require_permission
from ...models.user import User
from ...monitoring.sentry import capture_sentry_exception
from ...ratelimit.dependency import rate_limit
from ...repositories import RepositoryFactory
from ...schemas.privacy import (
    DataExportResponse,
    PrivacyStatisticsResponse,
    RetentionPolicyResponse,
    UserDataDeletionRequest,
    UserDataDeletionResponse,
)
from ...services.audit_service import AuditService
from ...services.auth_service import AuthService
from ...services.notification_service import NotificationService
from ...services.privacy_service import PrivacyService

logger = logging.getLogger(__name__)

# V1 router - mounted at /api/v1/privacy
router = APIRouter(tags=["privacy"])


async def _invalidate_account_tokens(
    db: Session,
    current_user: User,
    actor_snapshot: dict[str, str | None],
    *,
    trigger: str,
    event: str,
    log_message: str,
) -> None:
    user_repo = RepositoryFactory.create_user_repository(db)
    invalidated = await asyncio.to_thread(
        user_repo.invalidate_all_tokens,
        current_user.id,
        trigger=trigger,
    )
    if invalidated:
        return

    token_error = RuntimeError("invalidate_all_tokens returned False")
    logger.error(
        log_message,
        extra={
            "user_id": actor_snapshot["id"],
            "error": str(token_error),
        },
    )
    capture_sentry_exception(
        event,
        token_error,
        user_id=actor_snapshot["id"],
    )


async def _invalidate_deleted_account_tokens(
    db: Session,
    current_user: User,
    actor_snapshot: dict[str, str | None],
) -> None:
    await _invalidate_account_tokens(
        db,
        current_user,
        actor_snapshot,
        trigger="account_delete",
        event="account_delete_token_invalidation_failed",
        log_message="Account delete succeeded but token invalidation failed",
    )


async def _invalidate_anonymized_account_tokens(
    db: Session,
    current_user: User,
    actor_snapshot: dict[str, str | None],
) -> None:
    await _invalidate_account_tokens(
        db,
        current_user,
        actor_snapshot,
        trigger="account_anonymize",
        event="account_anonymize_token_invalidation_failed",
        log_message="Account anonymize succeeded but token invalidation failed",
    )


async def _send_privacy_confirmation(
    actor_snapshot: dict[str, str | None],
    *,
    send_fn: Callable[..., bool],
    send_name: str,
    event: str,
    log_message: str,
) -> None:
    recipient_email = actor_snapshot["email"] or ""
    try:
        email_sent = await asyncio.to_thread(
            send_fn,
            to_email=recipient_email,
            first_name=actor_snapshot["first_name"],
        )
        if not email_sent:
            raise RuntimeError(f"{send_name} returned False")
    except Exception as exc:
        logger.error(
            log_message,
            extra={
                "user_id": actor_snapshot["id"],
                "error": str(exc),
            },
            exc_info=True,
        )
        capture_sentry_exception(
            event,
            exc,
            user_id=actor_snapshot["id"],
        )


async def _send_deleted_confirmation(
    notification_service: NotificationService,
    actor_snapshot: dict[str, str | None],
) -> None:
    await _send_privacy_confirmation(
        actor_snapshot,
        send_fn=notification_service.send_account_deleted_confirmation,
        send_name="send_account_deleted_confirmation",
        event="account_delete_confirmation_email_failed",
        log_message="Account delete succeeded but confirmation email failed",
    )


async def _send_anonymized_confirmation(
    notification_service: NotificationService,
    actor_snapshot: dict[str, str | None],
) -> None:
    await _send_privacy_confirmation(
        actor_snapshot,
        send_fn=notification_service.send_account_anonymized_confirmation,
        send_name="send_account_anonymized_confirmation",
        event="account_anonymize_confirmation_email_failed",
        log_message="Account anonymize succeeded but confirmation email failed",
    )


def _log_privacy_action_audit(
    db: Session,
    http_request: Request,
    current_user: User,
    actor_snapshot: dict[str, str | None],
    *,
    audit_action: str,
    delete_account: bool,
) -> None:
    description = "User deleted account" if delete_account else "User anonymized account data"
    try:
        AuditService(db).log(
            action=audit_action,
            resource_type="user",
            resource_id=current_user.id,
            actor_id=actor_snapshot["id"],
            actor_email=actor_snapshot["email"],
            actor_type="user",
            description=description,
            metadata={
                "delete_account": delete_account,
                "actor_first_name": actor_snapshot["first_name"],
            },
            request=http_request,
        )
    except Exception as audit_error:
        action = "delete" if delete_account else "anonymize"
        logger.warning("Audit log write failed for user %s", action, exc_info=True)
        capture_sentry_exception(
            "account_delete_audit_failed" if delete_account else "account_anonymize_audit_failed",
            audit_error,
            user_id=actor_snapshot["id"],
        )


async def _delete_current_account(
    privacy_service: PrivacyService,
    notification_service: NotificationService,
    db: Session,
    http_request: Request,
    current_user: User,
    actor_snapshot: dict[str, str | None],
) -> UserDataDeletionResponse:
    deletion_stats = await asyncio.to_thread(
        privacy_service.delete_user_data, current_user.id, delete_account=True
    )
    # Order: capture pre-delete values -> delete -> invalidate sessions
    # -> send email -> audit. Token invalidation is security-critical and must
    # happen before blocking email I/O. Confirmation email failures after a
    # successful delete are captured with the user id for manual follow-up.
    await _invalidate_deleted_account_tokens(db, current_user, actor_snapshot)
    await _send_deleted_confirmation(notification_service, actor_snapshot)
    _log_privacy_action_audit(
        db,
        http_request,
        current_user,
        actor_snapshot,
        audit_action="user.delete",
        delete_account=True,
    )
    return UserDataDeletionResponse(
        status="success",
        message="Account and all associated data deleted",
        deletion_stats=deletion_stats,
        account_deleted=True,
    )


async def _anonymize_current_account(
    privacy_service: PrivacyService,
    notification_service: NotificationService,
    db: Session,
    http_request: Request,
    current_user: User,
    actor_snapshot: dict[str, str | None],
) -> UserDataDeletionResponse:
    await asyncio.to_thread(privacy_service.anonymize_user, current_user.id)
    await _invalidate_anonymized_account_tokens(db, current_user, actor_snapshot)
    await _send_anonymized_confirmation(notification_service, actor_snapshot)
    _log_privacy_action_audit(
        db,
        http_request,
        current_user,
        actor_snapshot,
        audit_action="user.anonymize",
        delete_account=False,
    )
    return UserDataDeletionResponse(
        status="success",
        message="Personal data anonymized",
        deletion_stats={},
        account_deleted=False,
    )


async def get_current_user(
    current_user_email: str = Depends(auth_get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    """
    Get the current authenticated user as a User object.

    Args:
        current_user_email: Email from JWT token
        auth_service: Auth service for user lookup

    Returns:
        User: The authenticated user object

    Raises:
        HTTPException: If user not found
    """
    user = await asyncio.to_thread(auth_service.get_user_by_email, current_user_email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("/export/me", response_model=DataExportResponse)
async def export_my_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DataExportResponse:
    """
    Export all data for the current user (GDPR data portability).

    Returns all personal data in a structured format.
    """
    privacy_service = PrivacyService(db)

    try:
        user_data = await asyncio.to_thread(privacy_service.export_user_data, current_user.id)
        return DataExportResponse(
            status="success",
            message="Data export completed successfully",
            data=user_data,
        )
    except Exception as e:
        logger.error("Error exporting user data: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export user data",
        )


@router.post(
    "/delete/me",
    response_model=UserDataDeletionResponse,
    dependencies=[Depends(rate_limit("write"))],
)
async def delete_my_data(
    request: UserDataDeletionRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notification_service: NotificationService = Depends(get_notification_service),
) -> UserDataDeletionResponse:
    """
    Delete user data (GDPR right to be forgotten).

    Can either anonymize data or completely delete the account.
    """
    privacy_service = PrivacyService(db)

    try:
        actor_snapshot = {
            "id": current_user.id,
            "email": current_user.email,
            "first_name": current_user.first_name,
        }

        if request.delete_account:
            return await _delete_current_account(
                privacy_service,
                notification_service,
                db,
                http_request,
                current_user,
                actor_snapshot,
            )
        return await _anonymize_current_account(
            privacy_service,
            notification_service,
            db,
            http_request,
            current_user,
            actor_snapshot,
        )

    except ValueError as e:
        # Business rule violations (e.g., has active bookings)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error deleting user data: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user data",
        )


@router.get("/statistics", response_model=PrivacyStatisticsResponse)
async def get_privacy_statistics(
    current_user: User = Depends(require_permission(PermissionName.ACCESS_MONITORING)),
    db: Session = Depends(get_db),
) -> PrivacyStatisticsResponse:
    """
    Get privacy and data retention statistics (admin only).

    Shows counts of data eligible for retention policies.
    """
    privacy_service = PrivacyService(db)

    try:
        stats = await asyncio.to_thread(privacy_service.get_privacy_statistics)
        return PrivacyStatisticsResponse(
            status="success",
            statistics=stats,
        )
    except Exception as e:
        logger.error("Error getting privacy statistics: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get privacy statistics",
        )


@router.post("/retention/apply", response_model=RetentionPolicyResponse)
async def apply_retention_policies(
    current_user: User = Depends(require_permission(PermissionName.MANAGE_USERS)),
    db: Session = Depends(get_db),
) -> RetentionPolicyResponse:
    """
    Manually trigger data retention policies (admin only).

    This is usually run automatically via scheduled tasks.
    """
    privacy_service = PrivacyService(db)

    try:
        retention_stats = await asyncio.to_thread(privacy_service.apply_retention_policies)
        return RetentionPolicyResponse(
            status="success",
            message="Retention policies applied",
            stats=retention_stats,
        )
    except Exception as e:
        logger.error("Error applying retention policies: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to apply retention policies",
        )


@router.get("/export/user/{user_id}", response_model=DataExportResponse)
async def export_user_data_admin(
    user_id: str,
    current_user: User = Depends(require_permission(PermissionName.MANAGE_USERS)),
    db: Session = Depends(get_db),
) -> DataExportResponse:
    """
    Export data for any user (admin only).

    For handling data requests on behalf of users.
    """
    privacy_service = PrivacyService(db)

    try:
        user_data = await asyncio.to_thread(privacy_service.export_user_data, user_id)
        return DataExportResponse(
            status="success",
            message=f"Data export completed for user {user_id}",
            data=user_data,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Error exporting user data: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export user data",
        )


@router.post(
    "/delete/user/{user_id}",
    response_model=UserDataDeletionResponse,
    dependencies=[Depends(rate_limit("write"))],
)
async def delete_user_data_admin(
    user_id: str,
    request: UserDataDeletionRequest,
    http_request: Request,
    current_user: User = Depends(require_permission(PermissionName.MANAGE_USERS)),
    db: Session = Depends(get_db),
) -> UserDataDeletionResponse:
    """
    Delete data for any user (admin only).

    For handling deletion requests on behalf of users.
    Note: Unlike self-service delete (/delete/me), this admin-initiated path
    does NOT send a confirmation email to the target user. Admin deletions
    are communicated out-of-band (support ticket, ban notification, etc.);
    an unsolicited "your account has been deleted" email would be surprising
    UX in abuse/moderation scenarios.
    """
    privacy_service = PrivacyService(db)

    try:
        deletion_stats = await asyncio.to_thread(
            privacy_service.delete_user_data, user_id, delete_account=request.delete_account
        )
        user_repo = RepositoryFactory.create_user_repository(db)
        invalidated = await asyncio.to_thread(
            user_repo.invalidate_all_tokens,
            user_id,
            trigger="admin_account_delete",
        )
        if not invalidated:
            token_error = RuntimeError("invalidate_all_tokens returned False")
            logger.error(
                "Admin account delete succeeded but target token invalidation failed",
                extra={
                    "user_id": current_user.id,
                    "target_user_id": user_id,
                    "error": str(token_error),
                },
            )
            # Admin deletion is an out-of-band moderation/abuse action. If token
            # invalidation fails after the delete commits, capture to Sentry with
            # actor and target context and continue with 200. Raising here would
            # leave the admin UI unclear even though deletion itself succeeded.
            # Admin tooling monitors account_delete_admin_token_invalidation_failed
            # events and triggers manual remediation via /logout-all-devices.
            capture_sentry_exception(
                "account_delete_admin_token_invalidation_failed",
                token_error,
                user_id=current_user.id,
                target_user_id=user_id,
            )
        try:
            # Keep admin deletes aggregated under user.delete; initiated_by metadata
            # distinguishes moderation/support actions from self-service deletes.
            AuditService(db).log(
                action="user.delete",
                resource_type="user",
                resource_id=user_id,
                actor=current_user,
                actor_type="user",
                description="Admin deleted user data",
                metadata={"delete_account": request.delete_account, "initiated_by": "admin"},
                request=http_request,
            )
        except Exception as audit_error:
            logger.warning("Audit log write failed for admin user delete", exc_info=True)
            capture_sentry_exception(
                "account_delete_admin_audit_failed",
                audit_error,
                user_id=current_user.id,
                target_user_id=user_id,
            )
        return UserDataDeletionResponse(
            status="success",
            message=f"Data deleted for user {user_id}",
            deletion_stats=deletion_stats,
            account_deleted=request.delete_account,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Error deleting user data: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user data",
        )
