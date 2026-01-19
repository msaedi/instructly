import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useStripeConnectStatus, stripeConnectStatusQueryKey } from '../useStripeConnectStatus';
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
  return { wrapper };
};

describe('useStripeConnectStatus', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('returns data on success', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValue({
        has_account: true,
        onboarding_completed: true,
        charges_enabled: true,
        payouts_enabled: true,
        details_submitted: true,
      }),
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useStripeConnectStatus(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.has_account).toBe(true);
  });

  it('reports error when response is not ok', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: false,
      json: jest.fn(),
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useStripeConnectStatus(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Failed to fetch Stripe Connect status');
  });

  it('does not run when disabled', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useStripeConnectStatus(false), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(fetchWithAuthMock).not.toHaveBeenCalled();
  });

  it('exports query key for use with invalidation', () => {
    expect(stripeConnectStatusQueryKey).toEqual(['payments', 'connect', 'status']);
  });
});
