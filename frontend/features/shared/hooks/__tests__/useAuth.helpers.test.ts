import {
  getUserInitials,
  getAvatarColor,
  hasRole,
  hasAnyRole,
  hasPermission,
  getPrimaryRole,
} from '../useAuth.helpers';
import type { User } from '../useAuth';

const colors = [
  '#3B82F6',
  '#8B5CF6',
  '#EF4444',
  '#10B981',
  '#F59E0B',
  '#EC4899',
  '#14B8A6',
  '#F97316',
];

describe('useAuth.helpers', () => {
  describe('getUserInitials', () => {
    it('returns empty string for null user', () => {
      expect(getUserInitials(null)).toBe('');
    });

    it('uses first name and last initial when provided', () => {
      expect(getUserInitials({ first_name: 'Alex', last_initial: 'Q' })).toBe('AQ');
    });

    it('uses first name and last name initial when last_initial is missing', () => {
      expect(getUserInitials({ first_name: 'Alex', last_name: 'Lee' })).toBe('AL');
    });

    it('falls back to first name initial when last name is missing', () => {
      expect(getUserInitials({ first_name: 'Alex' })).toBe('A');
    });

    it('falls back to email initial when no names are present', () => {
      expect(getUserInitials({ email: 'test@example.com' })).toBe('T');
    });
  });

  describe('getAvatarColor', () => {
    it('returns a consistent color for the same user id', () => {
      const first = getAvatarColor('user-123');
      const second = getAvatarColor('user-123');
      expect(first).toBe(second);
      expect(colors).toContain(first);
    });

    it('returns different colors for different user ids', () => {
      const first = getAvatarColor('user-123');
      const second = getAvatarColor('user-999');
      expect(colors).toContain(first);
      expect(colors).toContain(second);
      expect(first).not.toBe('');
      expect(second).not.toBe('');
    });
  });

  describe('roles and permissions helpers', () => {
    const user: User = {
      id: 'user-1',
      email: 'test@example.com',
      first_name: 'Test',
      last_name: 'User',
      permissions: ['read', 'write'],
      roles: ['student', 'instructor'],
    };

    it('hasRole returns true only when role exists', () => {
      expect(hasRole(user, 'student')).toBe(true);
      expect(hasRole(user, 'admin')).toBe(false);
    });

    it('hasAnyRole returns true when any role matches', () => {
      expect(hasAnyRole(user, ['admin', 'student'])).toBe(true);
      expect(hasAnyRole(user, ['admin'])).toBe(false);
    });

    it('hasPermission returns true only when permission exists', () => {
      expect(hasPermission(user, 'write')).toBe(true);
      expect(hasPermission(user, 'delete')).toBe(false);
    });

    it('getPrimaryRole returns the first role or null', () => {
      expect(getPrimaryRole(user)).toBe('student');
      expect(getPrimaryRole({ ...user, roles: [] })).toBeNull();
    });
  });
});
