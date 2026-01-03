import { useQuery } from '@tanstack/react-query';

import { CACHE_TIMES } from '@/lib/react-query/queryClient';
import {
  instructorReferralsApi,
  type FoundingStatus,
  type PopupData,
  type ReferralStats,
  type ReferredInstructor,
} from '@/services/api/instructorReferrals';

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

export type PayoutStatusTone = 'gray' | 'yellow' | 'blue' | 'green' | 'red';

export function useInstructorReferralStats(enabled: boolean = true) {
  return useQuery<ReferralStats>({
    queryKey: ['instructor', 'referrals', 'stats'],
    queryFn: () => instructorReferralsApi.getStats(),
    enabled,
    staleTime: CACHE_TIMES.FREQUENT,
    refetchOnWindowFocus: false,
  });
}

export function useReferredInstructors(params?: { limit?: number; offset?: number }, enabled: boolean = true) {
  return useQuery<{ instructors: ReferredInstructor[]; totalCount: number }>({
    queryKey: ['instructor', 'referrals', 'referred', params],
    queryFn: () => instructorReferralsApi.getReferredInstructors(params),
    enabled,
    staleTime: CACHE_TIMES.FREQUENT,
    refetchOnWindowFocus: false,
  });
}

export function useFoundingStatus(enabled: boolean = true) {
  return useQuery<FoundingStatus>({
    queryKey: ['instructor', 'referrals', 'founding-status'],
    queryFn: () => instructorReferralsApi.getFoundingStatus(),
    enabled,
    staleTime: CACHE_TIMES.SLOW,
    refetchOnWindowFocus: false,
  });
}

export function useReferralPopupData(enabled: boolean = true) {
  return useQuery<PopupData>({
    queryKey: ['instructor', 'referrals', 'popup-data'],
    queryFn: () => instructorReferralsApi.getPopupData(),
    enabled,
    staleTime: 1000 * 60 * 30,
    refetchOnWindowFocus: false,
  });
}

export function formatCents(cents: number): string {
  return currencyFormatter.format(cents / 100);
}

export function getPayoutStatusDisplay(
  status: ReferredInstructor['payoutStatus']
): { label: string; color: PayoutStatusTone } {
  switch (status) {
    case 'pending_live':
      return { label: 'Awaiting Go-Live', color: 'gray' };
    case 'pending_lesson':
      return { label: 'Awaiting First Lesson', color: 'yellow' };
    case 'pending_transfer':
      return { label: 'Processing Payout', color: 'blue' };
    case 'paid':
      return { label: 'Paid', color: 'green' };
    case 'failed':
      return { label: 'Payout Failed', color: 'red' };
    default:
      return { label: 'Unknown', color: 'gray' };
  }
}
