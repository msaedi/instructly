# backend/app/core/enums.py
"""
Core enums for the InstaInstru platform.

This module contains enumeration types used throughout the application
for type safety and consistency. These enums work alongside the RBAC
system, providing standard values while still allowing dynamic additions.
"""

from enum import Enum


class RoleName(str, Enum):
    """
    Standard role names in the RBAC system.

    These are the core roles that ship with the platform. Additional roles
    can be added to the database dynamically, but these are guaranteed to exist.
    """

    ADMIN = "admin"
    INSTRUCTOR = "instructor"
    STUDENT = "student"


class PermissionName(str, Enum):
    """
    Standard permission names in the RBAC system.

    These are the core permissions that ship with the platform. Additional
    permissions can be added to the database dynamically.
    """

    # Shared permissions (all authenticated users)
    MANAGE_OWN_PROFILE = "manage_own_profile"
    VIEW_OWN_BOOKINGS = "view_own_bookings"
    VIEW_OWN_SEARCH_HISTORY = "view_own_search_history"
    CHANGE_OWN_PASSWORD = "change_own_password"
    DELETE_OWN_ACCOUNT = "delete_own_account"

    # Student-specific permissions
    VIEW_INSTRUCTORS = "view_instructors"
    VIEW_INSTRUCTOR_AVAILABILITY = "view_instructor_availability"
    CREATE_BOOKINGS = "create_bookings"
    CANCEL_OWN_BOOKINGS = "cancel_own_bookings"
    VIEW_BOOKING_DETAILS = "view_booking_details"
    SEND_MESSAGES = "send_messages"
    VIEW_MESSAGES = "view_messages"

    # Instructor-specific permissions
    MANAGE_INSTRUCTOR_PROFILE = "manage_instructor_profile"
    MANAGE_SERVICES = "manage_services"
    MANAGE_AVAILABILITY = "manage_availability"
    VIEW_INCOMING_BOOKINGS = "view_incoming_bookings"
    COMPLETE_BOOKINGS = "complete_bookings"
    CANCEL_STUDENT_BOOKINGS = "cancel_student_bookings"
    VIEW_OWN_INSTRUCTOR_ANALYTICS = "view_own_instructor_analytics"
    SUSPEND_OWN_INSTRUCTOR_ACCOUNT = "suspend_own_instructor_account"

    # Admin permissions
    ADMIN_READ = "admin:read"
    ADMIN_MANAGE = "admin:manage"
    VIEW_ALL_USERS = "view_all_users"
    MANAGE_USERS = "manage_users"
    VIEW_SYSTEM_ANALYTICS = "view_system_analytics"
    EXPORT_ANALYTICS = "export_analytics"
    VIEW_ALL_BOOKINGS = "view_all_bookings"
    MANAGE_ALL_BOOKINGS = "manage_all_bookings"
    ACCESS_MONITORING = "access_monitoring"
    MODERATE_CONTENT = "moderate_content"
    MODERATE_MESSAGES = "moderate_messages"
    VIEW_FINANCIALS = "view_financials"
    MANAGE_FINANCIALS = "manage_financials"
    MANAGE_ROLES = "manage_roles"
    MANAGE_PERMISSIONS = "manage_permissions"


class AccountStatus(str, Enum):
    """
    User account lifecycle statuses.
    """

    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


class SearchType(str, Enum):
    """
    Types of searches that can be performed.
    """

    NATURAL_LANGUAGE = "natural_language"
    CATEGORY = "category"
    SERVICE_PILL = "service_pill"
    FILTER = "filter"
    SEARCH_HISTORY = "search_history"


class DeviceType(str, Enum):
    """
    Device types for analytics tracking.
    """

    DESKTOP = "desktop"
    MOBILE = "mobile"
    TABLET = "tablet"
    UNKNOWN = "unknown"


class InteractionType(str, Enum):
    """
    Types of search result interactions.
    """

    CLICK = "click"
    HOVER = "hover"
    BOOKMARK = "bookmark"
    VIEW_PROFILE = "view_profile"
    CONTACT = "contact"


class ConsentType(str, Enum):
    """
    Types of user consent for data collection.
    """

    ESSENTIAL = "essential"
    ANALYTICS = "analytics"
    PERSONALIZATION = "personalization"
    MARKETING = "marketing"
