/**
 * @jest-environment jsdom
 */
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import type { InstructorRatingsResponse, SearchRatingResponse } from '@/services/api/reviews';

const mockGetInstructorRatings = jest.fn();
const mockGetSearchRating = jest.fn();

jest.mock('@/services/api/reviews', () => ({
  reviewsApi: {
    getInstructorRatings: (...args: unknown[]) => mockGetInstructorRatings(...args),
    getSearchRating: (...args: unknown[]) => mockGetSearchRating(...args),
  },
}));

jest.mock('@/lib/react-query/queryClient', () => ({
  CACHE_TIMES: {
    SLOW: 10 * 60 * 1000,
  },
}));

import { useInstructorRatingsQuery, useSearchRatingQuery } from '../useRatings';

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

describe('useInstructorRatingsQuery', () => {
  beforeEach(() => {
    mockGetInstructorRatings.mockReset();
    mockGetInstructorRatings.mockResolvedValue({} as InstructorRatingsResponse);
  });

  it('fetches ratings when instructorId is provided', async () => {
    const { result } = renderHook(() => useInstructorRatingsQuery('inst-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetInstructorRatings).toHaveBeenCalledWith('inst-1');
  });

  it('does not fetch when instructorId is missing', async () => {
    renderHook(() => useInstructorRatingsQuery(''), { wrapper: createWrapper() });

    await waitFor(() => expect(mockGetInstructorRatings).not.toHaveBeenCalled());
  });
});

describe('useSearchRatingQuery', () => {
  beforeEach(() => {
    mockGetSearchRating.mockReset();
    mockGetSearchRating.mockResolvedValue({} as SearchRatingResponse);
  });

  it('fetches search ratings without a service id', async () => {
    const { result } = renderHook(() => useSearchRatingQuery('inst-2'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetSearchRating).toHaveBeenCalledWith('inst-2', undefined);
  });

  it('fetches search ratings for a specific service', async () => {
    const { result } = renderHook(() => useSearchRatingQuery('inst-2', 'svc-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetSearchRating).toHaveBeenCalledWith('inst-2', 'svc-1');
  });
});
