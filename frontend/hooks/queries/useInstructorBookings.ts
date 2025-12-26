/**
 * Hook for instructor bookings
 *
 * ✅ MIGRATED TO V1 - Uses /api/v1/instructor-bookings endpoints
 *
 * Provides a unified interface for fetching instructor bookings with various filters.
 * Routes to the appropriate v1 endpoint based on status and upcoming parameters.
 */

import type { BookingStatus } from '@/features/shared/api/types';
import {
  useInstructorBookingsList,
  useInstructorUpcomingBookings,
  useInstructorCompletedBookings,
} from '@/src/api/services/instructor-bookings';
import type { BookingResponse } from '@/src/api/generated/instructly.schemas';

type PaginatedBookingResponse = {
  items: BookingResponse[];
  total: number;
  page: number;
  per_page: number;
  has_next: boolean;
  has_prev: boolean;
};

const EMPTY_PAGE: PaginatedBookingResponse = {
  items: [],
  total: 0,
  page: 1,
  per_page: 1,
  has_next: false,
  has_prev: false,
};

type UseInstructorBookingsOptions = {
  status?: BookingStatus;
  upcoming?: boolean;
  excludeFutureConfirmed?: boolean;
  page?: number;
  perPage?: number;
  enabled?: boolean;
};

export function useInstructorBookings({
  status,
  upcoming,
  excludeFutureConfirmed,
  page = 1,
  perPage = 50,
  enabled = true,
}: UseInstructorBookingsOptions) {
  const cappedPerPage = Math.min(perPage, 100);
  type ListParams = NonNullable<Parameters<typeof useInstructorBookingsList>[0]> & {
    exclude_future_confirmed?: boolean;
  };

  // Determine which endpoint to use BEFORE calling hooks
  // This ensures we only make ONE API call, not three
  const shouldUseUpcoming = enabled && status === 'CONFIRMED' && upcoming === true;
  const shouldUseCompleted = enabled && status === 'COMPLETED' && upcoming === false;
  const shouldUseList = enabled && !shouldUseUpcoming && !shouldUseCompleted;

  // Case 1: Upcoming confirmed bookings (only enabled when needed)
  const upcomingResult = useInstructorUpcomingBookings(page, cappedPerPage, {
    enabled: shouldUseUpcoming,
  });

  // Case 2: Completed bookings (only enabled when needed)
  const completedResult = useInstructorCompletedBookings(page, cappedPerPage, {
    enabled: shouldUseCompleted,
  });

  // Case 3: General list with filters (only enabled when needed)
  const listParams = shouldUseList
    ? ({
        ...(status !== undefined ? { status } : {}),
        ...(upcoming !== undefined ? { upcoming } : {}),
        ...(excludeFutureConfirmed !== undefined
          ? { exclude_future_confirmed: excludeFutureConfirmed }
          : {}),
        page,
        per_page: cappedPerPage,
      } as ListParams)
    : undefined;

  const listResult = useInstructorBookingsList(listParams, {
    enabled: shouldUseList,
  });

  // Return the appropriate result based on parameters
  if (!enabled) {
    return {
      data: { ...EMPTY_PAGE, page, per_page: cappedPerPage },
      isLoading: false,
      isError: false,
      error: null,
      refetch: async () => ({ data: EMPTY_PAGE }),
    };
  }

  if (shouldUseUpcoming) {
    return {
      ...upcomingResult,
      data: upcomingResult.data
        ? {
            items: upcomingResult.data.items,
            total: upcomingResult.data.total,
            page: upcomingResult.data.page ?? page,
            per_page: upcomingResult.data.per_page ?? cappedPerPage,
            has_next: upcomingResult.data.has_next,
            has_prev: upcomingResult.data.has_prev,
          }
        : { ...EMPTY_PAGE, page, per_page: cappedPerPage },
    };
  }

  if (shouldUseCompleted) {
    return {
      ...completedResult,
      data: completedResult.data
        ? {
            items: completedResult.data.items,
            total: completedResult.data.total,
            page: completedResult.data.page ?? page,
            per_page: completedResult.data.per_page ?? cappedPerPage,
            has_next: completedResult.data.has_next,
            has_prev: completedResult.data.has_prev,
          }
        : { ...EMPTY_PAGE, page, per_page: cappedPerPage },
    };
  }

  // Default to general list
  return {
    ...listResult,
    data: listResult.data
      ? {
          items: listResult.data.items,
          total: listResult.data.total,
          page: listResult.data.page ?? page,
          per_page: listResult.data.per_page ?? cappedPerPage,
          has_next: listResult.data.has_next,
          has_prev: listResult.data.has_prev,
        }
      : { ...EMPTY_PAGE, page, per_page: cappedPerPage },
  };
}
