import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  usePaymentMethods,
  useInvalidatePaymentMethods,
  PAYMENT_METHODS_QUERY_KEY,
} from '../usePaymentMethods';
import { paymentService } from '@/services/api/payments';

jest.mock('@/services/api/payments', () => ({
  paymentService: {
    listPaymentMethods: jest.fn(),
  },
}));

const listPaymentMethodsMock = paymentService.listPaymentMethods as jest.Mock;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return { wrapper, queryClient };
};

describe('usePaymentMethods', () => {
  beforeEach(() => {
    listPaymentMethodsMock.mockReset();
  });

  it('returns payment methods on success', async () => {
    listPaymentMethodsMock.mockResolvedValueOnce([
      { id: 'pm_1', last4: '4242', brand: 'visa', is_default: true, created_at: '2024-01-01' },
    ]);

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePaymentMethods(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
  });

  it('reports error when the service fails', async () => {
    listPaymentMethodsMock.mockRejectedValueOnce(new Error('Network error'));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePaymentMethods(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Network error');
  });

  it('handles empty payment method lists', async () => {
    listPaymentMethodsMock.mockResolvedValueOnce([]);

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePaymentMethods(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([]);
  });
});

describe('useInvalidatePaymentMethods', () => {
  it('invalidates the payment methods query', () => {
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useInvalidatePaymentMethods(), { wrapper });

    result.current();

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: PAYMENT_METHODS_QUERY_KEY });
  });

  it('marks cached data as invalidated', () => {
    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(PAYMENT_METHODS_QUERY_KEY, []);

    const { result } = renderHook(() => useInvalidatePaymentMethods(), { wrapper });

    result.current();

    expect(queryClient.getQueryState(PAYMENT_METHODS_QUERY_KEY)?.isInvalidated).toBe(true);
  });

  it('can be called multiple times', () => {
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useInvalidatePaymentMethods(), { wrapper });

    result.current();
    result.current();

    expect(invalidateSpy).toHaveBeenCalledTimes(2);
  });
});
