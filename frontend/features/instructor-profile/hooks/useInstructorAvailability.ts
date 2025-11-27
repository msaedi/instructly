import { useQuery } from '@tanstack/react-query';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { publicApi, type ApiResponse } from '@/features/shared/api/client';
import { format, addDays } from 'date-fns';
import { logger } from '@/lib/logger';

interface AvailabilityResponse {
  instructor_id: string;
  instructor_first_name: string | null;  // Null if public_availability_show_instructor_name=false
  instructor_last_initial: string | null; // Null if public_availability_show_instructor_name=false
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
  const now = new Date();
  const todayIso = format(now, 'yyyy-MM-dd');
  const parsedStartDate = (() => {
    if (!startDate) return todayIso;
    const parsed = new Date(`${startDate}T00:00:00`);
    if (Number.isNaN(parsed.valueOf())) {
      logger.warn('Invalid start date for availability, using today instead', { startDate });
      return todayIso;
    }
    return format(parsed, 'yyyy-MM-dd');
  })();

  const sanitizedStartDate = (() => {
    const parsedProvided = new Date(`${parsedStartDate}T00:00:00`);
    const parsedToday = new Date(`${todayIso}T00:00:00`);
    if (parsedProvided < parsedToday) {
      // Note: This is expected behavior - don't log on every render
      return todayIso;
    }
    return parsedStartDate;
  })();

  const startDateObj = new Date(`${sanitizedStartDate}T00:00:00`);
  const endDate = format(addDays(startDateObj, 6), 'yyyy-MM-dd');

  return useQuery<AvailabilityResponse>({
    queryKey: queryKeys.availability.week(instructorId, sanitizedStartDate),
    queryFn: async () => {
      logger.debug('useInstructorAvailability queryFn executing', {
        instructorId,
        startDate: sanitizedStartDate,
        endDate,
      });
      logger.info('Fetching availability', { instructorId, start_date: sanitizedStartDate, end_date: endDate });

      const response = await publicApi.getInstructorAvailability(instructorId, {
        start_date: sanitizedStartDate,
        end_date: endDate,
      });

      // Handle rate limit: wait Retry-After and retry once
      const rateLimitResponse = response as ApiResponse<unknown> & { retryAfterSeconds?: number };
      if (response.status === 429 && rateLimitResponse.retryAfterSeconds) {
        await new Promise((r) => setTimeout(r, (rateLimitResponse.retryAfterSeconds || 1) * 1000));
        const retry = await publicApi.getInstructorAvailability(instructorId, {
          start_date: sanitizedStartDate,
          end_date: endDate,
        });
        if (retry.error) {
          logger.error('Availability retry failed', { error: retry.error });
          throw new Error(retry.error);
        }
        return retry.data!;
      }

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
    staleTime: CACHE_TIMES.FREQUENT,
    refetchInterval: CACHE_TIMES.FREQUENT,
    enabled: Boolean(instructorId && sanitizedStartDate),
  });
}
