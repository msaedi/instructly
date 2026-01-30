/**
 * @jest-environment jsdom
 */
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

// Store mock function
const mockGetStudentBadges = jest.fn();

// Mock badgesApi
jest.mock('@/services/api/badges', () => ({
  badgesApi: {
    getStudentBadges: (...args: unknown[]) => mockGetStudentBadges(...args),
  },
}));

// Mock queryKeys and CACHE_TIMES
jest.mock('@/lib/react-query/queryClient', () => ({
  queryKeys: {
    badges: {
      student: ['badges', 'student'],
    },
  },
  CACHE_TIMES: {
    FREQUENT: 5 * 60 * 1000,
  },
}));

import { useStudentBadges } from '../useStudentBadges';
import type { StudentBadgeItem } from '@/types/badges';

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

describe('useStudentBadges', () => {
  // Mock data matching StudentBadgeView schema
  const mockBadges: StudentBadgeItem[] = [
    {
      name: 'First Lesson',
      slug: 'first-lesson',
      earned: true,
      description: 'Complete your first lesson',
      awarded_at: '2024-01-15T00:00:00Z',
      confirmed_at: '2024-01-15T00:00:00Z',
      progress: { current: 1, goal: 1, percent: 100 },
      status: 'confirmed',
    },
    {
      name: 'Five Lessons',
      slug: 'five-lessons',
      earned: false,
      description: 'Complete five lessons',
      awarded_at: null,
      confirmed_at: null,
      progress: { current: 2, goal: 5, percent: 40 },
      status: 'in_progress',
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    mockGetStudentBadges.mockResolvedValue(mockBadges);
  });

  it('fetches student badges successfully', async () => {
    const { result } = renderHook(() => useStudentBadges(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(mockBadges);
    expect(mockGetStudentBadges).toHaveBeenCalledTimes(1);
  });

  it('returns empty array when user has no badges', async () => {
    mockGetStudentBadges.mockResolvedValue([]);

    const { result } = renderHook(() => useStudentBadges(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual([]);
    expect(result.current.data?.length).toBe(0);
  });

  it('handles API error gracefully', async () => {
    const error = new Error('Failed to fetch badges');
    mockGetStudentBadges.mockRejectedValue(error);

    const { result } = renderHook(() => useStudentBadges(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error).toBe(error);
    expect(result.current.data).toBeUndefined();
  });

  it('handles 401 unauthorized error', async () => {
    const error = Object.assign(new Error('Unauthorized'), { status: 401 });
    mockGetStudentBadges.mockRejectedValue(error);

    const { result } = renderHook(() => useStudentBadges(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error?.message).toBe('Unauthorized');
  });

  it('shows loading state initially', () => {
    mockGetStudentBadges.mockReturnValue(new Promise(() => {})); // Never resolves

    const { result } = renderHook(() => useStudentBadges(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it('returns correct query key for cache invalidation', async () => {
    const { result } = renderHook(() => useStudentBadges(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // Check that refetch works (indicating query key is properly set up)
    await result.current.refetch();
    expect(mockGetStudentBadges).toHaveBeenCalledTimes(2);
  });

  it('returns badges with mixed earned and in-progress states', async () => {
    const mixedBadges: StudentBadgeItem[] = [
      {
        name: 'Earned Badge',
        slug: 'earned-badge',
        earned: true,
        description: 'Already earned',
        awarded_at: '2024-01-15T00:00:00Z',
        confirmed_at: '2024-01-15T00:00:00Z',
        progress: { current: 1, goal: 1, percent: 100 },
        status: 'confirmed',
      },
      {
        name: 'In Progress Badge',
        slug: 'in-progress-badge',
        earned: false,
        description: 'Still working on it',
        awarded_at: null,
        confirmed_at: null,
        progress: { current: 3, goal: 10, percent: 30 },
        status: 'in_progress',
      },
    ];
    mockGetStudentBadges.mockResolvedValue(mixedBadges);

    const { result } = renderHook(() => useStudentBadges(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.[0]?.earned).toBe(true);
    expect(result.current.data?.[0]?.awarded_at).toBeTruthy();
    expect(result.current.data?.[1]?.earned).toBe(false);
    expect(result.current.data?.[1]?.awarded_at).toBeNull();
  });
});
