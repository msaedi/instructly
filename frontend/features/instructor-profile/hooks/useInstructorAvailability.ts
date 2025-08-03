import { useQuery } from '@tanstack/react-query';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { publicApi } from '@/features/shared/api/client';
import { format, addDays } from 'date-fns';
import { logger } from '@/lib/logger';

interface AvailabilityResponse {
  instructor_id: number;
  instructor_name: string;
  availability_by_date: Record<
    string,
    {
      date: string;
      available_slots: Array<{
        start_time: string;
        end_time: string;
      }>;
      is_blackout: boolean;
    }
  >;
  timezone: string;
  total_available_slots: number;
  earliest_available_date: string;
}

/**
 * Hook to fetch instructor availability for the week
 * Uses 5-minute cache as availability changes frequently
 */
export function useInstructorAvailability(instructorId: string, startDate?: string) {
  // Always use a date - either the provided one or today
  const now = new Date();
  const todayStr = format(now, 'yyyy-MM-dd');

  // If startDate is provided and it's in the past, use today instead
  let actualStartDate = startDate || todayStr;
  if (startDate && new Date(startDate) < new Date(todayStr)) {
    actualStartDate = todayStr;
    logger.debug('Start date was in the past, using today instead', {
      requested: startDate,
      using: actualStartDate
    });
  }

  const endDate = format(addDays(new Date(actualStartDate), 6), 'yyyy-MM-dd');

  logger.debug('useInstructorAvailability called', {
    instructorId,
    startDate: actualStartDate,
    endDate
  });

  return useQuery<AvailabilityResponse>({
    queryKey: queryKeys.availability.week(instructorId, actualStartDate),
    queryFn: async () => {
      logger.info('Fetching availability', { instructorId, start_date: actualStartDate, end_date: endDate });

      const response = await publicApi.getInstructorAvailability(instructorId, {
        start_date: actualStartDate,
        end_date: endDate,
      });

      logger.debug('Availability response received', {
        hasData: !!response.data,
        hasError: !!response.error,
        dataKeys: response.data ? Object.keys(response.data) : null
      });

      if (response.error) {
        logger.error('Availability fetch failed', { error: response.error });
        throw new Error(response.error);
      }

      return response.data!;
    },
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes
    refetchInterval: CACHE_TIMES.FREQUENT, // Background refresh every 5 minutes
    enabled: !!instructorId, // Only need instructorId now, date always has a default
  });
}
