import { render, screen } from '@testing-library/react';

import CommissionTierCard from '../CommissionTierCard';
import { useCommissionStatus } from '@/hooks/queries/useCommissionStatus';

jest.mock('@/hooks/queries/useCommissionStatus');

const mockUseCommissionStatus = useCommissionStatus as jest.MockedFunction<
  typeof useCommissionStatus
>;

function buildStatus(
  overrides: Partial<{
    is_founding: boolean;
    tier_name: string;
    commission_rate_pct: number;
    completed_lessons_30d: number;
    next_tier_name: string | null;
    next_tier_threshold: number | null;
    lessons_to_next_tier: number | null;
    tiers: Array<{
      name: string;
      display_name: string;
      commission_pct: number;
      min_lessons: number;
      max_lessons: number | null;
      is_current?: boolean;
      is_unlocked?: boolean;
    }>;
  }> = {}
) {
  return {
    is_founding: false,
    tier_name: 'entry',
    commission_rate_pct: 15,
    completed_lessons_30d: 3,
    next_tier_name: 'growth',
    next_tier_threshold: 5,
    lessons_to_next_tier: 2,
    tiers: [
      {
        name: 'entry',
        display_name: 'Entry',
        commission_pct: 15,
        min_lessons: 1,
        max_lessons: 4,
        is_current: true,
        is_unlocked: true,
      },
      {
        name: 'growth',
        display_name: 'Growth',
        commission_pct: 12,
        min_lessons: 5,
        max_lessons: 10,
        is_current: false,
        is_unlocked: false,
      },
      {
        name: 'pro',
        display_name: 'Pro',
        commission_pct: 10,
        min_lessons: 11,
        max_lessons: null,
        is_current: false,
        is_unlocked: false,
      },
    ],
    ...overrides,
  };
}

describe('CommissionTierCard', () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  it('returns null while commission status is unavailable', () => {
    mockUseCommissionStatus.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as unknown as ReturnType<typeof useCommissionStatus>);

    const { container } = render(<CommissionTierCard />);

    expect(container.firstChild).toBeNull();
  });

  it('returns null when a standard instructor has no tier ladder data', () => {
    mockUseCommissionStatus.mockReturnValue({
      data: buildStatus({
        tiers: [],
      }),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useCommissionStatus>);

    const { container } = render(<CommissionTierCard />);

    expect(container.firstChild).toBeNull();
  });

  it('renders founding view with locked badge and commitment copy', () => {
    mockUseCommissionStatus.mockReturnValue({
      data: buildStatus({
        is_founding: true,
        tier_name: 'founding',
        commission_rate_pct: 8,
        next_tier_name: null,
        next_tier_threshold: null,
        lessons_to_next_tier: null,
      }),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useCommissionStatus>);

    const { container } = render(<CommissionTierCard />);

    expect(screen.getByText('Founding Instructor')).toBeInTheDocument();
    expect(screen.getByText('8% · locked')).toBeInTheDocument();
    expect(
      screen.getByText(
        "You have locked in our lowest rate—permanently. Whatever the floor is, you're on it."
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText('10 hours per week · 3+ days · 8am–8pm · measured monthly (40 hrs/month)')
    ).toBeInTheDocument();
    expect(container.querySelector('svg')).toBeTruthy();
  });

  it('renders standard tier ladder with progress helper text', () => {
    mockUseCommissionStatus.mockReturnValue({
      data: buildStatus(),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useCommissionStatus>);

    render(<CommissionTierCard />);

    expect(screen.getByText('Entry tier · 15%')).toBeInTheDocument();
    expect(
      screen.getByText('3 of 5 lessons completed · in the last 30 days')
    ).toBeInTheDocument();
    expect(screen.getByText('Growth · 12%')).toBeInTheDocument();
    expect(screen.getByText('3 of 5 · 2 more to unlock')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Growth progress' })).toBeInTheDocument();
    expect(screen.queryByRole('progressbar', { name: 'Entry progress' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('progressbar')).toHaveLength(1);
  });

  it('renders growth tier with a full current-tier bar and partial next-tier bar', () => {
    mockUseCommissionStatus.mockReturnValue({
      data: buildStatus({
        tier_name: 'growth',
        commission_rate_pct: 12,
        completed_lessons_30d: 7,
        next_tier_name: 'pro',
        next_tier_threshold: 11,
        lessons_to_next_tier: 4,
        tiers: [
          {
            name: 'entry',
            display_name: 'Entry',
            commission_pct: 15,
            min_lessons: 1,
            max_lessons: 4,
            is_current: false,
            is_unlocked: true,
          },
          {
            name: 'growth',
            display_name: 'Growth',
            commission_pct: 12,
            min_lessons: 5,
            max_lessons: 10,
            is_current: true,
            is_unlocked: true,
          },
          {
            name: 'pro',
            display_name: 'Pro',
            commission_pct: 10,
            min_lessons: 11,
            max_lessons: null,
            is_current: false,
            is_unlocked: false,
          },
        ],
      }),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useCommissionStatus>);

    render(<CommissionTierCard />);

    expect(screen.getByText('Growth tier · 12%')).toBeInTheDocument();
    expect(
      screen.getByText('7 of 11 lessons completed · in the last 30 days')
    ).toBeInTheDocument();
    expect(screen.getByText('7 of 11 · 4 more to unlock')).toBeInTheDocument();
    expect(screen.queryByRole('progressbar', { name: 'Entry progress' })).not.toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Growth progress' })).toHaveAttribute(
      'aria-valuenow',
      '100'
    );
    expect(screen.getByRole('progressbar', { name: 'Pro progress' })).toHaveAttribute(
      'aria-valuenow',
      '7'
    );
    expect(screen.getAllByRole('progressbar')).toHaveLength(2);
  });

  it('renders pro tier with completed lower-tier bars and no helper text', () => {
    mockUseCommissionStatus.mockReturnValue({
      data: buildStatus({
        tier_name: 'pro',
        commission_rate_pct: 10,
        completed_lessons_30d: 14,
        next_tier_name: null,
        next_tier_threshold: null,
        lessons_to_next_tier: null,
        tiers: [
          {
            name: 'entry',
            display_name: 'Entry',
            commission_pct: 15,
            min_lessons: 1,
            max_lessons: 4,
            is_current: false,
            is_unlocked: true,
          },
          {
            name: 'growth',
            display_name: 'Growth',
            commission_pct: 12,
            min_lessons: 5,
            max_lessons: 10,
            is_current: false,
            is_unlocked: true,
          },
          {
            name: 'pro',
            display_name: 'Pro',
            commission_pct: 10,
            min_lessons: 11,
            max_lessons: null,
            is_current: true,
            is_unlocked: true,
          },
        ],
      }),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useCommissionStatus>);

    render(<CommissionTierCard />);

    expect(screen.getByText('Pro tier · 10%')).toBeInTheDocument();
    expect(
      screen.getByText('14 lessons completed · in the last 30 days')
    ).toBeInTheDocument();
    expect(screen.queryByRole('progressbar', { name: 'Entry progress' })).not.toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Growth progress' })).toHaveAttribute(
      'aria-valuenow',
      '100'
    );
    expect(screen.getByRole('progressbar', { name: 'Pro progress' })).toHaveAttribute(
      'aria-valuenow',
      '100'
    );
    expect(screen.getAllByRole('progressbar')).toHaveLength(2);
    expect(screen.queryByText(/more to unlock/i)).not.toBeInTheDocument();
  });
});
