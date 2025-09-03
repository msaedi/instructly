import type { User } from './useAuth';

// Helper functions for avatar
export function getUserInitials(user: { first_name?: string; last_name?: string; last_initial?: string; email?: string } | null): string {
  if (!user) return '';

  // Handle both last_initial (instructor public view) and last_name (own profile)
  const lastChar = user.last_initial || (user.last_name && user.last_name.length > 0 ? user.last_name[0] : '');
  if (user.first_name && user.first_name.length > 0 && lastChar) {
    return `${user.first_name[0]!}${lastChar}`.toUpperCase();
  } else if (user.first_name && user.first_name.length > 0) {
    return user.first_name[0]!.toUpperCase();
  } else if (user.email && user.email.length > 0) {
    return user.email[0]!.toUpperCase();
  }

  return '';
}

export function getAvatarColor(userId: string): string {
  // Generate a consistent color based on user ID
  const colors = [
    '#3B82F6', // blue
    '#8B5CF6', // purple
    '#EF4444', // red
    '#10B981', // green
    '#F59E0B', // yellow
    '#EC4899', // pink
    '#14B8A6', // teal
    '#F97316', // orange
  ];

  // Use the first few characters of the ULID to generate a hash
  const hash = userId.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const colorIndex = hash % colors.length;
  return colors[colorIndex]!;
}

// Helper function to check if user has a specific role
export function hasRole(user: User | null, role: string): boolean {
  if (!user || !user.roles) return false;
  return user.roles.includes(role);
}

// Helper function to check if user has any of the specified roles
export function hasAnyRole(user: User | null, roles: string[]): boolean {
  if (!user || !user.roles) return false;
  return roles.some((role) => user.roles.includes(role));
}

// Helper function to check if user has a specific permission
export function hasPermission(user: User | null, permission: string): boolean {
  if (!user || !user.permissions) return false;
  return user.permissions.includes(permission);
}

// Helper function to get the primary role (first role in the array)
export function getPrimaryRole(user: User | null): string | null {
  if (!user || !user.roles || user.roles.length === 0) return null;
  return user.roles[0] || null;
}
