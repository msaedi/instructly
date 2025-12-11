# backend/app/models/rbac.py
"""
Role-Based Access Control models for InstaInstru platform.

This module defines the RBAC models which provide granular permission
control for users. It includes roles, permissions, and the relationships
between users, roles, and permissions.

Classes:
    Role: User roles for grouping permissions
    Permission: Individual permissions that can be granted
    UserRole: Junction table for user-to-role mapping
    RolePermission: Junction table for role-to-permission mapping
    UserPermission: Individual permission overrides for users
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import ulid

from ..database import Base

if TYPE_CHECKING:
    from .user import User


class Role(Base):
    """
    User roles for access control.

    Roles group related permissions together. Users are assigned roles,
    and inherit all permissions associated with those roles.

    Attributes:
        id: Primary key
        name: Unique role name (e.g., 'admin', 'instructor', 'student')
        description: Human-readable description of the role
        created_at: Role creation timestamp

    Relationships:
        permissions: List of permissions assigned to this role
        users: List of users with this role
    """

    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    permissions: Mapped[List["Permission"]] = relationship(
        secondary="role_permissions",
        back_populates="roles",
        lazy="select",  # Changed from selectin - explicit joinedload used where needed
    )
    users: Mapped[List["User"]] = relationship(
        "User", secondary="user_roles", back_populates="roles"
    )

    def __repr__(self) -> str:
        return f"<Role {self.name}>"


class Permission(Base):
    """
    System permissions for granular access control.

    Permissions define specific actions that can be performed on resources.
    They can be assigned to roles or directly to users.

    Attributes:
        id: Primary key
        name: Unique permission name (e.g., 'view_analytics')
        description: Human-readable description
        resource: The resource this permission applies to (e.g., 'analytics')
        action: The action allowed (e.g., 'view', 'create', 'update', 'delete')
        created_at: Permission creation timestamp

    Relationships:
        roles: List of roles that have this permission
    """

    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    resource: Mapped[Optional[str]] = mapped_column(String(50))
    action: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    roles: Mapped[List["Role"]] = relationship(
        secondary="role_permissions", back_populates="permissions"
    )

    def __repr__(self) -> str:
        return f"<Permission {self.name}>"


class UserRole(Base):
    """
    Junction table for user-to-role mapping.

    This table implements the many-to-many relationship between users and roles.

    Attributes:
        user_id: Foreign key to users table
        role_id: Foreign key to roles table
        assigned_at: Timestamp when the role was assigned
    """

    __tablename__ = "user_roles"

    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RolePermission(Base):
    """
    Junction table for role-to-permission mapping.

    This table implements the many-to-many relationship between roles and permissions.

    Attributes:
        role_id: Foreign key to roles table
        permission_id: Foreign key to permissions table
    """

    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class UserPermission(Base):
    """
    Individual permission overrides for users.

    This table allows granting or revoking specific permissions for individual
    users, overriding their role-based permissions.

    Attributes:
        user_id: Foreign key to users table
        permission_id: Foreign key to permissions table
        granted: Whether the permission is granted (True) or revoked (False)
    """

    __tablename__ = "user_permissions"

    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )
    granted: Mapped[bool] = mapped_column(default=True)

    # Relationships for easier access
    permission: Mapped["Permission"] = relationship()
