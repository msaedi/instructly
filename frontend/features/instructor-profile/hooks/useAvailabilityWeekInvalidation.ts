import { useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/react-query/queryClient';

/**
 * Returns a callback that invalidates the instructor's weekly availability snapshot.
 * Keeps the dashboard snapshot in sync after edits in the availability editor.
 */
export function useAvailabilityWeekInvalidation(instructorId?: string, weekStart?: string | null) {
  const queryClient = useQueryClient();

  return useCallback(async () => {
    if (!instructorId || !weekStart) return;
    await queryClient.invalidateQueries({
      queryKey: queryKeys.availability.week(instructorId, weekStart),
    });
  }, [instructorId, queryClient, weekStart]);
}
