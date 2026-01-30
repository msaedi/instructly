import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { AuthProvider, useAuth } from '../useAuth';
import { http, httpGet, ApiError } from '@/lib/http';
import {
  getGuestSessionId,
  transferGuestSearchesToAccount,
  clearGuestSession,
} from '@/lib/searchTracking';
import { useRouter } from 'next/navigation';

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

jest.mock('@/lib/publicEnv', () => ({
  IS_PRODUCTION: true,
}));

jest.mock('@/lib/http', () => {
  const actual = jest.requireActual('@/lib/http');
  return {
    ...actual,
    http: jest.fn(),
    httpGet: jest.fn(),
  };
});

jest.mock('@/lib/searchTracking', () => ({
  getGuestSessionId: jest.fn(),
  transferGuestSearchesToAccount: jest.fn(),
  clearGuestSession: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
  },
}));

const httpMock = http as jest.Mock;
const httpGetMock = httpGet as jest.Mock;
const getGuestSessionIdMock = getGuestSessionId as jest.Mock;
const transferGuestSearchesToAccountMock = transferGuestSearchesToAccount as jest.Mock;
const clearGuestSessionMock = clearGuestSession as jest.Mock;
const useRouterMock = useRouter as jest.Mock;

const mockUser = {
  id: 'user-1',
  email: 'test@example.com',
  first_name: 'Test',
  last_name: 'User',
  permissions: [],
};

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
  Wrapper.displayName = 'AuthProviderWrapper';
  return Wrapper;
};

describe('useAuth', () => {
  const push = jest.fn();
  const replace = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    useRouterMock.mockReturnValue({ push, replace });
    httpMock.mockResolvedValue({ ok: true });
    httpGetMock.mockResolvedValue(mockUser);
    getGuestSessionIdMock.mockReturnValue(null);
  });

  it('returns unauthenticated state on 401', async () => {
    httpGetMock.mockRejectedValueOnce(new ApiError('Unauthorized', 401));

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.user).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('sets user and authenticated state on success', async () => {
    httpGetMock.mockResolvedValueOnce(mockUser);

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));

    expect(result.current.user).toEqual(mockUser);
    expect(result.current.error).toBeNull();
  });

  it('logs in with guest session and transfers searches', async () => {
    getGuestSessionIdMock.mockReturnValue('guest-123');
    httpGetMock.mockRejectedValueOnce(new ApiError('Unauthorized', 401));
    httpGetMock.mockResolvedValueOnce(mockUser);

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      const ok = await result.current.login('test@example.com', 'password');
      expect(ok).toBe(true);
    });

    expect(httpMock).toHaveBeenCalledWith(
      'POST',
      '/api/v1/auth/login-with-session',
      expect.objectContaining({
        headers: { 'Content-Type': 'application/json' },
        body: {
          email: 'test@example.com',
          password: 'password',
          guest_session_id: 'guest-123',
        },
      })
    );
    expect(transferGuestSearchesToAccountMock).toHaveBeenCalled();

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));
  });

  it('logs in without a guest session using form data', async () => {
    getGuestSessionIdMock.mockReturnValue(null);
    httpGetMock.mockRejectedValueOnce(new ApiError('Unauthorized', 401));
    httpGetMock.mockResolvedValueOnce(mockUser);

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      const ok = await result.current.login('test@example.com', 'password');
      expect(ok).toBe(true);
    });

    expect(httpMock).toHaveBeenCalledWith(
      'POST',
      '/api/v1/auth/login',
      expect.objectContaining({
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: expect.stringContaining('username=test%40example.com'),
      })
    );
    expect(transferGuestSearchesToAccountMock).not.toHaveBeenCalled();
  });

  it('sets error on login ApiError', async () => {
    httpGetMock.mockRejectedValueOnce(new ApiError('Unauthorized', 401));
    httpMock.mockRejectedValueOnce(new ApiError('Login failed', 400, { detail: 'Invalid credentials' }));

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      const ok = await result.current.login('bad@example.com', 'password');
      expect(ok).toBe(false);
    });

    expect(result.current.error).toBe('Invalid credentials');
  });

  it('suppresses server logout without user activation', () => {
    httpGetMock.mockResolvedValueOnce(mockUser);
    Object.defineProperty(navigator, 'userActivation', {
      value: { isActive: false, hasBeenActive: false },
      configurable: true,
    });

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    act(() => {
      result.current.logout();
    });

    expect(clearGuestSessionMock).toHaveBeenCalled();
    expect(httpMock).not.toHaveBeenCalled();
  });

  it('redirects to login with encoded return URL', () => {
    httpGetMock.mockRejectedValueOnce(new ApiError('Unauthorized', 401));
    window.history.pushState({}, '', '/student/dashboard?tab=rewards');

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    act(() => {
      result.current.redirectToLogin();
    });

    expect(sessionStorage.getItem('post_login_redirect')).toBe('/student/dashboard?tab=rewards');
    expect(push).toHaveBeenCalledWith(
      '/login?redirect=%2Fstudent%2Fdashboard%3Ftab%3Drewards'
    );
  });

  it('sets network error when non-ApiError occurs (lines 100-102)', async () => {
    // A generic Error (not ApiError) should trigger lines 100-102
    httpGetMock.mockRejectedValueOnce(new Error('Network failure'));

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // Should set error message when user not already loaded
    expect(result.current.error).toBe('Network error while checking authentication');
    expect(result.current.user).toBeNull();
  });

  it('sets network error on login when non-ApiError occurs (lines 183-184)', async () => {
    httpGetMock.mockRejectedValueOnce(new ApiError('Unauthorized', 401));
    // Non-ApiError during login
    httpMock.mockRejectedValueOnce(new Error('Network failure'));

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      const ok = await result.current.login('test@example.com', 'password');
      expect(ok).toBe(false);
    });

    expect(result.current.error).toBe('Network error during login');
  });

  it('logs out with user activation present (lines 217-227)', async () => {
    httpGetMock.mockResolvedValueOnce(mockUser);

    // Mock userActivation as active
    Object.defineProperty(navigator, 'userActivation', {
      value: { isActive: true, hasBeenActive: true },
      configurable: true,
    });

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));

    act(() => {
      result.current.logout();
    });

    // Should call backend logout when user is activated
    expect(httpMock).toHaveBeenCalledWith('POST', '/api/v1/public/logout');
    expect(clearGuestSessionMock).toHaveBeenCalled();
  });

  it('throws error when useAuth is used outside AuthProvider (line 275)', () => {
    // Suppress console.error for this test
    const originalError = console.error;
    console.error = jest.fn();

    // Create wrapper without AuthProvider
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const BadWrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    expect(() => {
      renderHook(() => useAuth(), { wrapper: BadWrapper });
    }).toThrow('useAuth must be used within an AuthProvider');

    console.error = originalError;
  });

  it('redirects to login with custom return URL', () => {
    httpGetMock.mockRejectedValueOnce(new ApiError('Unauthorized', 401));

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    act(() => {
      result.current.redirectToLogin('/custom/path');
    });

    expect(sessionStorage.getItem('post_login_redirect')).toBe('/custom/path');
    expect(push).toHaveBeenCalledWith('/login?redirect=%2Fcustom%2Fpath');
  });

  it('handles sessionStorage error in redirectToLogin gracefully', () => {
    httpGetMock.mockRejectedValueOnce(new ApiError('Unauthorized', 401));

    // Mock sessionStorage to throw
    const originalSetItem = sessionStorage.setItem;
    sessionStorage.setItem = () => {
      throw new Error('Storage full');
    };

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    // Should not throw even when sessionStorage fails
    act(() => {
      result.current.redirectToLogin('/path');
    });

    expect(push).toHaveBeenCalledWith('/login?redirect=%2Fpath');

    sessionStorage.setItem = originalSetItem;
  });

  it('calls checkAuth and refetches user data', async () => {
    httpGetMock.mockResolvedValueOnce(mockUser);

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));

    // Record the call count before checkAuth
    const callCountBefore = httpGetMock.mock.calls.length;

    // Reset mock for next call and call checkAuth
    httpGetMock.mockResolvedValueOnce({ ...mockUser, first_name: 'Updated' });

    await act(async () => {
      await result.current.checkAuth();
    });

    // Should have made at least one more API call after checkAuth
    expect(httpGetMock.mock.calls.length).toBeGreaterThan(callCountBefore);
  });

  it('handles hasBeenActive in userActivation for logout', async () => {
    httpGetMock.mockResolvedValueOnce(mockUser);

    // Only hasBeenActive is true (isActive is false)
    Object.defineProperty(navigator, 'userActivation', {
      value: { isActive: false, hasBeenActive: true },
      configurable: true,
    });

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));

    act(() => {
      result.current.logout();
    });

    // Should still call backend logout when hasBeenActive
    expect(httpMock).toHaveBeenCalledWith('POST', '/api/v1/public/logout');
  });

  it('handles no userActivation API (line 201 - hasActivationSignal false)', async () => {
    httpGetMock.mockResolvedValueOnce(mockUser);

    // Remove userActivation entirely
    Object.defineProperty(navigator, 'userActivation', {
      value: undefined,
      configurable: true,
    });

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));

    act(() => {
      result.current.logout();
    });

    // Without userActivation API, should still allow logout
    expect(httpMock).toHaveBeenCalledWith('POST', '/api/v1/public/logout');
  });
});
