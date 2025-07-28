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

    # Analytics permissions
    VIEW_ANALYTICS = "view_analytics"
    EXPORT_ANALYTICS = "export_analytics"

    # User management permissions
    MANAGE_USERS = "manage_users"
    VIEW_ALL_USERS = "view_all_users"

    # Financial permissions
    VIEW_FINANCIALS = "view_financials"
    MANAGE_FINANCIALS = "manage_financials"

    # Content moderation
    MODERATE_CONTENT = "moderate_content"

    # Instructor management
    MANAGE_INSTRUCTORS = "manage_instructors"
    VIEW_INSTRUCTORS = "view_instructors"

    # Profile management
    MANAGE_OWN_PROFILE = "manage_own_profile"

    # Booking permissions
    CREATE_BOOKINGS = "create_bookings"
    MANAGE_OWN_BOOKINGS = "manage_own_bookings"
    VIEW_ALL_BOOKINGS = "view_all_bookings"

    # Availability management
    MANAGE_OWN_AVAILABILITY = "manage_own_availability"
    VIEW_ALL_AVAILABILITY = "view_all_availability"


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
