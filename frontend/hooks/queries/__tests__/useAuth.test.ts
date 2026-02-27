import React from 'react';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useAuth, useAuthStatus, useRequireAuth } from '../useAuth';
import { queryFn } from '@/lib/react-query/api';
import { http, ApiError } from '@/lib/http';
import { queryKeys } from '@/lib/react-query/queryClient';
import {
  transferGuestSearchesToAccount,
  getGuestSessionId,
  clearGuestSession,
} from '@/lib/searchTracking';

jest.mock('next/navigation');

jest.mock('@/lib/react-query/api', () => ({
  queryFn: jest.fn(),
}));

jest.mock('@/lib/http', () => {
  const actual = jest.requireActual('@/lib/http');
  return { ...actual, http: jest.fn() };
});

jest.mock('@/lib/searchTracking', () => ({
  transferGuestSearchesToAccount: jest.fn(),
  getGuestSessionId: jest.fn(),
  clearGuestSession: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    debug: jest.fn(),
  },
}));

const queryFnMock = queryFn as jest.Mock;
const httpMock = http as jest.Mock;
const getGuestSessionIdMock = getGuestSessionId as jest.Mock;
const transferGuestSearchesMock = transferGuestSearchesToAccount as jest.Mock;
const clearGuestSessionMock = clearGuestSession as jest.Mock;
const useRouterMock = useRouter as jest.Mock;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return { wrapper, queryClient };
};

const makeQueryFn = (value: unknown, options?: { reject?: boolean; pending?: boolean }) => {
  if (options?.pending) {
    return () => new Promise(() => {});
  }
  if (options?.reject) {
    return () => Promise.reject(value);
  }
  return () => Promise.resolve(value);
};

describe('useAuth', () => {
  const pushMock = jest.fn();

  beforeEach(() => {
    queryFnMock.mockReset();
    httpMock.mockReset();
    getGuestSessionIdMock.mockReset();
    transferGuestSearchesMock.mockReset();
    clearGuestSessionMock.mockReset();
    useRouterMock.mockReturnValue({
      push: pushMock,
      replace: jest.fn(),
      prefetch: jest.fn(),
    });
  });

  it('exposes user state from the auth query', async () => {
    const user = { id: 'user-1', email: 'test@example.com' };
    queryFnMock.mockReturnValue(makeQueryFn(user));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));
    expect(result.current.user).toEqual(user);
  });

  it('logs in with guest session and transfers searches', async () => {
    queryFnMock.mockReturnValue(makeQueryFn(null));
    getGuestSessionIdMock.mockReturnValue('guest-123');
    httpMock.mockResolvedValueOnce({});
    transferGuestSearchesMock.mockResolvedValueOnce(undefined);

    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await result.current.login({ email: 'test@example.com', password: 'secret' });
    });

    expect(httpMock).toHaveBeenCalledWith('POST', '/api/v1/auth/login-with-session', {
      headers: { 'Content-Type': 'application/json' },
      body: {
        email: 'test@example.com',
        password: 'secret',
        guest_session_id: 'guest-123',
      },
    });
    expect(transferGuestSearchesMock).toHaveBeenCalled();
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.user });
  });

  it('logs in without guest session using urlencoded payload', async () => {
    queryFnMock.mockReturnValue(makeQueryFn(null));
    getGuestSessionIdMock.mockReturnValue(null);
    httpMock.mockResolvedValueOnce({});

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await result.current.login({ email: 'test@example.com', password: 'secret' });
    });

    expect(httpMock).toHaveBeenCalledWith('POST', '/api/v1/auth/login', {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username: 'test@example.com', password: 'secret' }).toString(),
    });
  });

  it('surfaces ApiError details on login failure', async () => {
    queryFnMock.mockReturnValue(makeQueryFn(null));
    getGuestSessionIdMock.mockReturnValue(null);
    httpMock.mockRejectedValueOnce(new ApiError('Failed', 400, { detail: 'Invalid credentials' }));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAuth(), { wrapper });

    await expect(
      result.current.login({ email: 'test@example.com', password: 'bad' })
    ).rejects.toThrow('Invalid credentials');
  });

  it('re-throws non-ApiError as Error from login mutationFn (line 101)', async () => {
    queryFnMock.mockReturnValue(makeQueryFn(null));
    getGuestSessionIdMock.mockReturnValue(null);
    // Throw a generic Error, NOT ApiError — exercises line 101: throw error as Error
    httpMock.mockRejectedValueOnce(new TypeError('Network request failed'));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAuth(), { wrapper });

    await expect(
      result.current.login({ email: 'test@example.com', password: 'bad' })
    ).rejects.toThrow('Network request failed');
  });

  it('clears cache and redirects on logout', async () => {
    queryFnMock.mockReturnValue(makeQueryFn(null));

    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(queryKeys.user, { id: 'user-1' });

    const { result } = renderHook(() => useAuth(), { wrapper });

    act(() => {
      result.current.logout();
    });

    expect(clearGuestSessionMock).toHaveBeenCalled();
    expect(pushMock).toHaveBeenCalledWith('/');
    expect(queryClient.getQueryData(queryKeys.user)).toBeUndefined();
  });

  it('redirects to login with encoded return URL', () => {
    queryFnMock.mockReturnValue(makeQueryFn(null));
    window.history.pushState({}, '', '/profile?tab=1');

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAuth(), { wrapper });

    act(() => {
      result.current.redirectToLogin();
    });

    expect(pushMock).toHaveBeenCalledWith('/login?redirect=%2Fprofile%3Ftab%3D1');
  });
});

describe('useAuthStatus', () => {
  beforeEach(() => {
    queryFnMock.mockReset();
    useRouterMock.mockReturnValue({
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
    });
  });

  it('returns authenticated state when user exists', async () => {
    queryFnMock.mockReturnValue(makeQueryFn({ id: 'user-2' }));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAuthStatus(), { wrapper });

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));
  });

  it('returns unauthenticated state when user is null', async () => {
    queryFnMock.mockReturnValue(makeQueryFn(null));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAuthStatus(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isAuthenticated).toBe(false);
  });

  it('returns unauthenticated state when query errors', async () => {
    queryFnMock.mockReturnValue(makeQueryFn(new Error('Auth failed'), { reject: true }));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAuthStatus(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isAuthenticated).toBe(false);
  });
});

describe('useRequireAuth', () => {
  const pushMock = jest.fn();

  beforeEach(() => {
    queryFnMock.mockReset();
    useRouterMock.mockReturnValue({
      push: pushMock,
      replace: jest.fn(),
      prefetch: jest.fn(),
    });
  });

  it('redirects to login when unauthenticated', async () => {
    queryFnMock.mockReturnValue(makeQueryFn(null));
    window.history.pushState({}, '', '/settings?tab=security');

    const { wrapper } = createWrapper();
    renderHook(() => useRequireAuth(), { wrapper });

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/login?redirect=%2Fsettings%3Ftab%3Dsecurity'));
  });

  it('does not redirect when authenticated', async () => {
    queryFnMock.mockReturnValue(makeQueryFn({ id: 'user-3' }));

    const { wrapper } = createWrapper();
    renderHook(() => useRequireAuth(), { wrapper });

    await waitFor(() => expect(pushMock).not.toHaveBeenCalled());
  });

  it('does not redirect while loading', async () => {
    queryFnMock.mockReturnValue(makeQueryFn(null, { pending: true }));

    const { wrapper } = createWrapper();
    renderHook(() => useRequireAuth(), { wrapper });

    await act(async () => {
      await Promise.resolve();
    });

    expect(pushMock).not.toHaveBeenCalled();
  });
});
