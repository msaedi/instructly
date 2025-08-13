// frontend/utils/nameDisplay.ts
/**
 * Name display utilities for consistent privacy-protected formatting
 */

import { User } from '@/types/booking';

/**
 * Format instructor name for student display with privacy protection
 * Returns "FirstName L." format for privacy
 */
export const formatInstructorNameForStudent = (
  firstName: string | null | undefined,
  lastInitial: string | null | undefined
): string => {
  if (!firstName) return 'Instructor';
  if (!lastInitial) return firstName;
  return `${firstName} ${lastInitial}.`;
};

/**
 * Format instructor name for student display using User object
 * Extracts first name and last initial for privacy
 */
export const formatInstructorFromUser = (instructor: any | null | undefined): string => {
  if (!instructor) return 'Instructor';

  const firstName = instructor.first_name;
  const lastInitial = instructor.last_initial || null;

  return formatInstructorNameForStudent(firstName, lastInitial);
};

/**
 * Format user's full name (for contexts where full name is appropriate)
 * Used for the user's own profile, admin views, etc.
 */
export const formatFullName = (user: any | null | undefined): string => {
  if (!user) return 'User';

  const firstName = user.first_name || '';
  // For instructors in public context, use last_initial
  // For authenticated users (own profile), use last_name
  const lastName = user.last_initial ? `${user.last_initial}.` : (user.last_name || '');

  return `${firstName} ${lastName}`.trim() || user.email || 'User';
};

/**
 * Get user initials for avatar display
 */
export const getUserInitials = (user: any | null | undefined): string => {
  if (!user) return '??';

  const firstName = user.first_name || '';
  // Use last_initial for instructors, last_name for authenticated users
  const lastInitialChar = user.last_initial ||
                          (user.last_name ? user.last_name.charAt(0).toUpperCase() : '');
  const firstInitial = firstName.charAt(0).toUpperCase();

  return (firstInitial + lastInitialChar) || '??';
};

/**
 * Format user display name (first name only for friendly contexts)
 */
export const formatDisplayName = (user: User | null | undefined): string => {
  if (!user) return 'User';
  return user.first_name || user.email || 'User';
};
