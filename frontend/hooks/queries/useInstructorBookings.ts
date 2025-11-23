import { useQuery } from '@tanstack/react-query';

import {
  protectedApi,
  type InstructorBookingsParams,
  type PaginatedBookingResponse,
} from '@/features/shared/api/client';
import type { BookingStatus } from '@/features/shared/api/types';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';

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
  page?: number;
  perPage?: number;
  enabled?: boolean;
};

export function useInstructorBookings({
  status,
  upcoming,
  page = 1,
  perPage = 50,
  enabled = true,
}: UseInstructorBookingsOptions) {
  const cappedPerPage = Math.min(perPage, 100);

  return useQuery({
    queryKey: ['instructor', 'bookings', { status: status ?? null, upcoming: !!upcoming, page, perPage: cappedPerPage }],
    queryFn: async ({ signal }) => {
      let response:
        | Awaited<ReturnType<typeof protectedApi.getInstructorBookings>>
        | Awaited<ReturnType<typeof protectedApi.getInstructorUpcomingBookings>>;
      const params: InstructorBookingsParams = {
        page,
        per_page: cappedPerPage,
        signal,
      };
      if (status === 'CONFIRMED' && upcoming === true) {
        response = await protectedApi.getInstructorUpcomingBookings(page, cappedPerPage, signal);
      } else if (status === 'COMPLETED' && upcoming === false) {
        response = await protectedApi.getInstructorCompletedBookings(page, cappedPerPage, signal);
      } else {
        if (typeof upcoming === 'boolean') {
          params.upcoming = upcoming;
        }
        if (status) {
          params.status = status;
        }
        response = await protectedApi.getInstructorBookings(params);
      }
      if (response.error) {
        if (response.status && response.status >= 400 && response.status < 500) {
          return {
            ...EMPTY_PAGE,
            page,
            per_page: cappedPerPage,
          };
        }
        throw new Error(response.error);
      }
      if (response.data) {
        return response.data;
      }
      return {
        ...EMPTY_PAGE,
        page,
        per_page: cappedPerPage,
      };
    },
    enabled,
    staleTime: CACHE_TIMES.FREQUENT,
    retry: false,
    refetchOnWindowFocus: false,
  });
}
