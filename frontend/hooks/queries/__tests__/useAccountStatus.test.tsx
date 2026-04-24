import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import {
  accountStatusQueryKey,
  useAccountStatus,
  useInvalidateAccountStatus,
  useReactivateAccount,
  useSuspendAccount,
} from '../useAccountStatus';
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

const makeBrokenJsonResponse = (): Response =>
  ({
    ok: false,
    json: jest.fn().mockRejectedValue(new Error('invalid json')),
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

const activeAccountStatus = {
  user_id: 'user-1',
  role: 'instructor',
  account_status: 'active',
  can_login: true,
  can_receive_bookings: true,
  is_active: true,
  is_suspended: false,
  is_deactivated: false,
};

const suspendedResponse = {
  success: true,
  message: 'Account suspended successfully',
  previous_status: 'active',
  new_status: 'suspended',
};

const resumedResponse = {
  success: true,
  message: 'Account reactivated successfully',
  previous_status: 'suspended',
  new_status: 'active',
};

describe('useAccountStatus', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('returns account status data on success', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeJsonResponse(activeAccountStatus, true));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAccountStatus(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/account/status');
    expect(result.current.data).toEqual(activeAccountStatus);
  });

  it('does not fetch while disabled', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAccountStatus(false), { wrapper });

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchWithAuthMock).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('surfaces API detail when status fetch fails', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(
      makeJsonResponse({ detail: 'Account status is unavailable' }, false)
    );

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAccountStatus(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error?.message).toBe('Account status is unavailable');
  });
});

describe('useInvalidateAccountStatus', () => {
  it('invalidates the account status query', async () => {
    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(accountStatusQueryKey, activeAccountStatus);
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useInvalidateAccountStatus(), { wrapper });

    await act(async () => {
      await result.current();
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: accountStatusQueryKey });
    expect(queryClient.getQueryState(accountStatusQueryKey)?.isInvalidated).toBe(true);
  });
});

describe('account lifecycle mutations', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('suspends the account with the expected endpoint', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeJsonResponse(suspendedResponse, true));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useSuspendAccount(), { wrapper });

    await act(async () => {
      await expect(result.current.mutateAsync()).resolves.toEqual(suspendedResponse);
    });

    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/account/suspend', {
      method: 'POST',
    });
  });

  it('uses the pause fallback when an error response has invalid JSON', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeBrokenJsonResponse());

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useSuspendAccount(), { wrapper });

    await act(async () => {
      await expect(result.current.mutateAsync()).rejects.toThrow('Failed to pause account.');
    });
  });

  it('reactivates the account with the expected endpoint', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeJsonResponse(resumedResponse, true));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useReactivateAccount(), { wrapper });

    await act(async () => {
      await expect(result.current.mutateAsync()).resolves.toEqual(resumedResponse);
    });

    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/account/reactivate', {
      method: 'POST',
    });
  });

  it('surfaces API detail when resume fails', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(
      makeJsonResponse({ detail: 'Account is already active' }, false)
    );

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useReactivateAccount(), { wrapper });

    await act(async () => {
      await expect(result.current.mutateAsync()).rejects.toThrow('Account is already active');
    });
  });
});
