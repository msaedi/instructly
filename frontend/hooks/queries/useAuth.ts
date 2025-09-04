import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { queryFn } from '@/lib/react-query/api';
import { ApiError } from '@/lib/http';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { logger } from '@/lib/logger';
import {
  transferGuestSearchesToAccount,
  getGuestSessionId,
  clearGuestSession,
} from '@/lib/searchTracking';
import { withApiBase } from '@/lib/apiBase';
import { User } from '@/features/shared/hooks/useAuth';

/**
 * Login request type
 */
interface LoginRequest {
  email: string;
  password: string;
}

/**
 * Login response type
 */
interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in?: number;
  user?: User;
}

/**
 * React Query-powered authentication hook
 *
 * This hook provides authentication state management using React Query,
 * which gives us automatic caching, background refetching, and optimistic updates.
 *
 * Features:
 * - Automatic token management
 * - Session persistence across tabs
 * - Guest session transfer on login
 * - Cache invalidation on logout
 * - Integrated with existing auth patterns
 *
 * @example
 * ```tsx
 * function LoginForm() {
 *   const { login, isLoggingIn } = useAuth();
 *
 *   const handleSubmit = async (email, password) => {
 *     try {
 *       await login({ email, password });
 *       router.push('/student/dashboard');
 *     } catch (error) {
 *       showError(error.message);
 *     }
 *   };
 * }
 * ```
 */
export function useAuth() {
  const router = useRouter();
  const queryClient = useQueryClient();

  // Query for current user
  const userQuery = useQuery<User>({
    queryKey: queryKeys.user,
    queryFn: queryFn<User>('/auth/me', { requireAuth: true }),
    staleTime: CACHE_TIMES.SESSION,
    gcTime: CACHE_TIMES.SESSION,
    retry: false,
    // Enable unconditionally; cookie-based sessions are the source of truth
    enabled: true,
  });

  // Login mutation
  const loginMutation = useMutation<LoginResponse, Error, LoginRequest>({
    mutationFn: async ({ email, password }) => {
      const guestSessionId = getGuestSessionId();

      // Use session-aware endpoint if guest session exists
      const endpoint = guestSessionId ? '/auth/login-with-session' : '/auth/login';

      const body = guestSessionId
        ? { email, password, guest_session_id: guestSessionId }
        : { username: email, password };

      const response = await fetch(
        withApiBase(endpoint),
        {
          method: 'POST',
          headers: {
            'Content-Type': guestSessionId
              ? 'application/json'
              : 'application/x-www-form-urlencoded',
          },
          body: guestSessionId ? JSON.stringify(body) : new URLSearchParams(body as unknown as Record<string, string>),
        }
      );

      if (!response.ok) {
        const error = await response.json();
        throw new ApiError(error.detail || 'Login failed', response.status);
      }

      return response.json();
    },
    onSuccess: async (_data) => {
      // Token is cookie-based; no localStorage writes

      // Transfer guest searches if applicable
      const guestSessionId = getGuestSessionId();
      if (guestSessionId) {
        await transferGuestSearchesToAccount();
        logger.info('Guest search transfer completed after login');
      }

      // Invalidate and refetch user data
      await queryClient.invalidateQueries({ queryKey: queryKeys.user });

      logger.info('User logged in successfully');
    },
  });

  // Logout function
  const logout = () => {
    // Clear user data from cache
    queryClient.setQueryData(queryKeys.user, null);
    queryClient.removeQueries({ queryKey: queryKeys.user });

    // Clear all cached data
    queryClient.clear();

    // Handle guest session
    clearGuestSession();

    router.push('/');
    logger.info('User logged out');
  };

  // Redirect to login helper
  const redirectToLogin = (returnUrl?: string) => {
    const url = returnUrl || window.location.pathname + window.location.search;
    const encodedUrl = encodeURIComponent(url);

    logger.info('Redirecting to login', {
      returnUrl: url,
      encodedUrl,
    });

    router.push(`/login?redirect=${encodedUrl}`);
  };

  return {
    // User state
    user: userQuery.data ?? null,
    isAuthenticated: !!userQuery.data,
    isLoading: userQuery.isLoading,
    error: userQuery.error?.message ?? null,

    // Actions
    login: loginMutation.mutateAsync,
    logout,
    redirectToLogin,

    // Mutation states
    isLoggingIn: loginMutation.isPending,
    loginError: loginMutation.error?.message ?? null,

    // Utility to refetch user
    refetchUser: userQuery.refetch,
  };
}

/**
 * Hook to check authentication status without throwing errors
 * Useful for navigation bars and conditional rendering
 */
export function useAuthStatus() {
  const { data: user, isLoading } = useQuery<User>({
    queryKey: queryKeys.user,
    queryFn: queryFn<User>('/auth/me', { requireAuth: true }),
    staleTime: CACHE_TIMES.SESSION,
    enabled: true,
    retry: false,
    throwOnError: false,
  });

  return {
    isAuthenticated: !!user,
    isLoading,
    user,
  };
}

/**
 * Hook to require authentication
 * Redirects to login if not authenticated
 *
 * @example
 * ```tsx
 * function ProtectedPage() {
 *   const { user } = useRequireAuth();
 *
 *   // If we get here, user is authenticated
 *   return <div>Welcome {user.full_name}</div>;
 * }
 * ```
 */
export function useRequireAuth() {
  const router = useRouter();
  const { user, isLoading, isAuthenticated } = useAuthStatus();

  React.useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      const returnUrl = window.location.pathname + window.location.search;
      router.push(`/login?redirect=${encodeURIComponent(returnUrl)}`);
    }
  }, [isLoading, isAuthenticated, router]);

  return {
    user,
    isLoading,
  };
}
