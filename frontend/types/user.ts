// frontend/types/user.ts

/**
 * User Type Definitions
 *
 * This module contains all TypeScript interfaces and types related to
 * users, authentication, and user profiles.
 *
 * @module user
 */

import { RoleName } from './enums';

/**
 * User role enumeration
 * Defines the possible roles a user can have in the system
 */
export enum UserRole {
  STUDENT = 'student',
  INSTRUCTOR = 'instructor',
}

/**
 * Base user interface
 *
 * Core user properties shared across the application
 *
 * @interface User
 */
export interface User {
  /** Unique user identifier (ULID string) */
  id: string;

  /** User's email address (used for authentication) */
  email: string;

  /** User's first name (from API: first_name) */
  first_name: string;

  /** User's last name (from API: last_name) */
  last_name: string;

  /** Camel case version for frontend convenience */
  firstName?: string;

  /** Camel case version for frontend convenience */
  lastName?: string;

  /** User's phone number (required) */
  phone: string;

  /** User's zip code */
  zip_code: string;

  /** Camel case version for frontend convenience */
  zipCode?: string;

  /** User role (student or instructor) */
  role: UserRole | string; // string for backward compatibility

  /** Account creation timestamp */
  created_at?: string;

  /** Last update timestamp */
  updated_at?: string;

  /** Whether email is verified (future feature) */
  email_verified?: boolean;

  /** Whether user account is active */
  is_active?: boolean;

  /** Whether user has profile picture (optional API field) */
  has_profile_picture?: boolean;

  /** Profile picture version (optional API field) */
  profile_picture_version?: number;
}

/**
 * Extended user data typically returned from /auth/me endpoint
 *
 * @interface UserData
 * @extends User
 */
export interface UserData extends User {
  /** Instructor profile ID if user is an instructor (ULID string) */
  instructor_profile_id?: string;

  /** Whether user has completed onboarding */
  onboarding_completed?: boolean;

  /** User's preferred language (future feature) */
  preferred_language?: string;

  /** User's timezone (future feature) */
  timezone?: string;
}

// Auth request/response types removed - use generated types from @/features/shared/api/types:
// - LoginRequest: defined inline where needed (OAuth2 form data)
// - LoginResponse: export type LoginResponse = components['schemas']['LoginResponse']
// - RegisterRequest: use generated type from shim
// - PasswordResetRequest: export type PasswordResetRequest = components['schemas']['PasswordResetRequest']

/**
 * Password reset confirmation
 *
 * @interface PasswordResetConfirm
 */
export interface PasswordResetConfirm {
  /** Reset token from email */
  token: string;

  /** New password */
  new_password: string;

  /** Password confirmation */
  password_confirm: string;
}

// UserProfileUpdate removed - use generated types from @/features/shared/api/types

/**
 * Type guard to check if a string is a valid UserRole
 *
 * @param role - String to check
 * @returns boolean indicating if role is valid
 */
export function isValidUserRole(role: string): role is UserRole {
  return Object.values(UserRole).includes(role as UserRole);
}

/**
 * Type guard to check if user is an instructor
 *
 * @param user - User object to check
 * @returns boolean indicating if user is an instructor
 */
export function isInstructorUser(user: User | UserData): boolean {
  // Legacy check for backward compatibility
  if ('role' in user && user.role) {
    return user.role === UserRole.INSTRUCTOR || user.role === 'instructor';
  }
  // New RBAC check
  if ('roles' in user && Array.isArray(user.roles)) {
    return user.roles.includes(RoleName.INSTRUCTOR);
  }
  return false;
}

/**
 * Type guard to check if user is a student
 *
 * @param user - User object to check
 * @returns boolean indicating if user is a student
 */
export function isStudentUser(user: User | UserData): boolean {
  // Legacy check for backward compatibility
  if ('role' in user && user.role) {
    return user.role === UserRole.STUDENT || user.role === 'student';
  }
  // New RBAC check
  if ('roles' in user && Array.isArray(user.roles)) {
    return user.roles.includes(RoleName.STUDENT);
  }
  return false;
}

/**
 * Get user display name with fallback
 *
 * @param user - User object
 * @returns Display name or email fallback
 */
export function getUserDisplayName(user: Partial<User>): string {
  // For friendly contexts, just use first name
  if (user.firstName || user.first_name) {
    return user.firstName || user.first_name || 'User';
  }
  return user.email || 'User';
}

/**
 * Get user full name for formal contexts
 *
 * @param user - User object
 * @returns Full name
 */
export function getUserFullName(user: Partial<User>): string {
  const firstName = user.firstName || user.first_name || '';
  const lastName = user.lastName || user.last_name || '';
  return `${firstName} ${lastName}`.trim() || user.email || 'User';
}

/**
 * Get user initials
 *
 * @param user - User object
 * @returns Two-letter initials
 */
export function getUserInitials(user: Partial<User>): string {
  const firstName = user.firstName || user.first_name || '';
  const lastName = user.lastName || user.last_name || '';
  const firstInitial = firstName.charAt(0).toUpperCase();
  const lastInitial = lastName.charAt(0).toUpperCase();
  return (firstInitial + lastInitial) || '??';
}

/**
 * Format user role for display
 *
 * @param role - User role
 * @returns Formatted role string
 */
export function formatUserRole(role: UserRole | string): string {
  const roleStr = role.toString().toLowerCase();
  return roleStr.charAt(0).toUpperCase() + roleStr.slice(1);
}
