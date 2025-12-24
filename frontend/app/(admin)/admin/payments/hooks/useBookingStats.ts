import { useQuery } from '@tanstack/react-query';

import { getAdminBookingStatsApiV1AdminBookingsStatsGet } from '@/src/api/generated/admin-bookings/admin-bookings';
import type { AdminBookingStatsResponse } from '@/src/api/generated/instructly.schemas';

export type BookingStats = AdminBookingStatsResponse;

export function useBookingStats() {
  return useQuery({
    queryKey: ['admin-payments', 'stats'],
    queryFn: async (): Promise<BookingStats> => getAdminBookingStatsApiV1AdminBookingsStatsGet(),
  });
}
