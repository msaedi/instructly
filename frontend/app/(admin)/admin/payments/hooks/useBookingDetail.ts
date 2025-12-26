import { useQuery } from '@tanstack/react-query';

import { getAdminBookingDetailApiV1AdminBookingsBookingIdGet } from '@/src/api/generated/admin-bookings/admin-bookings';

import { mapBookingDetailToAdminBooking, type AdminBooking } from './useAdminBookings';

export function useBookingDetail(bookingId: string | null) {
  return useQuery({
    queryKey: ['admin-payments', 'booking', bookingId],
    queryFn: async (): Promise<AdminBooking | null> => {
      if (!bookingId) {
        return null;
      }
      const detail = await getAdminBookingDetailApiV1AdminBookingsBookingIdGet(bookingId);
      return mapBookingDetailToAdminBooking(detail);
    },
    enabled: Boolean(bookingId),
  });
}
