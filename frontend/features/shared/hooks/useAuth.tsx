// frontend/features/shared/hooks/useAuth.tsx
'use client';

import React, { useState, useEffect, createContext, useContext, ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { API_ENDPOINTS, fetchWithAuth } from '@/lib/api';
import { logger } from '@/lib/logger';
import {
  transferGuestSearchesToAccount,
  getGuestSessionId,
  clearGuestSession,
} from '@/lib/searchTracking';

export interface User {
  id: number;
  email: string;
  full_name: string;
  roles: string[]; // Changed from single role to roles array
  permissions: string[]; // Added permissions array
  is_active: boolean;
  created_at: string;
  updated_at: string;
  profile_image_url?: string;
  first_name?: string;
  last_name?: string;
  unread_messages_count?: number;
  unread_platform_messages_count?: number;
  credits_balance?: number;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<boolean>;
  logout: () => void;
  checkAuth: () => Promise<void>;
  redirectToLogin: (returnUrl?: string) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const checkAuth = async () => {
    setIsLoading(true);
    setError(null);

    const token = localStorage.getItem('access_token');

    if (!token) {
      logger.debug('No auth token found');
      setUser(null);
      setIsLoading(false);
      return;
    }

    try {
      logger.info('Checking authentication status');
      const response = await fetchWithAuth(API_ENDPOINTS.ME);

      if (response.ok) {
        const userData = await response.json();

        // Parse name fields
        const nameParts = userData.full_name?.split(' ') || [];
        userData.first_name = nameParts[0] || '';
        userData.last_name = nameParts.slice(1).join(' ') || '';

        logger.info('User authenticated', {
          userId: userData.id,
          roles: userData.roles,
          email: userData.email,
        });
        setUser(userData);
      } else if (response.status === 401) {
        logger.warn('Invalid or expired auth token');
        localStorage.removeItem('access_token');
        setUser(null);
      } else {
        logger.error('Failed to fetch user data', undefined, {
          status: response.status,
          statusText: response.statusText,
        });
        setError('Failed to verify authentication');
      }
    } catch (err) {
      logger.error('Authentication check error', err);
      setError('Network error while checking authentication');
    } finally {
      setIsLoading(false);
    }
  };

  const login = async (email: string, password: string): Promise<boolean> => {
    setIsLoading(true);
    setError(null);

    try {
      // Get guest session ID if available
      const guestSessionId = getGuestSessionId();

      // Use new endpoint if we have a guest session, otherwise use regular login
      const endpoint = guestSessionId
        ? `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/auth/login-with-session`
        : `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/auth/login`;

      const body = guestSessionId
        ? JSON.stringify({
            email,
            password,
            guest_session_id: guestSessionId,
          })
        : new URLSearchParams({
            username: email,
            password: password,
          });

      const headers = guestSessionId
        ? { 'Content-Type': 'application/json' }
        : { 'Content-Type': 'application/x-www-form-urlencoded' };

      const response = await fetch(endpoint, {
        method: 'POST',
        headers,
        body,
      });

      if (response.ok) {
        const data = await response.json();
        localStorage.setItem('access_token', data.access_token);

        // Transfer guest searches to user account (backend handles this automatically)
        if (guestSessionId) {
          await transferGuestSearchesToAccount();
          logger.info('Guest search transfer completed after login');
        }

        await checkAuth();

        return true;
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Login failed');
        return false;
      }
    } catch (err) {
      logger.error('Login error', err);
      setError('Network error during login');
      return false;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    // Clear auth token
    localStorage.removeItem('access_token');
    setUser(null);

    // Handle guest session based on user preference
    clearGuestSession(); // This respects the user's clearDataOnLogout preference

    router.push('/');
    logger.info('User logged out');
  };

  const redirectToLogin = (returnUrl?: string) => {
    const url = returnUrl || window.location.pathname + window.location.search;
    const encodedUrl = encodeURIComponent(url);

    logger.info('Redirecting to login', {
      returnUrl: url,
      encodedUrl,
    });

    // Use replace instead of push to avoid polluting browser history
    // This way the back button won't land on the auth page
    router.replace(`/login?redirect=${encodedUrl}`);
  };

  // Check authentication on mount
  useEffect(() => {
    checkAuth();
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        error,
        login,
        logout,
        checkAuth,
        redirectToLogin,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

// Helper functions for avatar
export function getUserInitials(user: User | null): string {
  if (!user) return '';

  if (user.first_name && user.last_name) {
    return `${user.first_name[0]}${user.last_name[0]}`.toUpperCase();
  } else if (user.full_name) {
    const parts = user.full_name.split(' ');
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
    }
    return user.full_name[0].toUpperCase();
  } else if (user.email) {
    return user.email[0].toUpperCase();
  }

  return '';
}

export function getAvatarColor(userId: number): string {
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

  return colors[userId % colors.length];
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
  return user.roles[0];
}
