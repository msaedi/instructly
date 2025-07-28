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
 */
export enum PermissionName {
  // Analytics permissions
  VIEW_ANALYTICS = 'view_analytics',
  EXPORT_ANALYTICS = 'export_analytics',

  // User management permissions
  MANAGE_USERS = 'manage_users',
  VIEW_ALL_USERS = 'view_all_users',

  // Financial permissions
  VIEW_FINANCIALS = 'view_financials',
  MANAGE_FINANCIALS = 'manage_financials',

  // Content moderation
  MODERATE_CONTENT = 'moderate_content',

  // Instructor management
  MANAGE_INSTRUCTORS = 'manage_instructors',
  VIEW_INSTRUCTORS = 'view_instructors',

  // Profile management
  MANAGE_OWN_PROFILE = 'manage_own_profile',

  // Booking permissions
  CREATE_BOOKINGS = 'create_bookings',
  MANAGE_OWN_BOOKINGS = 'manage_own_bookings',
  VIEW_ALL_BOOKINGS = 'view_all_bookings',

  // Availability management
  MANAGE_OWN_AVAILABILITY = 'manage_own_availability',
  VIEW_ALL_AVAILABILITY = 'view_all_availability',
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
