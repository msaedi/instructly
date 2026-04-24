import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import InstructorReferralsPage from '../page';
import { useInstructorReferralDashboard } from '@/hooks/queries/useInstructorReferrals';

jest.mock('@/hooks/queries/useInstructorReferrals', () => {
  const actual = jest.requireActual('@/hooks/queries/useInstructorReferrals');
  return {
    ...actual,
    useInstructorReferralDashboard: jest.fn(),
  };
});

jest.mock('@/components/UserProfileDropdown', () => ({
  __esModule: true,
  default: () => <div data-testid="user-dropdown" />,
}));

jest.mock('@/components/dashboard/SectionHeroCard', () => ({
  __esModule: true,
  SectionHeroCard: ({ title }: { title: string }) => <div>{title}</div>,
}));

jest.mock('@/features/referrals/InviteByEmail', () => ({
  __esModule: true,
  default: () => <div data-testid="invite-by-email" />,
}));

jest.mock('../../_embedded/EmbeddedContext', () => ({
  useEmbedded: () => false,
}));

const mockUseInstructorReferralDashboard =
  useInstructorReferralDashboard as jest.MockedFunction<typeof useInstructorReferralDashboard>;

describe('InstructorReferralsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseInstructorReferralDashboard.mockReturnValue({
      data: {
        referralCode: 'REF123',
        referralLink: 'https://example.com/ref/REF123',
        instructorAmountCents: 2500,
        studentAmountCents: 2000,
        totalReferred: 2,
        pendingPayouts: 1,
        totalEarnedCents: 2000,
        rewards: {
          pending: [
            {
              id: 'reward-pending',
              amountCents: 2000,
              date: '2026-04-01T12:00:00Z',
              failureReason: null,
              payoutStatus: 'pending',
              refereeFirstName: 'Mia',
              refereeLastInitial: 'J',
              referralType: 'student',
            },
          ],
          unlocked: [
            {
              id: 'reward-unlocked',
              amountCents: 2500,
              date: '2026-04-02T12:00:00Z',
              failureReason: null,
              payoutStatus: null,
              refereeFirstName: 'Theo',
              refereeLastInitial: 'R',
              referralType: 'instructor',
            },
          ],
          redeemed: [],
        },
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useInstructorReferralDashboard>);
  });

  it('renders the shared full-width tab underline and switches reward groups', async () => {
    const user = userEvent.setup();

    render(<InstructorReferralsPage />);

    const inProgressTab = screen.getByRole('tab', { name: 'In Progress' });
    const earnedTab = screen.getByRole('tab', { name: 'Earned' });

    expect(inProgressTab).toHaveClass(
      '-mb-px',
      'flex-1',
      'border-b-2',
      'border-(--color-brand)',
      'text-(--color-brand)'
    );
    expect(earnedTab).toHaveClass('flex-1', 'border-transparent');
    expect(screen.getByText('Mia J.')).toBeInTheDocument();

    await user.click(earnedTab);

    expect(screen.getByText('Theo R.')).toBeInTheDocument();
    expect(earnedTab).toHaveAttribute('aria-selected', 'true');
  });
});
