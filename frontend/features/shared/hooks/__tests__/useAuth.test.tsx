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
});
