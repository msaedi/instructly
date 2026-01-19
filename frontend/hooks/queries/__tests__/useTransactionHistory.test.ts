/**
 * @jest-environment jsdom
 */
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import type { Transaction } from '@/features/shared/api/types';

// Mock paymentService
const mockGetTransactionHistory = jest.fn();
jest.mock('@/services/api/payments', () => ({
  paymentService: {
    getTransactionHistory: (...args: unknown[]) => mockGetTransactionHistory(...args),
  },
}));

// Mock CACHE_TIMES
jest.mock('@/lib/react-query/queryClient', () => ({
  CACHE_TIMES: {
    FREQUENT: 5 * 60 * 1000, // 5 minutes
  },
}));

import {
  useTransactionHistory,
  useInvalidateTransactionHistory,
  TRANSACTION_HISTORY_QUERY_KEY,
} from '../useTransactionHistory';

// Create wrapper for testing
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

// Mock transaction data
const mockTransactions: Transaction[] = [
  {
    id: '01K2GY3VEVJWKZDVH5HMNXEVRD',
    booking_id: '01K2GY3VEVJWKZDVH5HMNXE001',
    booking_date: '2024-01-15',
    start_time: '10:00',
    end_time: '11:00',
    duration_minutes: 60,
    created_at: '2024-01-15T10:00:00Z',
    status: 'completed',
    instructor_name: 'John D.',
    service_name: 'Guitar Lesson',
    hourly_rate: 50,
    lesson_amount: 50,
    service_fee: 5,
    credit_applied: 0,
    tip_amount: 5,
    tip_paid: 5,
    tip_status: null,
    total_paid: 60,
  },
  {
    id: '01K2GY3VEVJWKZDVH5HMNXEVRE',
    booking_id: '01K2GY3VEVJWKZDVH5HMNXE002',
    booking_date: '2024-01-14',
    start_time: '09:00',
    end_time: '10:00',
    duration_minutes: 60,
    created_at: '2024-01-14T09:00:00Z',
    status: 'completed',
    instructor_name: 'Jane S.',
    service_name: 'Piano Lesson',
    hourly_rate: 40,
    lesson_amount: 40,
    service_fee: 4,
    credit_applied: 10,
    tip_amount: 0,
    tip_paid: 0,
    tip_status: null,
    total_paid: 34,
  },
];

describe('useTransactionHistory', () => {
  beforeEach(() => {
    mockGetTransactionHistory.mockReset();
    mockGetTransactionHistory.mockResolvedValue(mockTransactions);
  });

  it('exports the query key constant', () => {
    expect(TRANSACTION_HISTORY_QUERY_KEY).toEqual(['payments', 'transactions']);
  });

  it('fetches transaction history with default params', async () => {
    const { result } = renderHook(() => useTransactionHistory(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockGetTransactionHistory).toHaveBeenCalledWith(20, 0);
    expect(result.current.data).toEqual(mockTransactions);
  });

  it('fetches transaction history with custom limit and offset', async () => {
    const { result } = renderHook(() => useTransactionHistory(10, 5), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockGetTransactionHistory).toHaveBeenCalledWith(10, 5);
  });

  it('handles loading state', () => {
    // Make the mock return a pending promise
    mockGetTransactionHistory.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useTransactionHistory(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it('handles error state', async () => {
    const error = new Error('Failed to fetch transactions');
    mockGetTransactionHistory.mockRejectedValue(error);

    const { result } = renderHook(() => useTransactionHistory(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error).toBe(error);
  });

  it('returns empty array when API returns empty', async () => {
    mockGetTransactionHistory.mockResolvedValue([]);

    const { result } = renderHook(() => useTransactionHistory(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual([]);
  });
});

describe('useInvalidateTransactionHistory', () => {
  it('returns a function that invalidates the cache', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    // Pre-populate cache
    queryClient.setQueryData([...TRANSACTION_HISTORY_QUERY_KEY, { limit: 20, offset: 0 }], mockTransactions);

    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: queryClient }, children);

    const { result } = renderHook(() => useInvalidateTransactionHistory(), { wrapper });

    // The hook returns an invalidation function
    expect(typeof result.current).toBe('function');

    // Call the invalidation function
    result.current();

    // After invalidation, the query should be stale (invalidated)
    await waitFor(() => {
      const state = queryClient.getQueryState([...TRANSACTION_HISTORY_QUERY_KEY, { limit: 20, offset: 0 }]);
      expect(state?.isInvalidated).toBe(true);
    });
  });
});

describe('useTransactionHistory query key', () => {
  it('uses different cache entries for different params', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: queryClient }, children);

    // First query with default params
    const { result: result1 } = renderHook(() => useTransactionHistory(20, 0), { wrapper });
    await waitFor(() => expect(result1.current.isSuccess).toBe(true));

    // Second query with different params
    mockGetTransactionHistory.mockResolvedValue([mockTransactions[0]!]);
    const { result: result2 } = renderHook(() => useTransactionHistory(10, 10), { wrapper });
    await waitFor(() => expect(result2.current.isSuccess).toBe(true));

    // Should have made two separate API calls
    expect(mockGetTransactionHistory).toHaveBeenCalledTimes(2);
    expect(mockGetTransactionHistory).toHaveBeenNthCalledWith(1, 20, 0);
    expect(mockGetTransactionHistory).toHaveBeenNthCalledWith(2, 10, 10);
  });
});
