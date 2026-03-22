import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import InstructorReferralsPage from '@/app/(auth)/instructor/referrals/page';
import { copyToClipboard } from '@/lib/copy';
import { shareOrCopy } from '@/features/shared/referrals/share';

jest.mock('@/components/UserProfileDropdown', () => ({
  __esModule: true,
  default: () => <div data-testid="user-profile-dropdown" />,
}));

jest.mock('@/hooks/queries/useInstructorReferrals', () => ({
  useInstructorReferralDashboard: jest.fn(),
  formatCents: (cents: number) => `$${Math.round(cents / 100)}`,
  formatReferralRewardDate: (value: string) =>
    value === 'not-a-date' ? 'Date unavailable' : 'Mar 21, 2026',
  formatReferralDisplayName: (firstName: string, lastInitial: string) =>
    lastInitial ? `${firstName} ${lastInitial}.` : firstName,
  getReferralRewardTypeLabel: (referralType: string) =>
    referralType === 'instructor' ? 'Instructor referral' : 'Student referral',
  getEmptyRewardMessage: (tab: string) => {
    const messages: Record<string, string> = {
      unlocked: 'No unlocked rewards yet. Rewards appear here once earned.',
      pending: 'No pending rewards yet. Rewards appear here once a referral signs up.',
      redeemed: 'No redeemed rewards yet. Rewards appear here after a payout completes.',
    };
    return messages[tab];
  },
}));

jest.mock('@/lib/copy', () => ({
  copyToClipboard: jest.fn(),
}));

jest.mock('@/features/shared/referrals/share', () => ({
  shareOrCopy: jest.fn(),
}));

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

const hookModule = jest.requireMock('@/hooks/queries/useInstructorReferrals') as {
  useInstructorReferralDashboard: jest.Mock;
};
const copyToClipboardMock = copyToClipboard as jest.MockedFunction<typeof copyToClipboard>;
const shareOrCopyMock = shareOrCopy as jest.MockedFunction<typeof shareOrCopy>;
const { toast } = jest.requireMock('sonner') as {
  toast: {
    success: jest.Mock;
    error: jest.Mock;
  };
};

const dashboardResponse = {
  referralCode: 'FNVC6KDW',
  referralLink: 'https://beta.instainstru.com/r/FNVC6KDW',
  instructorAmountCents: 5000,
  studentAmountCents: 2000,
  totalReferred: 4,
  pendingPayouts: 2,
  totalEarnedCents: 9000,
  rewards: {
    unlocked: [
      {
        id: 'reward-1',
        amountCents: 5000,
        date: '2026-03-21T12:00:00Z',
        failureReason: null,
        payoutStatus: 'pending',
        refereeFirstName: 'Mina',
        refereeLastInitial: 'T',
        referralType: 'instructor' as const,
      },
    ],
    pending: [
      {
        id: 'reward-2',
        amountCents: 2000,
        date: '2026-03-21T12:00:00Z',
        failureReason: null,
        payoutStatus: null,
        refereeFirstName: 'Arlo',
        refereeLastInitial: 'J',
        referralType: 'student' as const,
      },
    ],
    redeemed: [
      {
        id: 'reward-3',
        amountCents: 5000,
        date: '2026-03-21T12:00:00Z',
        failureReason: null,
        payoutStatus: 'paid',
        refereeFirstName: 'Nora',
        refereeLastInitial: 'L',
        referralType: 'instructor' as const,
      },
    ],
  },
};

describe('InstructorReferralsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    hookModule.useInstructorReferralDashboard.mockReturnValue({
      data: dashboardResponse,
      isLoading: false,
      isError: false,
    });
    copyToClipboardMock.mockResolvedValue(true);
    shareOrCopyMock.mockResolvedValue('shared');
  });

  it('renders the redesigned referrals dashboard', () => {
    render(<InstructorReferralsPage />);

    expect(screen.getByRole('heading', { name: 'Referrals' })).toBeInTheDocument();
    expect(screen.getByText('Refer an instructor')).toBeInTheDocument();
    expect(screen.getByText('Refer a student')).toBeInTheDocument();
    expect(screen.getByText('$50 cash')).toBeInTheDocument();
    expect(screen.getByText('$20 cash')).toBeInTheDocument();
    expect(screen.getByDisplayValue('https://beta.instainstru.com/r/FNVC6KDW')).toBeInTheDocument();
    expect(screen.getByText('Total referred')).toBeInTheDocument();
    expect(screen.getByText('Pending payouts')).toBeInTheDocument();
    expect(screen.getByText('Total earned')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Unlocked' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Pending' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Redeemed' })).toBeInTheDocument();
    expect(
      screen.getByText('Share your unique referral link with students or fellow instructors.')
    ).toBeInTheDocument();
    expect(screen.getByText('They sign up and join iNSTAiNSTRU.')).toBeInTheDocument();
    expect(screen.queryByText(/founding/i)).not.toBeInTheDocument();
  });

  it('copies the referral link from the copy button', async () => {
    const user = userEvent.setup();

    render(<InstructorReferralsPage />);
    await user.click(screen.getByRole('button', { name: 'Copy referral link' }));

    await waitFor(() => {
      expect(copyToClipboardMock).toHaveBeenCalledWith('https://beta.instainstru.com/r/FNVC6KDW');
    });
    expect(toast.success).toHaveBeenCalledWith('Referral link copied');
  });

  it('switches reward tabs and renders the selected reward list', async () => {
    const user = userEvent.setup();

    render(<InstructorReferralsPage />);

    expect(screen.getByText('Mina T.')).toBeInTheDocument();
    expect(screen.getByText('Transfer pending')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Pending' }));
    expect(screen.getByText('Arlo J.')).toBeInTheDocument();
    expect(screen.getByText('Student referral')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Redeemed' }));
    expect(screen.getByText('Nora L.')).toBeInTheDocument();
    expect(screen.getByText('Transferred')).toBeInTheDocument();
  });

  it('renders loading and error states', () => {
    hookModule.useInstructorReferralDashboard.mockReturnValueOnce({
      data: undefined,
      isLoading: true,
      isError: false,
    });

    const { rerender } = render(<InstructorReferralsPage />);
    expect(document.querySelector('.animate-pulse')).toBeInTheDocument();

    hookModule.useInstructorReferralDashboard.mockReturnValueOnce({
      data: undefined,
      isLoading: false,
      isError: true,
    });

    rerender(<InstructorReferralsPage />);
    expect(screen.getByText(/Failed to load referrals right now/i)).toBeInTheDocument();
  });
});
