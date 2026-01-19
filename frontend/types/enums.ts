// frontend/types/enums.ts
/**
 * Core enums for the InstaInstru platform frontend.
 *
 * These enums match the backend definitions for consistency
 * and type safety across the application.
 */

/**
 * Standard role names in the RBAC system.
 *
 * These are the core roles that ship with the platform.
 */
export enum RoleName {
  ADMIN = 'admin',
  INSTRUCTOR = 'instructor',
  STUDENT = 'student',
}

/**
 * Standard permission names in the RBAC system.
 * These must match the backend PermissionName enum exactly.
 */
export enum PermissionName {
  // Shared permissions (all authenticated users)
  MANAGE_OWN_PROFILE = 'manage_own_profile',
  VIEW_OWN_BOOKINGS = 'view_own_bookings',
  VIEW_OWN_SEARCH_HISTORY = 'view_own_search_history',
  CHANGE_OWN_PW = 'change_own_password',
  DELETE_OWN_ACCOUNT = 'delete_own_account',

  // Student-specific permissions
  VIEW_INSTRUCTORS = 'view_instructors',
  VIEW_INSTRUCTOR_AVAILABILITY = 'view_instructor_availability',
  CREATE_BOOKINGS = 'create_bookings',
  CANCEL_OWN_BOOKINGS = 'cancel_own_bookings',
  VIEW_BOOKING_DETAILS = 'view_booking_details',

  // Instructor-specific permissions
  MANAGE_INSTRUCTOR_PROFILE = 'manage_instructor_profile',
  MANAGE_SERVICES = 'manage_services',
  MANAGE_AVAILABILITY = 'manage_availability',
  VIEW_INCOMING_BOOKINGS = 'view_incoming_bookings',
  COMPLETE_BOOKINGS = 'complete_bookings',
  CANCEL_STUDENT_BOOKINGS = 'cancel_student_bookings',
  VIEW_OWN_INSTRUCTOR_ANALYTICS = 'view_own_instructor_analytics',
  SUSPEND_OWN_INSTRUCTOR_ACCOUNT = 'suspend_own_instructor_account',

  // Admin permissions
  VIEW_ALL_USERS = 'view_all_users',
  MANAGE_USERS = 'manage_users',
  VIEW_SYSTEM_ANALYTICS = 'view_system_analytics',
  EXPORT_ANALYTICS = 'export_analytics',
  VIEW_ALL_BOOKINGS = 'view_all_bookings',
  MANAGE_ALL_BOOKINGS = 'manage_all_bookings',
  ACCESS_MONITORING = 'access_monitoring',
  MODERATE_CONTENT = 'moderate_content',
  VIEW_FINANCIALS = 'view_financials',
  MANAGE_FINANCIALS = 'manage_financials',
  MANAGE_ROLES = 'manage_roles',
  MANAGE_PERMISSIONS = 'manage_permissions',
}

/**
 * User account lifecycle statuses.
 */
export enum AccountStatus {
  ACTIVE = 'active',
  SUSPENDED = 'suspended',
  DEACTIVATED = 'deactivated',
}

/**
 * Types of searches that can be performed.
 */
export enum SearchType {
  NATURAL_LANGUAGE = 'natural_language',
  CATEGORY = 'category',
  SERVICE_PILL = 'service_pill',
  FILTER = 'filter',
  SEARCH_HISTORY = 'search_history',
}

/**
 * Device types for analytics tracking.
 */
export enum DeviceType {
  DESKTOP = 'desktop',
  MOBILE = 'mobile',
  TABLET = 'tablet',
  UNKNOWN = 'unknown',
}

/**
 * Types of search result interactions.
 */
export enum InteractionType {
  CLICK = 'click',
  HOVER = 'hover',
  BOOKMARK = 'bookmark',
  VIEW_PROFILE = 'view_profile',
  CONTACT = 'contact',
}

/**
 * Types of user consent for data collection.
 */
export enum ConsentType {
  ESSENTIAL = 'essential',
  ANALYTICS = 'analytics',
  PERSONALIZATION = 'personalization',
  MARKETING = 'marketing',
}
