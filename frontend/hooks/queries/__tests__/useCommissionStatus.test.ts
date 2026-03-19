/**
 * @jest-environment jsdom
 */
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

const mockFetchInstructorCommissionStatus = jest.fn();

jest.mock('@/src/api/services/instructors', () => ({
  fetchInstructorCommissionStatus: (...args: unknown[]) =>
    mockFetchInstructorCommissionStatus(...args),
}));

import { useCommissionStatus } from '../useCommissionStatus';

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

describe('useCommissionStatus', () => {
  beforeEach(() => {
    mockFetchInstructorCommissionStatus.mockReset();
    mockFetchInstructorCommissionStatus.mockResolvedValue({
      is_founding: false,
      tier_name: 'entry',
      commission_rate_pct: 15,
      completed_lessons_30d: 3,
      next_tier_name: 'growth',
      next_tier_threshold: 5,
      lessons_to_next_tier: 2,
      tiers: [],
    });
  });

  it('fetches commission status when enabled by default', async () => {
    const { result } = renderHook(() => useCommissionStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockFetchInstructorCommissionStatus).toHaveBeenCalledTimes(1);
    expect(result.current.data).toEqual(
      expect.objectContaining({
        tier_name: 'entry',
        commission_rate_pct: 15,
        lessons_to_next_tier: 2,
      })
    );
  });

  it('skips fetching when disabled', async () => {
    const { result } = renderHook(() => useCommissionStatus(false), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.fetchStatus).toBe('idle'));

    expect(mockFetchInstructorCommissionStatus).not.toHaveBeenCalled();
  });
});
