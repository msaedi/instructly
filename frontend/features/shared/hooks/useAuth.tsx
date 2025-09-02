// frontend/features/shared/hooks/useAuth.tsx
'use client';

import React, { useState, useEffect, useCallback, createContext, useContext, ReactNode, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/react-query/queryClient';
import { useRouter } from 'next/navigation';
import { API_ENDPOINTS } from '@/lib/api';
import { httpGet, ApiError } from '@/lib/http';
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
  phone?: string;
  zip_code?: string;
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
  // Cookie-based sessions: no token gating
  const hasToken = true;
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const userRef = useRef<User | null>(null);

  useEffect(() => {
    userRef.current = user;
  }, [user]);

  const queryClient = useQueryClient();
  const userQuery = useQuery<User>({
    queryKey: queryKeys.user,
    queryFn: async () => {
      logger.info('Checking authentication status');
      const data = (await httpGet(withApiBase(API_ENDPOINTS.ME))) as User;
      return data;
    },
    staleTime: 1000 * 60 * 5,
    retry: 0,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (userQuery.data) {
      setUser(userQuery.data);
      setError(null);
      setIsLoading(false);
      if (process.env.NODE_ENV !== 'production') {
        logger.debug('[TRACE] checkAuth() success', { nowHasUser: true });
      }
    } else if (userQuery.isError) {
      const err: unknown = userQuery.error as unknown;
      if (err instanceof ApiError && err.status === 401) {
        logger.warn('Not authenticated');
        setUser(null);
        setError(null);
      } else if (err instanceof Error) {
        logger.error('Authentication check error', err);
        if (!userRef.current) setError('Network error while checking authentication');
      }
      setIsLoading(false);
    } else if (userQuery.isLoading) {
      setIsLoading(true);
    }
  }, [userQuery.data, userQuery.isError, userQuery.error, userQuery.isLoading]);

  const checkAuth = useCallback(async () => {
    (window as unknown as { __checkAuthCount?: number }).__checkAuthCount = ((window as unknown as { __checkAuthCount?: number }).__checkAuthCount || 0) + 1;
    if (process.env.NODE_ENV !== 'production') {
      logger.debug('[TRACE] checkAuth()', {
        count: (window as unknown as { __checkAuthCount?: number }).__checkAuthCount,
        hadUser: !!userRef.current,
      });
    }
    await queryClient.invalidateQueries({ queryKey: queryKeys.user });
    await userQuery.refetch();
  }, [queryClient, userQuery]);

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

      // Create full URL for fetch - check if apiPath is already absolute
      const isAbsoluteUrl = apiPath.startsWith('http://') || apiPath.startsWith('https://');
      const endpoint = typeof window !== 'undefined'
        ? (isAbsoluteUrl ? apiPath : `${window.location.origin}${apiPath}`)
        : apiPath;

      logger.info('Login endpoint:', { endpoint, path, apiPath, isAbsoluteUrl });

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
        await response.json();
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
    // Clear auth state locally
    setUser(null);
    clearGuestSession();

    // Request backend to clear cookies
    fetch(withApiBase('/api/public/logout'), { method: 'POST', credentials: 'include' })
      .catch(() => {})
      .finally(() => {
        // Navigate home after clearing
        if (typeof window !== 'undefined') {
          window.location.assign('/');
        } else {
          router.replace('/');
        }
      });
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

  // useQuery will fetch on mount; no need to call checkAuth here

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
