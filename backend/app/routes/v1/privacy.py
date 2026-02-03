# backend/app/routes/v1/privacy.py
"""
V1 Privacy API endpoints for GDPR compliance.

Provides user data export, deletion, and privacy management endpoints.
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ...api.dependencies.services import get_auth_service
from ...auth import get_current_user as auth_get_current_user
from ...core.enums import PermissionName
from ...database import get_db
from ...dependencies.permissions import require_permission
from ...models.user import User
from ...schemas.privacy import (
    DataExportResponse,
    PrivacyStatisticsResponse,
    RetentionPolicyResponse,
    UserDataDeletionRequest,
    UserDataDeletionResponse,
)
from ...services.audit_service import AuditService
from ...services.auth_service import AuthService
from ...services.privacy_service import PrivacyService

logger = logging.getLogger(__name__)

# V1 router - mounted at /api/v1/privacy
router = APIRouter(tags=["privacy"])


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
        logger.error(f"Error exporting user data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export user data",
        )


@router.post("/delete/me", response_model=UserDataDeletionResponse)
async def delete_my_data(
    request: UserDataDeletionRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserDataDeletionResponse:
    """
    Delete user data (GDPR right to be forgotten).

    Can either anonymize data or completely delete the account.
    """
    privacy_service = PrivacyService(db)

    try:
        if request.delete_account:
            # Full account deletion
            deletion_stats = await asyncio.to_thread(
                privacy_service.delete_user_data, current_user.id, delete_account=True
            )
            try:
                AuditService(db).log(
                    action="user.delete",
                    resource_type="user",
                    resource_id=current_user.id,
                    actor=current_user,
                    actor_type="user",
                    description="User deleted account",
                    metadata={"delete_account": True},
                    request=http_request,
                )
            except Exception:
                logger.warning("Audit log write failed for user delete", exc_info=True)
            return UserDataDeletionResponse(
                status="success",
                message="Account and all associated data deleted",
                deletion_stats=deletion_stats,
                account_deleted=True,
            )
        else:
            # Anonymize only
            success = await asyncio.to_thread(privacy_service.anonymize_user, current_user.id)
            if success:
                try:
                    AuditService(db).log(
                        action="user.delete",
                        resource_type="user",
                        resource_id=current_user.id,
                        actor=current_user,
                        actor_type="user",
                        description="User anonymized account data",
                        metadata={"delete_account": False},
                        request=http_request,
                    )
                except Exception:
                    logger.warning("Audit log write failed for user anonymize", exc_info=True)
                return UserDataDeletionResponse(
                    status="success",
                    message="Personal data anonymized",
                    deletion_stats={},
                    account_deleted=False,
                )
            else:
                raise Exception("Anonymization failed")

    except ValueError as e:
        # Business rule violations (e.g., has active bookings)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting user data: {str(e)}")
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
        logger.error(f"Error getting privacy statistics: {str(e)}")
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
        logger.error(f"Error applying retention policies: {str(e)}")
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
        logger.error(f"Error exporting user data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export user data",
        )


@router.post("/delete/user/{user_id}", response_model=UserDataDeletionResponse)
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
    """
    privacy_service = PrivacyService(db)

    try:
        deletion_stats = await asyncio.to_thread(
            privacy_service.delete_user_data, user_id, delete_account=request.delete_account
        )
        try:
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
        except Exception:
            logger.warning("Audit log write failed for admin user delete", exc_info=True)
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
        logger.error(f"Error deleting user data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user data",
        )
