import { useQuery } from '@tanstack/react-query';

export interface BookingStats {
  today: {
    booking_count: number;
    revenue: number;
  };
  this_week: {
    gmv: number;
    platform_revenue: number;
  };
  needs_action: {
    pending_completion: number;
    disputed: number;
  };
}

const MOCK_STATS: BookingStats = {
  today: {
    booking_count: 12,
    revenue: 1120,
  },
  this_week: {
    gmv: 4280,
    platform_revenue: 513.6,
  },
  needs_action: {
    pending_completion: 3,
    disputed: 2,
  },
};

export function useBookingStats() {
  return useQuery({
    queryKey: ['admin-payments', 'stats'],
    queryFn: async () => MOCK_STATS,
  });
}
