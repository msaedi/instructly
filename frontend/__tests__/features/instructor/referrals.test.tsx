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
    expect(screen.getByText('$50 cash')).toHaveClass('bg-(--color-brand-lavender)', 'text-(--color-brand)');
    expect(screen.getByText('$20 cash')).toHaveClass('bg-(--color-brand-lavender)', 'text-(--color-brand)');
    expect(screen.getByDisplayValue('https://beta.instainstru.com/r/FNVC6KDW')).toBeInTheDocument();
    expect(screen.getByText('In progress')).toBeInTheDocument();
    expect(screen.getByText('Pending')).toBeInTheDocument();
    expect(screen.getAllByText('Redeemed').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getAllByText('$50').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('$90')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Your Referrals' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'In Progress' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Earned' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Redeemed' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Pending' })).not.toBeInTheDocument();
    expect(screen.queryByText('How it works')).not.toBeInTheDocument();
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

    expect(screen.getByText('Arlo J.')).toBeInTheDocument();
    expect(screen.getByText('Student referral')).toBeInTheDocument();
    const pendingAmountPill = screen.getAllByText('$20').find((element) => element.tagName === 'SPAN');
    expect(pendingAmountPill).toHaveClass('bg-(--color-brand-lavender)', 'text-(--color-brand)');

    await user.click(screen.getByRole('tab', { name: 'Earned' }));
    expect(screen.getByText('Mina T.')).toBeInTheDocument();
    expect(screen.getByText('Transfer pending')).toBeInTheDocument();
    const earnedAmountPill = screen.getAllByText('$50').find((element) => element.tagName === 'SPAN');
    expect(earnedAmountPill).toHaveClass('bg-(--color-brand-lavender)', 'text-(--color-brand)');

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
