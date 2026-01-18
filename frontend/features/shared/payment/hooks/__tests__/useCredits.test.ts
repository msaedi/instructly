/**
 * @jest-environment jsdom
 */
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

// Store the mock function reference
const mockGetCreditBalance = jest.fn();

// Mock paymentService
jest.mock('@/services/api/payments', () => {
  return {
    __esModule: true,
    paymentService: {
      getCreditBalance: (...args: unknown[]) => mockGetCreditBalance(...args),
    },
  };
});

// Mock queryKeys and CACHE_TIMES
jest.mock('@/lib/react-query/queryClient', () => ({
  queryKeys: {
    payments: {
      credits: ['payments', 'credits'],
    },
  },
  CACHE_TIMES: {
    FREQUENT: 5 * 60 * 1000, // 5 minutes
  },
}));

// Mock logger
const mockLoggerDebug = jest.fn();
const mockLoggerError = jest.fn();
jest.mock('@/lib/logger', () => ({
  logger: {
    debug: (...args: unknown[]) => mockLoggerDebug(...args),
    error: (...args: unknown[]) => mockLoggerError(...args),
  },
}));

import { useCredits, type CreditBalance } from '../useCredits';

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

describe('useCredits', () => {
  const mockBalance: CreditBalance = {
    available: 2000, // $20.00
    expires_at: '2024-06-15T00:00:00Z',
    pending: 500, // $5.00
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockGetCreditBalance.mockResolvedValue(mockBalance);
  });

  it('fetches credit balance successfully', async () => {
    const { result } = renderHook(() => useCredits(), {
      wrapper: createWrapper(),
    });

    // Wait for data to be fetched (not just isSuccess)
    await waitFor(() => expect(result.current.data?.available).toBe(mockBalance.available));

    expect(result.current.data).toEqual(mockBalance);
    expect(mockGetCreditBalance).toHaveBeenCalled();
  });

  it('has fetching state while loading', () => {
    mockGetCreditBalance.mockReturnValue(new Promise(() => {})); // Never resolves

    const { result } = renderHook(() => useCredits(), {
      wrapper: createWrapper(),
    });

    // With placeholderData, isLoading is false but isFetching is true
    expect(result.current.isFetching).toBe(true);
    // Placeholder data is available immediately
    expect(result.current.data).toEqual({
      available: 0,
      expires_at: null,
      pending: 0,
    });
  });

  it('provides placeholder data on error', async () => {
    mockGetCreditBalance.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useCredits(), {
      wrapper: createWrapper(),
    });

    // Placeholder data should be available immediately
    expect(result.current.data).toEqual({
      available: 0,
      expires_at: null,
      pending: 0,
    });
  });

  it('logs debug message on successful fetch', async () => {
    const { result } = renderHook(() => useCredits(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockLoggerDebug).toHaveBeenCalledWith(
      'Credits fetched via useCredits hook',
      { available: mockBalance.available }
    );
  });

  it('logs error on failed fetch', async () => {
    const error = new Error('Failed to fetch');
    mockGetCreditBalance.mockRejectedValueOnce(error);

    renderHook(() => useCredits(), {
      wrapper: createWrapper(),
    });

    // Wait for the error to be logged
    await waitFor(() => {
      expect(mockLoggerError).toHaveBeenCalled();
    });

    expect(mockLoggerError).toHaveBeenCalledWith(
      'Failed to fetch credit balance',
      error
    );
  });

  it('returns zero balance when no credits', async () => {
    const emptyBalance: CreditBalance = {
      available: 0,
      expires_at: null,
      pending: 0,
    };
    mockGetCreditBalance.mockResolvedValue(emptyBalance);

    const { result } = renderHook(() => useCredits(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.available).toBe(0);
  });

  it('handles null expires_at', async () => {
    const balanceNoExpiry: CreditBalance = {
      available: 1000,
      expires_at: null,
      pending: 0,
    };
    mockGetCreditBalance.mockResolvedValue(balanceNoExpiry);

    const { result } = renderHook(() => useCredits(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.expires_at).toBeNull();
  });
});
