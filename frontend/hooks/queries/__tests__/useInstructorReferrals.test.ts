import { renderHook } from '@testing-library/react';

import {
  formatCents,
  formatReferralDisplayName,
  formatReferralRewardDate,
  getEmptyRewardMessage,
  getReferralRewardTypeLabel,
  useInstructorReferralDashboard,
} from '../useInstructorReferrals';
import { useGetReferralDashboardApiV1InstructorReferralsDashboardGet } from '@/src/api/generated/instructor-referrals-v1/instructor-referrals-v1';

jest.mock('@/src/api/generated/instructor-referrals-v1/instructor-referrals-v1', () => ({
  useGetReferralDashboardApiV1InstructorReferralsDashboardGet: jest.fn(),
}));

const useDashboardQueryMock = useGetReferralDashboardApiV1InstructorReferralsDashboardGet as jest.Mock;

describe('useInstructorReferralDashboard', () => {
  beforeEach(() => {
    useDashboardQueryMock.mockReset();
    useDashboardQueryMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      queryKey: ['/api/v1/instructor-referrals/dashboard'],
    });
  });

  it('maps the dashboard payload into the frontend shape', () => {
    renderHook(() => useInstructorReferralDashboard());

    const options = useDashboardQueryMock.mock.calls[0][0] as {
      query: {
        enabled: boolean;
        refetchOnWindowFocus: boolean;
        staleTime: number;
        select: (value: unknown) => unknown;
      };
    };

    const mapped = options.query.select({
      referral_code: 'FNVC6KDW',
      referral_link: 'https://beta.instainstru.com/r/FNVC6KDW',
      instructor_amount_cents: 5000,
      student_amount_cents: 2000,
      total_referred: 3,
      pending_payouts: 1,
      total_earned_cents: 7000,
      rewards: {
        pending: [
          {
            id: 'pending-1',
            amount_cents: 2000,
            date: '2026-03-20T10:00:00Z',
            failure_reason: null,
            payout_status: null,
            referee_first_name: 'Sam',
            referee_last_initial: 'L',
            referral_type: 'student',
          },
        ],
        unlocked: [],
        redeemed: [],
      },
    });

    expect(mapped).toEqual({
      referralCode: 'FNVC6KDW',
      referralLink: 'https://beta.instainstru.com/r/FNVC6KDW',
      instructorAmountCents: 5000,
      studentAmountCents: 2000,
      totalReferred: 3,
      pendingPayouts: 1,
      totalEarnedCents: 7000,
      rewards: {
        pending: [
          {
            id: 'pending-1',
            amountCents: 2000,
            date: '2026-03-20T10:00:00Z',
            failureReason: null,
            payoutStatus: null,
            refereeFirstName: 'Sam',
            refereeLastInitial: 'L',
            referralType: 'student',
          },
        ],
        unlocked: [],
        redeemed: [],
      },
    });
    expect(options.query.enabled).toBe(true);
    expect(options.query.refetchOnWindowFocus).toBe(false);
    expect(typeof options.query.staleTime).toBe('number');
  });

  it('passes through a disabled query state', () => {
    renderHook(() => useInstructorReferralDashboard(false));

    expect(useDashboardQueryMock).toHaveBeenCalledWith({
      query: expect.objectContaining({
        enabled: false,
      }),
    });
  });
});

describe('formatCents', () => {
  it('formats cents as whole dollars', () => {
    expect(formatCents(5000)).toBe('$50');
    expect(formatCents(0)).toBe('$0');
  });
});

describe('formatReferralRewardDate', () => {
  it('formats ISO dates for display', () => {
    expect(formatReferralRewardDate('2026-03-21T12:00:00Z')).toBe('Mar 21, 2026');
  });

  it('falls back when the date is invalid', () => {
    expect(formatReferralRewardDate('not-a-date')).toBe('Date unavailable');
  });
});

describe('formatReferralDisplayName', () => {
  it('formats a first name and last initial', () => {
    expect(formatReferralDisplayName('John', 'S')).toBe('John S.');
  });

  it('falls back to first name when the initial is blank', () => {
    expect(formatReferralDisplayName('John', '')).toBe('John');
  });

  it('falls back when the first name is blank', () => {
    expect(formatReferralDisplayName('', 'S')).toBe('Unknown referral');
  });
});

describe('referral reward labels', () => {
  it('maps referral type labels', () => {
    expect(getReferralRewardTypeLabel('instructor')).toBe('Instructor referral');
    expect(getReferralRewardTypeLabel('student')).toBe('Student referral');
  });

  it('returns empty messages for each tab', () => {
    expect(getEmptyRewardMessage('unlocked')).toBe(
      'No unlocked rewards yet. Rewards appear here once earned.'
    );
    expect(getEmptyRewardMessage('pending')).toBe(
      'No pending rewards yet. Rewards appear here once a referral signs up.'
    );
    expect(getEmptyRewardMessage('redeemed')).toBe(
      'No redeemed rewards yet. Rewards appear here after a payout completes.'
    );
  });
});
