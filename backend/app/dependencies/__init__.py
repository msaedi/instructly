"""
FastAPI dependencies for the InstaInstru application.
"""

from .permissions import (
    get_permission_service,
    permission_checker,
    require_all_permissions,
    require_any_permission,
    require_permission,
    require_role,
)

__all__ = [
    "get_permission_service",
    "require_permission",
    "require_any_permission",
    "require_all_permissions",
    "require_role",
    "permission_checker",
]
