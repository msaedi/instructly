import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useUser, useUserSafe, useIsAuthenticated } from '../useUser';
import { httpJson } from '@/features/shared/api/http';
import { withApiBase } from '@/lib/apiBase';

jest.mock('@/features/shared/api/http', () => ({
  httpJson: jest.fn(),
}));

jest.mock('@/lib/apiBase', () => ({
  withApiBase: jest.fn((path: string) => `https://api.test${path}`),
}));

const httpJsonMock = httpJson as jest.Mock;
const withApiBaseMock = withApiBase as jest.Mock;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retryDelay: 0 } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return { wrapper };
};

describe('useUser', () => {
  beforeEach(() => {
    httpJsonMock.mockReset();
    withApiBaseMock.mockClear();
  });

  it('returns user data on success', async () => {
    const user = { id: 'user-1', email: 'test@example.com' };
    httpJsonMock.mockResolvedValueOnce(user);

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUser(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(user);
    expect(withApiBaseMock).toHaveBeenCalledWith('/api/v1/auth/me');
  });

  it('does not retry on 401 errors', async () => {
    httpJsonMock.mockRejectedValueOnce({ status: 401 });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUser(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(httpJsonMock).toHaveBeenCalledTimes(1);
  });

  it('retries on non-401 errors', async () => {
    httpJsonMock.mockRejectedValue({ status: 500 });

    const { wrapper } = createWrapper();
    renderHook(() => useUser(), { wrapper });

    await waitFor(() => expect(httpJsonMock).toHaveBeenCalledTimes(4));
  });
});

describe('useUserSafe', () => {
  beforeEach(() => {
    httpJsonMock.mockReset();
    withApiBaseMock.mockClear();
  });

  it('returns user data on success', async () => {
    const user = { id: 'user-2', email: 'safe@example.com' };
    httpJsonMock.mockResolvedValueOnce(user);

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUserSafe(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(user);
  });

  it('does not retry when an error occurs', async () => {
    httpJsonMock.mockRejectedValueOnce({ status: 500 });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUserSafe(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(httpJsonMock).toHaveBeenCalledTimes(1);
  });

  it('uses the /auth/me endpoint', async () => {
    httpJsonMock.mockResolvedValueOnce({ id: 'user-3' });

    const { wrapper } = createWrapper();
    renderHook(() => useUserSafe(), { wrapper });

    await waitFor(() => expect(withApiBaseMock).toHaveBeenCalledWith('/api/v1/auth/me'));
  });
});

describe('useIsAuthenticated', () => {
  beforeEach(() => {
    httpJsonMock.mockReset();
  });

  it('returns true when a user is present', async () => {
    httpJsonMock.mockResolvedValueOnce({ id: 'user-4' });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useIsAuthenticated(), { wrapper });

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));
  });

  it('returns false when the user is null', async () => {
    httpJsonMock.mockResolvedValueOnce(null);

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useIsAuthenticated(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isAuthenticated).toBe(false);
  });

  it('returns false when an error occurs', async () => {
    httpJsonMock.mockRejectedValueOnce({ status: 500 });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useIsAuthenticated(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isAuthenticated).toBe(false);
  });
});
