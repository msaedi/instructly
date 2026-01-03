import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import InstructorReferralsPage from '@/app/(auth)/instructor/referrals/page';

jest.mock('@/components/UserProfileDropdown', () => ({
  __esModule: true,
  default: () => <div data-testid="user-profile-dropdown" />,
}));

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
  },
}));

jest.mock('@/hooks/queries/useInstructorReferrals', () => ({
  useInstructorReferralStats: jest.fn(),
  useReferredInstructors: jest.fn(),
  formatCents: (cents: number) => `$${(cents / 100).toFixed(0)}`,
  getPayoutStatusDisplay: (status: string) => {
    const map: Record<string, { label: string; color: string }> = {
      pending_live: { label: 'Awaiting Go-Live', color: 'gray' },
      pending_lesson: { label: 'Awaiting First Lesson', color: 'yellow' },
      pending_transfer: { label: 'Processing Payout', color: 'blue' },
      paid: { label: 'Paid', color: 'green' },
      failed: { label: 'Payout Failed', color: 'red' },
    };
    return map[status] || { label: 'Unknown', color: 'gray' };
  },
}));

const mockStats = {
  referralCode: 'TESTCODE',
  referralLink: 'https://instainstru.com/r/TESTCODE',
  totalReferred: 5,
  pendingPayouts: 2,
  completedPayouts: 3,
  totalEarnedCents: 22500,
  isFoundingPhase: true,
  foundingSpotsRemaining: 42,
  currentBonusCents: 7500,
};

const mockReferredInstructors = {
  instructors: [
    {
      id: '1',
      firstName: 'Sarah',
      lastInitial: 'C',
      referredAt: new Date('2024-12-01'),
      isLive: true,
      wentLiveAt: new Date('2024-12-05'),
      firstLessonCompletedAt: new Date('2024-12-10'),
      payoutStatus: 'paid' as const,
      payoutAmountCents: 7500,
    },
    {
      id: '2',
      firstName: 'Mike',
      lastInitial: 'R',
      referredAt: new Date('2024-12-15'),
      isLive: true,
      wentLiveAt: new Date('2024-12-18'),
      firstLessonCompletedAt: null,
      payoutStatus: 'pending_lesson' as const,
      payoutAmountCents: null,
    },
  ],
  totalCount: 2,
};

describe('InstructorReferralsPage', () => {
  const hooks = jest.requireMock('@/hooks/queries/useInstructorReferrals') as {
    useInstructorReferralStats: jest.Mock;
    useReferredInstructors: jest.Mock;
  };

  beforeEach(() => {
    hooks.useInstructorReferralStats.mockReset();
    hooks.useReferredInstructors.mockReset();
  });

  it('renders loading state', () => {
    hooks.useInstructorReferralStats.mockReturnValue({ isLoading: true });
    hooks.useReferredInstructors.mockReturnValue({ isLoading: true });

    render(<InstructorReferralsPage />);
    expect(document.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('renders referral stats', () => {
    hooks.useInstructorReferralStats.mockReturnValue({ data: mockStats, isLoading: false });
    hooks.useReferredInstructors.mockReturnValue({ data: mockReferredInstructors, isLoading: false });

    render(<InstructorReferralsPage />);

    expect(screen.getByText('Referrals')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('$225')).toBeInTheDocument();
  });

  it('shows founding phase alert when active', () => {
    hooks.useInstructorReferralStats.mockReturnValue({ data: mockStats, isLoading: false });
    hooks.useReferredInstructors.mockReturnValue({ data: mockReferredInstructors, isLoading: false });

    render(<InstructorReferralsPage />);

    expect(screen.getByText('Founding Phase Bonus')).toBeInTheDocument();
    expect(screen.getByText(/42/)).toBeInTheDocument();
  });

  it('does not show founding alert when phase is over', () => {
    hooks.useInstructorReferralStats.mockReturnValue({
      data: { ...mockStats, isFoundingPhase: false },
      isLoading: false,
    });
    hooks.useReferredInstructors.mockReturnValue({ data: mockReferredInstructors, isLoading: false });

    render(<InstructorReferralsPage />);

    expect(screen.queryByText('Founding Phase Bonus')).not.toBeInTheDocument();
  });

  it('copies referral link on button click', async () => {
    hooks.useInstructorReferralStats.mockReturnValue({ data: mockStats, isLoading: false });
    hooks.useReferredInstructors.mockReturnValue({ data: mockReferredInstructors, isLoading: false });

    const writeText = jest.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });

    render(<InstructorReferralsPage />);

    fireEvent.click(screen.getByText('Copy link'));

    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith('https://instainstru.com/r/TESTCODE');
    });
  });

  it('displays referred instructors list', () => {
    hooks.useInstructorReferralStats.mockReturnValue({ data: mockStats, isLoading: false });
    hooks.useReferredInstructors.mockReturnValue({ data: mockReferredInstructors, isLoading: false });

    render(<InstructorReferralsPage />);

    expect(screen.getByText('Sarah C.')).toBeInTheDocument();
    expect(screen.getByText('Mike R.')).toBeInTheDocument();
    expect(screen.getByText('Paid')).toBeInTheDocument();
    expect(screen.getByText('Awaiting First Lesson')).toBeInTheDocument();
  });

  it('shows empty state when no referrals', () => {
    hooks.useInstructorReferralStats.mockReturnValue({ data: mockStats, isLoading: false });
    hooks.useReferredInstructors.mockReturnValue({
      data: { instructors: [], totalCount: 0 },
      isLoading: false,
    });

    render(<InstructorReferralsPage />);

    expect(screen.getByText('No referrals yet')).toBeInTheDocument();
  });

  it('shows error state on API failure', () => {
    hooks.useInstructorReferralStats.mockReturnValue({
      error: new Error('API Error'),
      isLoading: false,
    });
    hooks.useReferredInstructors.mockReturnValue({ data: null, isLoading: false });

    render(<InstructorReferralsPage />);

    expect(screen.getByText(/Failed to load referral data/i)).toBeInTheDocument();
  });
});
