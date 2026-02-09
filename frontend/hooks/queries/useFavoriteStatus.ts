/**
 * React Query hook for checking favorite status
 *
 * Provides cached access to favorite status for an instructor.
 * This replaces direct favoritesApi.check calls to prevent duplicate API calls.
 *
 * @example
 * ```tsx
 * function InstructorCard({ instructorId }: { instructorId: string }) {
 *   const { data: isFavorited } = useFavoriteStatus(instructorId);
 *
 *   return <Heart filled={isFavorited} />;
 * }
 * ```
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { favoritesApi } from '@/services/api/favorites';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';
import { useAuth } from '@/features/shared/hooks/useAuth';

/**
 * Hook to check if an instructor is favorited
 *
 * @param instructorId - ULID of the instructor to check
 * @param initialValue - Optional initial value (e.g., from server-rendered data)
 * @returns React Query result with boolean favorite status
 */
export function useFavoriteStatus(instructorId: string, initialValue?: boolean) {
  const { user } = useAuth();
  const isAuthenticated = !!user;

  return useQuery({
    queryKey: ['favorites', 'check', instructorId],
    queryFn: async () => {
      const res = await favoritesApi.check(instructorId);
      // React Query query functions must never resolve `undefined`.
      // If the API returns an unexpected payload (for example an auth/problem body),
      // default to `false` instead of bubbling an undefined value into the cache.
      return typeof res?.is_favorited === 'boolean' ? res.is_favorited : false;
    },
    enabled: isAuthenticated && !!instructorId,
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes
    refetchOnWindowFocus: false,
    initialData: initialValue,
  });
}

/**
 * Hook to invalidate favorite status cache for an instructor
 * Use this after adding/removing a favorite
 */
export function useInvalidateFavoriteStatus() {
  const queryClient = useQueryClient();
  return (instructorId: string) =>
    queryClient.invalidateQueries({ queryKey: ['favorites', 'check', instructorId] });
}

/**
 * Hook to update favorite status optimistically
 * Use this when toggling favorites for instant UI feedback
 */
export function useSetFavoriteStatus() {
  const queryClient = useQueryClient();
  return (instructorId: string, isFavorited: boolean) => {
    queryClient.setQueryData(['favorites', 'check', instructorId], isFavorited);
  };
}
