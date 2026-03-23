import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import {
  trustedDevicesQueryKey,
  useInvalidateTrustedDevices,
  useRevokeAllTrustedDevices,
  useRevokeTrustedDevice,
  useTrustedDevices,
} from '../useTrustedDevices';
import { fetchWithAuth } from '@/lib/api';

jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(),
}));

const fetchWithAuthMock = fetchWithAuth as jest.MockedFunction<typeof fetchWithAuth>;

const makeJsonResponse = (body: unknown, ok: boolean): Response =>
  ({
    ok,
    json: jest.fn().mockResolvedValue(body),
  }) as unknown as Response;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return { wrapper, queryClient };
};

describe('useTrustedDevices', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('returns trusted devices on success', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(
      makeJsonResponse(
        {
          items: [
            {
              id: 'device-1',
              device_name: 'Chrome on macOS',
              created_at: '2026-03-01T00:00:00Z',
              last_used_at: '2026-03-10T00:00:00Z',
              expires_at: '2026-03-31T00:00:00Z',
            },
          ],
        },
        true
      )
    );

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useTrustedDevices(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual({
      items: [
        {
          id: 'device-1',
          device_name: 'Chrome on macOS',
          created_at: '2026-03-01T00:00:00Z',
          last_used_at: '2026-03-10T00:00:00Z',
          expires_at: '2026-03-31T00:00:00Z',
        },
      ],
    });
    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/2fa/trusted-devices');
  });

  it('reports an error when the request fails', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeJsonResponse({}, false));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useTrustedDevices(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Failed to fetch trusted devices');
  });

  it('does not fetch when disabled', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useTrustedDevices(false), { wrapper });

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchWithAuthMock).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useInvalidateTrustedDevices', () => {
  it('invalidates the trusted devices query', async () => {
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useInvalidateTrustedDevices(), { wrapper });

    await act(async () => {
      await result.current();
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: trustedDevicesQueryKey });
  });
});

describe('trusted device revoke mutations', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('revokes one trusted device and invalidates the list', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(
      makeJsonResponse({ message: 'Trusted device revoked' }, true)
    );

    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries').mockResolvedValue();
    const { result } = renderHook(() => useRevokeTrustedDevice(), { wrapper });

    await act(async () => {
      await expect(result.current.mutateAsync('device-1')).resolves.toEqual({
        message: 'Trusted device revoked',
      });
    });

    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/2fa/trusted-devices/device-1', {
      method: 'DELETE',
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: trustedDevicesQueryKey });
  });

  it('surfaces an error when single-device revoke fails', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeJsonResponse({}, false));

    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderHook(() => useRevokeTrustedDevice(), { wrapper });

    await act(async () => {
      await expect(result.current.mutateAsync('device-1')).rejects.toThrow(
        'Failed to revoke trusted device'
      );
    });

    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('revokes all trusted devices and invalidates the list', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(
      makeJsonResponse({ message: 'All trusted devices revoked' }, true)
    );

    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries').mockResolvedValue();
    const { result } = renderHook(() => useRevokeAllTrustedDevices(), { wrapper });

    await act(async () => {
      await expect(result.current.mutateAsync()).resolves.toEqual({
        message: 'All trusted devices revoked',
      });
    });

    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/2fa/trusted-devices', {
      method: 'DELETE',
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: trustedDevicesQueryKey });
  });

  it('surfaces an error when revoke-all fails', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeJsonResponse({}, false));

    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderHook(() => useRevokeAllTrustedDevices(), { wrapper });

    await act(async () => {
      await expect(result.current.mutateAsync()).rejects.toThrow(
        'Failed to revoke trusted devices'
      );
    });

    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
