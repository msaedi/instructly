/**
 * @jest-environment jsdom
 */
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import type { EarningsResponse, PayoutHistoryResponse } from '@/features/shared/api/types';

const mockGetEarnings = jest.fn();
const mockGetPayouts = jest.fn();

jest.mock('@/services/api/payments', () => ({
  paymentService: {
    getEarnings: (...args: unknown[]) => mockGetEarnings(...args),
    getPayouts: (...args: unknown[]) => mockGetPayouts(...args),
  },
}));

jest.mock('@/lib/react-query/queryClient', () => ({
  CACHE_TIMES: {
    FREQUENT: 5 * 60 * 1000,
  },
}));

import { useInstructorEarnings } from '../useInstructorEarnings';
import { useInstructorPayouts } from '../useInstructorPayouts';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

describe('useInstructorEarnings', () => {
  beforeEach(() => {
    mockGetEarnings.mockReset();
    mockGetEarnings.mockResolvedValue({} as EarningsResponse);
  });

  it('fetches earnings when enabled by default', async () => {
    const { result } = renderHook(() => useInstructorEarnings(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetEarnings).toHaveBeenCalledTimes(1);
  });

  it('skips fetching when disabled', async () => {
    renderHook(() => useInstructorEarnings(false), { wrapper: createWrapper() });

    await waitFor(() => expect(mockGetEarnings).not.toHaveBeenCalled());
  });
});

describe('useInstructorPayouts', () => {
  beforeEach(() => {
    mockGetPayouts.mockReset();
    mockGetPayouts.mockResolvedValue({} as PayoutHistoryResponse);
  });

  it('fetches payouts when enabled by default', async () => {
    const { result } = renderHook(() => useInstructorPayouts(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetPayouts).toHaveBeenCalledTimes(1);
  });

  it('skips fetching when disabled', async () => {
    renderHook(() => useInstructorPayouts(false), { wrapper: createWrapper() });

    await waitFor(() => expect(mockGetPayouts).not.toHaveBeenCalled());
  });
});
