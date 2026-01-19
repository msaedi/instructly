import React from 'react';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useTfaStatus, useInvalidateTfaStatus, tfaStatusQueryKey } from '../useTfaStatus';
import { fetchWithAuth } from '@/lib/api';

jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(),
}));

const fetchWithAuthMock = fetchWithAuth as jest.Mock;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return { wrapper, queryClient };
};

describe('useTfaStatus', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('returns data on successful fetch', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValue({ enabled: true }),
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useTfaStatus(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ enabled: true });
  });

  it('reports error when response is not ok', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: false,
      json: jest.fn(),
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useTfaStatus(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Failed to fetch 2FA status');
  });

  it('does not run when disabled', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useTfaStatus(false), { wrapper });

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchWithAuthMock).not.toHaveBeenCalled();
    expect(result.current.isLoading).toBe(false);
  });
});

describe('useInvalidateTfaStatus', () => {
  it('invalidates the tfa status query', () => {
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useInvalidateTfaStatus(), { wrapper });

    result.current();

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: tfaStatusQueryKey });
  });

  it('marks cached data as invalidated', () => {
    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(tfaStatusQueryKey, { enabled: false });

    const { result } = renderHook(() => useInvalidateTfaStatus(), { wrapper });

    result.current();

    expect(queryClient.getQueryState(tfaStatusQueryKey)?.isInvalidated).toBe(true);
  });

  it('can be called multiple times', () => {
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useInvalidateTfaStatus(), { wrapper });

    result.current();
    result.current();

    expect(invalidateSpy).toHaveBeenCalledTimes(2);
  });
});
