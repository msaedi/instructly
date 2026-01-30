/**
 * @jest-environment jsdom
 */
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

// Store mock functions
const mockGetRatingsBatch = jest.fn();
const mockGetExistingForBookings = jest.fn();

// Mock reviewsApi
jest.mock('@/services/api/reviews', () => ({
  reviewsApi: {
    getRatingsBatch: (...args: unknown[]) => mockGetRatingsBatch(...args),
    getExistingForBookings: (...args: unknown[]) => mockGetExistingForBookings(...args),
  },
}));

// Mock CACHE_TIMES
jest.mock('@/lib/react-query/queryClient', () => ({
  CACHE_TIMES: {
    FREQUENT: 5 * 60 * 1000,
  },
}));

import { useRatingsBatch, useExistingReviews } from '../useReviewsBatch';

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

describe('useRatingsBatch', () => {
  const mockRatingsResponse = {
    results: [
      { instructor_id: 'inst-1', rating: 4.5, review_count: 10 },
      { instructor_id: 'inst-2', rating: 4.8, review_count: 25 },
      { instructor_id: 'inst-3', rating: null, review_count: 0 },
    ],
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockGetRatingsBatch.mockResolvedValue(mockRatingsResponse);
  });

  it('fetches ratings for multiple instructors successfully', async () => {
    const instructorIds = ['inst-1', 'inst-2', 'inst-3'];

    const { result } = renderHook(() => useRatingsBatch(instructorIds), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // Verify map structure (covers lines 46-48)
    expect(result.current.data).toEqual({
      'inst-1': { rating: 4.5, review_count: 10 },
      'inst-2': { rating: 4.8, review_count: 25 },
      'inst-3': { rating: null, review_count: 0 },
    });

    expect(mockGetRatingsBatch).toHaveBeenCalledWith(['inst-1', 'inst-2', 'inst-3']);
  });

  it('returns empty map for empty instructor list', () => {
    const { result } = renderHook(() => useRatingsBatch([]), {
      wrapper: createWrapper(),
    });

    // Query is disabled when empty array, so isFetching should be false immediately
    expect(result.current.isFetching).toBe(false);

    // No API call should be made
    expect(mockGetRatingsBatch).not.toHaveBeenCalled();

    // Data should be undefined when query is disabled
    expect(result.current.data).toBeUndefined();
  });

  it('sorts instructor IDs for consistent query keys', async () => {
    mockGetRatingsBatch.mockResolvedValue({
      results: [
        { instructor_id: 'zzz', rating: 4.0, review_count: 5 },
        { instructor_id: 'aaa', rating: 3.5, review_count: 2 },
      ],
    });

    // Pass unsorted IDs
    const { result } = renderHook(() => useRatingsBatch(['zzz', 'aaa']), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // API should receive sorted IDs
    expect(mockGetRatingsBatch).toHaveBeenCalledWith(['aaa', 'zzz']);
  });

  it('respects enabled flag when false', async () => {
    const { result } = renderHook(() => useRatingsBatch(['inst-1'], false), {
      wrapper: createWrapper(),
    });

    // Query should not run
    expect(result.current.isFetching).toBe(false);
    expect(mockGetRatingsBatch).not.toHaveBeenCalled();
  });

  it('handles API error gracefully', async () => {
    const error = new Error('Network error');
    mockGetRatingsBatch.mockRejectedValue(error);

    const { result } = renderHook(() => useRatingsBatch(['inst-1']), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error).toBe(error);
  });

  it('handles null ratings correctly', async () => {
    mockGetRatingsBatch.mockResolvedValue({
      results: [
        { instructor_id: 'new-inst', rating: null, review_count: 0 },
      ],
    });

    const { result } = renderHook(() => useRatingsBatch(['new-inst']), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.['new-inst']?.rating).toBeNull();
    expect(result.current.data?.['new-inst']?.review_count).toBe(0);
  });

  it('handles single instructor ID', async () => {
    mockGetRatingsBatch.mockResolvedValue({
      results: [{ instructor_id: 'solo', rating: 5.0, review_count: 1 }],
    });

    const { result } = renderHook(() => useRatingsBatch(['solo']), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual({
      solo: { rating: 5.0, review_count: 1 },
    });
  });
});

describe('useExistingReviews', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('fetches existing reviews for bookings successfully', async () => {
    const reviewedBookingIds = ['booking-1', 'booking-3'];
    mockGetExistingForBookings.mockResolvedValue(reviewedBookingIds);

    const bookingIds = ['booking-1', 'booking-2', 'booking-3'];
    const { result } = renderHook(() => useExistingReviews(bookingIds), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // Verify result structure (covers lines 80-82)
    expect(result.current.data?.reviewedIds).toEqual(reviewedBookingIds);
    expect(result.current.data?.reviewedMap).toEqual({
      'booking-1': true,
      'booking-3': true,
    });

    // booking-2 should not be in the map
    expect(result.current.data?.reviewedMap['booking-2']).toBeUndefined();
  });

  it('returns empty result for empty booking list', () => {
    const { result } = renderHook(() => useExistingReviews([]), {
      wrapper: createWrapper(),
    });

    // Query is disabled when empty array, so isFetching should be false immediately
    expect(result.current.isFetching).toBe(false);

    // No API call should be made
    expect(mockGetExistingForBookings).not.toHaveBeenCalled();

    // Data should be undefined when query is disabled
    expect(result.current.data).toBeUndefined();
  });

  it('handles no reviews exist case', async () => {
    mockGetExistingForBookings.mockResolvedValue([]);

    const { result } = renderHook(() => useExistingReviews(['booking-1', 'booking-2']), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.reviewedIds).toEqual([]);
    expect(result.current.data?.reviewedMap).toEqual({});
  });

  it('sorts booking IDs for consistent query keys', async () => {
    mockGetExistingForBookings.mockResolvedValue(['zzz']);

    const { result } = renderHook(() => useExistingReviews(['zzz', 'aaa']), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // API should receive sorted IDs
    expect(mockGetExistingForBookings).toHaveBeenCalledWith(['aaa', 'zzz']);
  });

  it('respects enabled flag when false', async () => {
    const { result } = renderHook(() => useExistingReviews(['booking-1'], false), {
      wrapper: createWrapper(),
    });

    expect(result.current.isFetching).toBe(false);
    expect(mockGetExistingForBookings).not.toHaveBeenCalled();
  });

  it('handles API error gracefully', async () => {
    const error = new Error('Server error');
    mockGetExistingForBookings.mockRejectedValue(error);

    const { result } = renderHook(() => useExistingReviews(['booking-1']), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error).toBe(error);
  });

  it('allows O(1) lookup via reviewedMap', async () => {
    mockGetExistingForBookings.mockResolvedValue(['b1', 'b2', 'b3']);

    const { result } = renderHook(
      () => useExistingReviews(['b1', 'b2', 'b3', 'b4', 'b5']),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // O(1) lookups
    expect(result.current.data?.reviewedMap['b1']).toBe(true);
    expect(result.current.data?.reviewedMap['b2']).toBe(true);
    expect(result.current.data?.reviewedMap['b3']).toBe(true);
    expect(result.current.data?.reviewedMap['b4']).toBeUndefined();
    expect(result.current.data?.reviewedMap['b5']).toBeUndefined();
  });
});
