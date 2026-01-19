import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  useUserAddresses,
  useInvalidateUserAddresses,
  userAddressesQueryKey,
} from '../useUserAddresses';
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

describe('useUserAddresses', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('returns data on success', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValue({ items: [{ id: 'addr-1', street_line1: '123 Main' }] }),
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUserAddresses(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(1);
  });

  it('reports error when response is not ok', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: false,
      json: jest.fn(),
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUserAddresses(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Failed to fetch user addresses');
  });

  it('does not run when disabled', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUserAddresses(false), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(fetchWithAuthMock).not.toHaveBeenCalled();
  });
});

describe('useInvalidateUserAddresses', () => {
  it('invalidates the user addresses query', () => {
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useInvalidateUserAddresses(), { wrapper });

    result.current();

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: userAddressesQueryKey });
  });

  it('marks cached data as invalidated', () => {
    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(userAddressesQueryKey, { items: [] });

    const { result } = renderHook(() => useInvalidateUserAddresses(), { wrapper });

    result.current();

    expect(queryClient.getQueryState(userAddressesQueryKey)?.isInvalidated).toBe(true);
  });

  it('can be called multiple times', () => {
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useInvalidateUserAddresses(), { wrapper });

    result.current();
    result.current();

    expect(invalidateSpy).toHaveBeenCalledTimes(2);
  });
});
