import { useGetReferralDashboardApiV1InstructorReferralsDashboardGet } from '@/src/api/generated/instructor-referrals-v1/instructor-referrals-v1';
import type {
  ReferralDashboardResponse,
  ReferralDashboardRewardItem,
} from '@/src/api/generated/instructly.schemas';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';

export type InstructorReferralReward = {
  id: string;
  amountCents: number;
  date: string;
  failureReason: string | null;
  payoutStatus: string | null;
  refereeFirstName: string;
  refereeLastInitial: string;
  referralType: 'student' | 'instructor';
};

export type InstructorReferralDashboard = {
  referralCode: string;
  referralLink: string;
  instructorAmountCents: number;
  studentAmountCents: number;
  totalReferred: number;
  pendingPayouts: number;
  totalEarnedCents: number;
  rewards: {
    pending: InstructorReferralReward[];
    unlocked: InstructorReferralReward[];
    redeemed: InstructorReferralReward[];
  };
};

export type ReferralRewardTab = keyof InstructorReferralDashboard['rewards'];

const wholeDollarFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

const dateFormatter = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
});

function mapReward(reward: ReferralDashboardRewardItem): InstructorReferralReward {
  return {
    id: reward.id,
    amountCents: reward.amount_cents,
    date: reward.date,
    failureReason: reward.failure_reason ?? null,
    payoutStatus: reward.payout_status ?? null,
    refereeFirstName: reward.referee_first_name,
    refereeLastInitial: reward.referee_last_initial,
    referralType: reward.referral_type,
  };
}

function mapDashboard(data: ReferralDashboardResponse): InstructorReferralDashboard {
  return {
    referralCode: data.referral_code,
    referralLink: data.referral_link,
    instructorAmountCents: data.instructor_amount_cents,
    studentAmountCents: data.student_amount_cents,
    totalReferred: data.total_referred,
    pendingPayouts: data.pending_payouts,
    totalEarnedCents: data.total_earned_cents,
    rewards: {
      pending: data.rewards.pending.map(mapReward),
      unlocked: data.rewards.unlocked.map(mapReward),
      redeemed: data.rewards.redeemed.map(mapReward),
    },
  };
}

export function useInstructorReferralDashboard(enabled: boolean = true) {
  return useGetReferralDashboardApiV1InstructorReferralsDashboardGet({
    query: {
      enabled,
      staleTime: CACHE_TIMES.FREQUENT,
      refetchOnWindowFocus: false,
      select: mapDashboard,
    },
  });
}

export function formatCents(cents: number): string {
  return wholeDollarFormatter.format(cents / 100);
}

export function formatReferralRewardDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) {
    return 'Date unavailable';
  }
  return dateFormatter.format(date);
}

export function formatReferralDisplayName(firstName: string, lastInitial: string): string {
  const normalizedFirstName = firstName.trim();
  const normalizedLastInitial = lastInitial.trim().replace(/\.$/, '');

  if (!normalizedFirstName) {
    return 'Unknown referral';
  }

  if (!normalizedLastInitial) {
    return normalizedFirstName;
  }

  return `${normalizedFirstName} ${normalizedLastInitial}.`;
}

export function getReferralRewardTypeLabel(referralType: InstructorReferralReward['referralType']): string {
  return referralType === 'instructor' ? 'Instructor referral' : 'Student referral';
}

export function getEmptyRewardMessage(tab: ReferralRewardTab): string {
  switch (tab) {
    case 'pending':
      return 'No pending rewards yet. Rewards appear here once a referral signs up.';
    case 'redeemed':
      return 'No redeemed rewards yet. Rewards appear here after a payout completes.';
    case 'unlocked':
    default:
      return 'No unlocked rewards yet. Rewards appear here once earned.';
  }
}
