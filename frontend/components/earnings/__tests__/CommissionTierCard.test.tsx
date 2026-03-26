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
    activity_window_days: number;
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
    activity_window_days: 30,
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
    expect(screen.getByTestId('commission-rate-pill')).toHaveClass(
      'bg-[#F3E8FF]',
      'text-[#7E22CE]'
    );
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

  it('uses fallback dot counts for nonstandard tier names', () => {
    mockUseCommissionStatus.mockReturnValue({
      data: buildStatus({
        tier_name: 'custom_window',
        commission_rate_pct: 13,
        completed_lessons_30d: 3,
        next_tier_name: 'custom_open',
        next_tier_threshold: 5,
        lessons_to_next_tier: 2,
        tiers: [
          {
            name: 'custom_window',
            display_name: 'Custom Window',
            commission_pct: 13,
            min_lessons: 2,
            max_lessons: 4,
            is_current: true,
            is_unlocked: true,
          },
          {
            name: 'custom_open',
            display_name: 'Custom Open',
            commission_pct: 9,
            min_lessons: 5,
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

    expect(screen.getByText('Custom Window tier · 13%')).toBeInTheDocument();
    expect(screen.getByTestId('commission-tier-track-custom_window')).toHaveAttribute(
      'data-dot-count',
      '3'
    );
    expect(screen.getByTestId('commission-tier-track-custom_window')).toHaveAttribute(
      'data-filled-dots',
      '2'
    );
    expect(screen.getByTestId('commission-tier-track-custom_open')).toHaveAttribute(
      'data-dot-count',
      '1'
    );
    expect(screen.getByTestId('commission-tier-track-custom_open')).toHaveAttribute(
      'data-filled-dots',
      '0'
    );
  });

  it('renders the entry tier ladder with the dot-line pattern and lavender rate pill', () => {
    mockUseCommissionStatus.mockReturnValue({
      data: buildStatus({
        activity_window_days: 45,
      }),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useCommissionStatus>);

    render(<CommissionTierCard />);

    expect(screen.getByText('Entry tier · 15%')).toBeInTheDocument();
    expect(
      screen.getByText('3 lessons completed · in the last 45 days')
    ).toBeInTheDocument();
    expect(screen.getByTestId('commission-rate-pill')).toHaveClass(
      'bg-[#F3E8FF]',
      'text-[#7E22CE]'
    );
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(screen.getByTestId('commission-tier-connector')).toBeInTheDocument();
    expect(screen.getByTestId('commission-tier-row-entry')).toHaveAttribute(
      'data-tier-state',
      'active'
    );
    expect(screen.getByTestId('commission-tier-step-entry')).toHaveClass(
      'bg-[#7C3AED]',
      'border-[#7C3AED]'
    );
    expect(screen.getByTestId('commission-tier-track-entry')).toHaveAttribute('data-dot-count', '4');
    expect(screen.getByTestId('commission-tier-track-entry')).toHaveAttribute(
      'data-filled-dots',
      '3'
    );
    expect(screen.getAllByTestId(/commission-tier-dot-entry-/)).toHaveLength(4);
    expect(screen.getByTestId('commission-tier-dot-entry-4')).toHaveAttribute(
      'data-dot-state',
      'unfilled'
    );
    expect(screen.getByTestId('commission-tier-row-growth')).toHaveAttribute(
      'data-tier-state',
      'unmet'
    );
    expect(screen.getByTestId('commission-tier-track-growth')).toHaveAttribute(
      'data-dot-count',
      '6'
    );
    expect(screen.getByTestId('commission-tier-track-growth')).toHaveAttribute(
      'data-filled-dots',
      '0'
    );
    expect(screen.getByTestId('commission-tier-track-pro')).toHaveAttribute('data-dot-count', '1');
  });

  it('renders met, active, and unmet tier states for growth instructors', () => {
    mockUseCommissionStatus.mockReturnValue({
      data: buildStatus({
        tier_name: 'growth',
        commission_rate_pct: 12,
        completed_lessons_30d: 6,
        next_tier_name: 'pro',
        next_tier_threshold: 11,
        lessons_to_next_tier: 5,
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
      screen.getByText('6 lessons completed · in the last 30 days')
    ).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(screen.getByTestId('commission-tier-row-entry')).toHaveAttribute(
      'data-tier-state',
      'met'
    );
    expect(screen.getByTestId('commission-tier-step-entry')).toHaveClass(
      'bg-[#F3E8FF]',
      'text-[#7E22CE]'
    );
    expect(screen.getByTestId('commission-tier-step-entry')).toHaveTextContent('1');
    expect(screen.getByTestId('commission-tier-track-entry')).toHaveAttribute(
      'data-filled-dots',
      '4'
    );
    expect(screen.getByTestId('commission-tier-row-growth')).toHaveAttribute(
      'data-tier-state',
      'active'
    );
    expect(screen.getByTestId('commission-tier-step-growth')).toHaveAttribute(
      'aria-current',
      'step'
    );
    expect(screen.getByTestId('commission-tier-track-growth')).toHaveAttribute(
      'data-dot-count',
      '6'
    );
    expect(screen.getByTestId('commission-tier-track-growth')).toHaveAttribute(
      'data-filled-dots',
      '2'
    );
    expect(screen.getByTestId('commission-tier-dot-growth-3')).toHaveAttribute(
      'data-dot-state',
      'unfilled'
    );
    expect(screen.getByTestId('commission-tier-row-pro')).toHaveAttribute(
      'data-tier-state',
      'unmet'
    );
    expect(screen.getByTestId('commission-tier-step-pro')).toHaveTextContent('3');
    expect(screen.getByTestId('commission-tier-track-pro')).toHaveAttribute(
      'data-filled-dots',
      '0'
    );
  });

  it('renders pro tier with completed lower tiers and a single filled pro milestone', () => {
    mockUseCommissionStatus.mockReturnValue({
      data: buildStatus({
        tier_name: 'pro',
        commission_rate_pct: 10,
        completed_lessons_30d: 19,
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
      screen.getByText('19 lessons completed · in the last 30 days')
    ).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(screen.getByTestId('commission-tier-row-entry')).toHaveAttribute(
      'data-tier-state',
      'met'
    );
    expect(screen.getByTestId('commission-tier-step-entry')).toHaveTextContent('1');
    expect(screen.getByTestId('commission-tier-row-growth')).toHaveAttribute(
      'data-tier-state',
      'met'
    );
    expect(screen.getByTestId('commission-tier-step-growth')).toHaveTextContent('2');
    expect(screen.getByTestId('commission-tier-row-pro')).toHaveAttribute(
      'data-tier-state',
      'active'
    );
    expect(screen.getByTestId('commission-tier-step-pro')).toHaveAttribute(
      'aria-current',
      'step'
    );
    expect(screen.getByTestId('commission-tier-track-entry')).toHaveAttribute(
      'data-filled-dots',
      '4'
    );
    expect(screen.getByTestId('commission-tier-track-growth')).toHaveAttribute(
      'data-filled-dots',
      '6'
    );
    expect(screen.getByTestId('commission-tier-track-pro')).toHaveAttribute(
      'data-filled-dots',
      '1'
    );
    expect(screen.getByTestId('commission-tier-dot-pro-1')).toHaveAttribute(
      'data-dot-state',
      'filled'
    );
  });
});
