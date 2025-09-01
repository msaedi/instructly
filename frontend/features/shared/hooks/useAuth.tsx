// frontend/features/shared/hooks/useAuth.tsx
'use client';

import React, { useState, useEffect, createContext, useContext, ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { API_ENDPOINTS, fetchWithAuth, getErrorMessage } from '@/lib/api';
import { logger } from '@/lib/logger';
import {
  transferGuestSearchesToAccount,
  getGuestSessionId,
  clearGuestSession,
} from '@/lib/searchTracking';
import { withApiBase } from '@/lib/apiBase';

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  roles: string[]; // Changed from single role to roles array
  permissions: string[]; // Added permissions array
  is_active: boolean;
  created_at: string;
  updated_at: string;
  profile_image_url?: string;
  unread_messages_count?: number;
  unread_platform_messages_count?: number;
  credits_balance?: number;
  profile_picture_version?: number;
  has_profile_picture?: boolean;
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
  const hasToken = typeof window !== 'undefined' && !!localStorage.getItem('access_token');
  // Initialize user from localStorage if token exists to prevent flashing
  const [user, setUser] = useState<User | null>(() => {
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('access_token');
      const cachedUser = localStorage.getItem('cached_user');
      if (token && cachedUser) {
        try {
          return JSON.parse(cachedUser);
        } catch {
          return null;
        }
      }
    }
    return null;
  });
  // Don't show loading if we have cached user data
  const [isLoading, setIsLoading] = useState(() => {
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('access_token');
      const cachedUser = localStorage.getItem('cached_user');
      return !(token && cachedUser);
    }
    return true;
  });
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
      let response = await fetchWithAuth(API_ENDPOINTS.ME);

      if (response.status === 429) {
        // Respect Retry-After and retry once silently
        const retryAfter = parseInt(response.headers.get('Retry-After') || '0', 10);
        if (Number.isFinite(retryAfter) && retryAfter > 0) {
          await new Promise((r) => setTimeout(r, retryAfter * 1000));
          response = await fetchWithAuth(API_ENDPOINTS.ME);
        }
      }

      if (response.ok) {
        const userData = await response.json();
        logger.info('User authenticated', {
          userId: userData.id,
          roles: userData.roles,
          email: userData.email,
        });
        setUser(userData);
        // Cache user data to prevent auth loss during navigation
        localStorage.setItem('cached_user', JSON.stringify(userData));
      } else if (response.status === 401) {
        logger.warn('Invalid or expired auth token - clearing session');
        localStorage.removeItem('access_token');
        localStorage.removeItem('cached_user');
        setUser(null);
      } else {
        const msg = await getErrorMessage(response);
        logger.error('Failed to fetch user data', undefined, {
          status: response.status,
          statusText: response.statusText,
        });
        // Don't clear user on non-401 errors if already authenticated
        if (!user) {
          setError(msg);
        }
      }
    } catch (err) {
      logger.error('Authentication check error', err);
      // Don't clear user on network errors if already authenticated
      if (!user) {
        setError('Network error while checking authentication');
      }
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
      logger.info('Login attempt with guest session:', { guestSessionId, hasGuestSession: !!guestSessionId });

      // Use new endpoint if we have a guest session, otherwise use regular login
      const path = guestSessionId ? '/auth/login-with-session' : '/auth/login';
      const apiPath = withApiBase(path);

      // Create full URL for fetch
      const endpoint = typeof window !== 'undefined'
        ? `${window.location.origin}${apiPath}`
        : `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}${path}`;

      logger.info('Login endpoint:', { endpoint, path, apiPath });

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

      logger.info('Sending login request:', {
        endpoint,
        hasGuestSession: !!guestSessionId,
        bodyPreview: guestSessionId ? JSON.parse(body as string) : 'form-data'
      });

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
          logger.info('Initiating guest search transfer for session:', { guestSessionId });
          await transferGuestSearchesToAccount();
          logger.info('Guest search transfer completed after login');
        } else {
          logger.warn('No guest session ID found during login');
        }

        // Immediately fetch and cache user data
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
    // Clear auth token and cached user
    localStorage.removeItem('access_token');
    localStorage.removeItem('cached_user');
    setUser(null);

    // Handle guest session based on user preference
    clearGuestSession(); // This respects the user's clearDataOnLogout preference

    // Force hard navigation to avoid auth guards on current page racing to /login
    if (typeof window !== 'undefined') {
      window.location.assign('/');
    } else {
      router.replace('/');
    }
    logger.info('User logged out');
  };

  const redirectToLogin = (returnUrl?: string) => {
    const url = returnUrl || window.location.pathname + window.location.search;
    const encodedUrl = encodeURIComponent(url);

    logger.info('Redirecting to login', {
      returnUrl: url,
      encodedUrl,
    });

    // Persist intended destination as a fallback to query param
    try {
      if (typeof window !== 'undefined') {
        sessionStorage.setItem('post_login_redirect', url);
      }
    } catch {
      // ignore storage errors
    }

    // Use push to maintain proper navigation history
    router.push(`/login?redirect=${encodedUrl}`);
  };

  // Check authentication on mount: always validate the token if present
  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    if (token) {
      checkAuth();
    } else {
      // Ensure we reflect logged-out state
      setUser(null);
      setIsLoading(false);
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user && hasToken,
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
export function getUserInitials(user: any | null): string {
  if (!user) return '';

  // Handle both last_initial (instructor public view) and last_name (own profile)
  const lastChar = user.last_initial || (user.last_name ? user.last_name[0] : '');
  if (user.first_name && lastChar) {
    return `${user.first_name[0]}${lastChar}`.toUpperCase();
  } else if (user.first_name) {
    return user.first_name[0].toUpperCase();
  } else if (user.email) {
    return user.email[0].toUpperCase();
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
  return colors[hash % colors.length];
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
