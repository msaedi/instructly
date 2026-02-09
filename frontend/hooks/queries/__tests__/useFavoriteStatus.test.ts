import { renderHook, waitFor, act } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import {
  useFavoriteStatus,
  useInvalidateFavoriteStatus,
  useSetFavoriteStatus,
} from '../useFavoriteStatus';
import { favoritesApi } from '@/services/api/favorites';

jest.mock('@/services/api/favorites', () => ({
  favoritesApi: {
    check: jest.fn(),
  },
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(),
}));

import { useAuth } from '@/features/shared/hooks/useAuth';

const useAuthMock = useAuth as jest.Mock;
const favoritesApiMock = favoritesApi as jest.Mocked<typeof favoritesApi>;

describe('useFavoriteStatus', () => {
  const createWrapper = () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: queryClient }, children);
    return { wrapper, queryClient };
  };

  beforeEach(() => {
    jest.clearAllMocks();
    useAuthMock.mockReturnValue({ user: { id: 'user-1' } });
    favoritesApiMock.check.mockResolvedValue({ is_favorited: false });
  });

  describe('useFavoriteStatus', () => {
    it('fetches favorite status when user is authenticated', async () => {
      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useFavoriteStatus('inst-1'), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(favoritesApiMock.check).toHaveBeenCalledWith('inst-1');
      expect(result.current.data).toBe(false);
    });

    it('returns true when instructor is favorited', async () => {
      favoritesApiMock.check.mockResolvedValue({ is_favorited: true });

      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useFavoriteStatus('inst-1'), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
        expect(result.current.data).toBe(true);
      });
    });

    it('defaults to false when API payload is missing is_favorited', async () => {
      favoritesApiMock.check.mockResolvedValue({} as never);

      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useFavoriteStatus('inst-1'), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toBe(false);
    });

    it('does not fetch when user is not authenticated', async () => {
      useAuthMock.mockReturnValue({ user: null });

      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useFavoriteStatus('inst-1'), { wrapper });

      // Query should not be enabled
      expect(result.current.isLoading).toBe(false);
      expect(result.current.isFetching).toBe(false);
      expect(favoritesApiMock.check).not.toHaveBeenCalled();
    });

    it('does not fetch when instructorId is empty', async () => {
      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useFavoriteStatus(''), { wrapper });

      // Query should not be enabled
      expect(result.current.isLoading).toBe(false);
      expect(result.current.isFetching).toBe(false);
      expect(favoritesApiMock.check).not.toHaveBeenCalled();
    });

    it('uses initialValue when provided', async () => {
      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useFavoriteStatus('inst-1', true), { wrapper });

      // Should have initial data immediately
      expect(result.current.data).toBe(true);
    });

    it('handles API error gracefully', async () => {
      favoritesApiMock.check.mockRejectedValue(new Error('Network error'));

      const { wrapper } = createWrapper();

      const { result } = renderHook(() => useFavoriteStatus('inst-1'), { wrapper });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });
    });
  });

  describe('useInvalidateFavoriteStatus', () => {
    it('invalidates favorite status cache', async () => {
      const { wrapper, queryClient } = createWrapper();

      // First, populate the cache
      const { result: statusResult } = renderHook(
        () => useFavoriteStatus('inst-1'),
        { wrapper }
      );

      await waitFor(() => {
        expect(statusResult.current.isSuccess).toBe(true);
      });

      // Now test invalidation
      const { result: invalidateResult } = renderHook(
        () => useInvalidateFavoriteStatus(),
        { wrapper }
      );

      // Spy on invalidateQueries
      const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

      act(() => {
        invalidateResult.current('inst-1');
      });

      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ['favorites', 'check', 'inst-1'],
      });

      invalidateSpy.mockRestore();
    });
  });

  describe('useSetFavoriteStatus', () => {
    it('updates favorite status optimistically', async () => {
      const { wrapper, queryClient } = createWrapper();

      // First, populate the cache with false
      const { result: statusResult } = renderHook(
        () => useFavoriteStatus('inst-1'),
        { wrapper }
      );

      await waitFor(() => {
        expect(statusResult.current.isSuccess).toBe(true);
        expect(statusResult.current.data).toBe(false);
      });

      // Now test setting
      const { result: setResult } = renderHook(
        () => useSetFavoriteStatus(),
        { wrapper }
      );

      act(() => {
        setResult.current('inst-1', true);
      });

      // Check cache was updated
      const cached = queryClient.getQueryData(['favorites', 'check', 'inst-1']);
      expect(cached).toBe(true);
    });

    it('can set to false', async () => {
      favoritesApiMock.check.mockResolvedValue({ is_favorited: true });

      const { wrapper, queryClient } = createWrapper();

      // First, populate the cache with true
      const { result: statusResult } = renderHook(
        () => useFavoriteStatus('inst-1'),
        { wrapper }
      );

      await waitFor(() => {
        expect(statusResult.current.isSuccess).toBe(true);
        expect(statusResult.current.data).toBe(true);
      });

      // Now test setting to false
      const { result: setResult } = renderHook(
        () => useSetFavoriteStatus(),
        { wrapper }
      );

      act(() => {
        setResult.current('inst-1', false);
      });

      // Check cache was updated
      const cached = queryClient.getQueryData(['favorites', 'check', 'inst-1']);
      expect(cached).toBe(false);
    });
  });
});
