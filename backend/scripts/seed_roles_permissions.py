#!/usr/bin/env python3
"""Seed roles and permissions with ULIDs."""

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import PermissionName, RoleName
from app.models.rbac import Permission, Role, RolePermission


def seed_roles_and_permissions():
    """Seed the database with roles and permissions."""
    engine = create_engine(settings.get_database_url())

    with Session(engine) as session:
        # Check if roles already exist
        existing_roles = session.query(Role).count()
        if existing_roles > 0:
            print(f"Roles already exist ({existing_roles} found), skipping seed")
            return

        print("Seeding roles and permissions...")

        # Create roles
        admin_role = Role(name=RoleName.ADMIN, description="Full system access")
        instructor_role = Role(name=RoleName.INSTRUCTOR, description="Can manage own profile and availability")
        student_role = Role(name=RoleName.STUDENT, description="Can search and book instructors")

        session.add_all([admin_role, instructor_role, student_role])
        session.flush()

        # Create permissions
        permissions = []

        # Shared permissions
        permissions.extend(
            [
                Permission(
                    name=PermissionName.MANAGE_OWN_PROFILE,
                    description="Manage own profile information",
                    resource="profile",
                    action="manage",
                ),
                Permission(
                    name=PermissionName.VIEW_OWN_BOOKINGS,
                    description="View own bookings",
                    resource="bookings",
                    action="view",
                ),
                Permission(
                    name=PermissionName.VIEW_OWN_SEARCH_HISTORY,
                    description="View own search history",
                    resource="search",
                    action="view",
                ),
                Permission(
                    name=PermissionName.CHANGE_OWN_PW,
                    description="Change own password",
                    resource="account",
                    action="update",
                ),
                Permission(
                    name=PermissionName.DELETE_OWN_ACCOUNT,
                    description="Delete own account",
                    resource="account",
                    action="delete",
                ),
            ]
        )

        # Student permissions
        permissions.extend(
            [
                Permission(
                    name=PermissionName.VIEW_INSTRUCTORS,
                    description="View instructor profiles",
                    resource="instructors",
                    action="view",
                ),
                Permission(
                    name=PermissionName.VIEW_INSTRUCTOR_AVAILABILITY,
                    description="View instructor availability",
                    resource="availability",
                    action="view",
                ),
                Permission(
                    name=PermissionName.CREATE_BOOKINGS,
                    description="Create new bookings",
                    resource="bookings",
                    action="create",
                ),
                Permission(
                    name=PermissionName.CANCEL_OWN_BOOKINGS,
                    description="Cancel own bookings",
                    resource="bookings",
                    action="cancel",
                ),
                Permission(
                    name=PermissionName.VIEW_BOOKING_DETAILS,
                    description="View booking details",
                    resource="bookings",
                    action="view",
                ),
                Permission(
                    name=PermissionName.SEND_MESSAGES,
                    description="Send messages in booking chats",
                    resource="messages",
                    action="send",
                ),
                Permission(
                    name=PermissionName.VIEW_MESSAGES,
                    description="View messages in booking chats",
                    resource="messages",
                    action="view",
                ),
            ]
        )

        # Instructor permissions
        permissions.extend(
            [
                Permission(
                    name=PermissionName.MANAGE_INSTRUCTOR_PROFILE,
                    description="Manage instructor profile",
                    resource="instructor_profile",
                    action="manage",
                ),
                Permission(
                    name=PermissionName.MANAGE_SERVICES,
                    description="Manage offered services",
                    resource="services",
                    action="manage",
                ),
                Permission(
                    name=PermissionName.MANAGE_AVAILABILITY,
                    description="Manage availability schedule",
                    resource="availability",
                    action="manage",
                ),
                Permission(
                    name=PermissionName.VIEW_INCOMING_BOOKINGS,
                    description="View incoming bookings",
                    resource="bookings",
                    action="view",
                ),
                Permission(
                    name=PermissionName.COMPLETE_BOOKINGS,
                    description="Mark bookings as completed",
                    resource="bookings",
                    action="complete",
                ),
                Permission(
                    name=PermissionName.CANCEL_STUDENT_BOOKINGS,
                    description="Cancel student bookings",
                    resource="bookings",
                    action="cancel",
                ),
                Permission(
                    name=PermissionName.VIEW_OWN_INSTRUCTOR_ANALYTICS,
                    description="View own instructor analytics",
                    resource="analytics",
                    action="view",
                ),
                Permission(
                    name=PermissionName.SUSPEND_OWN_INSTRUCTOR_ACCOUNT,
                    description="Suspend own instructor account",
                    resource="account",
                    action="suspend",
                ),
            ]
        )

        # Admin permissions
        permissions.extend(
            [
                Permission(
                    name=PermissionName.ADMIN_READ,
                    description="Read admin configuration and dashboards",
                    resource="admin",
                    action="read",
                ),
                Permission(
                    name=PermissionName.ADMIN_MANAGE,
                    description="Manage admin configuration and settings",
                    resource="admin",
                    action="manage",
                ),
                Permission(
                    name=PermissionName.VIEW_ALL_USERS, description="View all users", resource="users", action="view"
                ),
                Permission(
                    name=PermissionName.MANAGE_USERS, description="Manage all users", resource="users", action="manage"
                ),
                Permission(
                    name=PermissionName.VIEW_SYSTEM_ANALYTICS,
                    description="View system-wide analytics",
                    resource="analytics",
                    action="view",
                ),
                Permission(
                    name=PermissionName.EXPORT_ANALYTICS,
                    description="Export analytics data",
                    resource="analytics",
                    action="export",
                ),
                Permission(
                    name=PermissionName.VIEW_ALL_BOOKINGS,
                    description="View all bookings",
                    resource="bookings",
                    action="view",
                ),
                Permission(
                    name=PermissionName.MANAGE_ALL_BOOKINGS,
                    description="Manage all bookings",
                    resource="bookings",
                    action="manage",
                ),
                Permission(
                    name=PermissionName.ACCESS_MONITORING,
                    description="Access monitoring endpoints",
                    resource="monitoring",
                    action="access",
                ),
                Permission(
                    name=PermissionName.MODERATE_CONTENT,
                    description="Moderate user content",
                    resource="content",
                    action="moderate",
                ),
                Permission(
                    name=PermissionName.MODERATE_MESSAGES,
                    description="Moderate chat messages",
                    resource="messages",
                    action="moderate",
                ),
                Permission(
                    name=PermissionName.VIEW_FINANCIALS,
                    description="View financial data",
                    resource="financials",
                    action="view",
                ),
                Permission(
                    name=PermissionName.MANAGE_FINANCIALS,
                    description="Manage financial data",
                    resource="financials",
                    action="manage",
                ),
                Permission(
                    name=PermissionName.MANAGE_ROLES, description="Manage user roles", resource="roles", action="manage"
                ),
                Permission(
                    name=PermissionName.MANAGE_PERMISSIONS,
                    description="Manage permissions",
                    resource="permissions",
                    action="manage",
                ),
            ]
        )

        session.add_all(permissions)
        session.flush()

        # Create a mapping for easy lookup
        perm_map = {p.name: p for p in permissions}

        # Assign permissions to roles
        # Admin gets everything
        for perm in permissions:
            session.add(RolePermission(role_id=admin_role.id, permission_id=perm.id))

        # Student permissions
        student_perms = [
            PermissionName.MANAGE_OWN_PROFILE,
            PermissionName.VIEW_OWN_BOOKINGS,
            PermissionName.VIEW_OWN_SEARCH_HISTORY,
            PermissionName.CHANGE_OWN_PW,
            PermissionName.DELETE_OWN_ACCOUNT,
            PermissionName.VIEW_INSTRUCTORS,
            PermissionName.VIEW_INSTRUCTOR_AVAILABILITY,
            PermissionName.CREATE_BOOKINGS,
            PermissionName.CANCEL_OWN_BOOKINGS,
            PermissionName.VIEW_BOOKING_DETAILS,
            PermissionName.SEND_MESSAGES,
            PermissionName.VIEW_MESSAGES,
        ]
        for perm_name in student_perms:
            perm = perm_map[perm_name]
            session.add(RolePermission(role_id=student_role.id, permission_id=perm.id))

        # Instructor permissions
        instructor_perms = [
            PermissionName.MANAGE_OWN_PROFILE,
            PermissionName.VIEW_OWN_BOOKINGS,
            PermissionName.VIEW_OWN_SEARCH_HISTORY,
            PermissionName.CHANGE_OWN_PW,
            PermissionName.DELETE_OWN_ACCOUNT,
            PermissionName.MANAGE_INSTRUCTOR_PROFILE,
            PermissionName.MANAGE_SERVICES,
            PermissionName.MANAGE_AVAILABILITY,
            PermissionName.VIEW_INCOMING_BOOKINGS,
            PermissionName.COMPLETE_BOOKINGS,
            PermissionName.CANCEL_STUDENT_BOOKINGS,
            PermissionName.VIEW_OWN_INSTRUCTOR_ANALYTICS,
            PermissionName.SUSPEND_OWN_INSTRUCTOR_ACCOUNT,
            PermissionName.SEND_MESSAGES,
            PermissionName.VIEW_MESSAGES,
        ]
        for perm_name in instructor_perms:
            perm = perm_map[perm_name]
            session.add(RolePermission(role_id=instructor_role.id, permission_id=perm.id))

        session.commit()
        print(f"✅ Created {len([admin_role, instructor_role, student_role])} roles")
        print(f"✅ Created {len(permissions)} permissions")
        print("✅ Assigned permissions to roles")


if __name__ == "__main__":
    seed_roles_and_permissions()
