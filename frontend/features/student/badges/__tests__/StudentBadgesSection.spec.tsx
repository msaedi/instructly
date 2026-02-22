import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StudentBadgesPanel, StudentBadgesSection } from '../StudentBadgesSection';
import type { StudentBadgeItem } from '@/types/badges';

jest.mock('../useStudentBadges');
// Radix Portal renders outside the component tree; mock it to render inline
jest.mock('@radix-ui/react-dialog', () => {
  const React = require('react');
  const actual = jest.requireActual('@radix-ui/react-dialog');
  return {
    ...actual,
    Portal: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

function renderPanel(
  badges: StudentBadgeItem[],
  overrides: Partial<Parameters<typeof StudentBadgesPanel>[0]> = {},
) {
  return render(
    <StudentBadgesPanel
      badges={badges}
      isLoading={false}
      isError={false}
      errorMessage={undefined}
      onRetry={jest.fn()}
      modalOpen={false}
      onModalChange={jest.fn()}
      {...overrides}
    />,
  );
}

const allBadges: StudentBadgeItem[] = [
  {
    slug: 'welcome_aboard',
    name: 'Welcome Aboard',
    earned: true,
    status: 'confirmed',
    awarded_at: '2024-01-01T00:00:00Z',
    confirmed_at: '2024-01-02T00:00:00Z',
  },
  {
    slug: 'top_student',
    name: 'Top Student',
    earned: true,
    status: 'pending',
    awarded_at: '2024-01-05T00:00:00Z',
  },
  {
    slug: 'consistent_learner',
    name: 'Consistent Learner',
    earned: false,
    progress: { current: 2, goal: 3, percent: 66 },
    description: 'Complete three weeks in a row.',
  },
  {
    slug: 'explorer',
    name: 'Explorer',
    earned: false,
    description: 'Take lessons in three categories.',
    progress: null,
  },
];

describe('StudentBadgesPanel', () => {
  it('renders earned, pending, progress, and locked sections', () => {
    renderPanel(allBadges);

    expect(screen.getByText(/Welcome Aboard/i)).toBeInTheDocument();
    expect(screen.getByText(/Top Student/i)).toBeInTheDocument();
    expect(screen.getByText(/Verifying/i)).toBeInTheDocument();
    expect(screen.getByText(/2 \/ 3/)).toBeInTheDocument();
    expect(screen.getByText(/Take lessons in three categories/i)).toBeInTheDocument();
  });

  it('hides progress details when backend omits progress', () => {
    const badges: StudentBadgeItem[] = [
      {
        slug: 'top_student',
        name: 'Top Student',
        earned: false,
        description: 'High average rating required.',
        progress: null,
      },
    ];

    renderPanel(badges);

    expect(screen.getByText(/High average rating required/i)).toBeInTheDocument();
    expect(screen.queryByText(/\/ 0/)).not.toBeInTheDocument();
  });

  it('renders skeleton placeholders while loading', () => {
    const { container } = renderPanel([], { isLoading: true });

    // Skeleton component uses animate-pulse class
    const skeletons = container.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThanOrEqual(6);
    // Badges should not render while loading
    expect(screen.queryByText(/Earned/)).not.toBeInTheDocument();
  });

  it('renders error state with retry button', async () => {
    const user = userEvent.setup();
    const onRetry = jest.fn();
    renderPanel([], { isError: true, errorMessage: 'Something went wrong', onRetry });

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('uses fallback error message when none is provided', () => {
    renderPanel([], { isError: true, errorMessage: undefined });

    expect(screen.getByText('Unable to load badges right now.')).toBeInTheDocument();
  });

  it('shows empty state when only locked badges exist', () => {
    const lockedOnly: StudentBadgeItem[] = [
      { slug: 'explorer', name: 'Explorer', earned: false, description: 'Locked badge', progress: null },
    ];

    renderPanel(lockedOnly);

    expect(screen.getByText(/Start your first lesson/i)).toBeInTheDocument();
    expect(screen.getByText(/Welcome Aboard/i)).toBeInTheDocument();
  });

  it('calls onModalChange when Explore button is clicked', async () => {
    const user = userEvent.setup();
    const onModalChange = jest.fn();
    renderPanel(allBadges, { onModalChange });

    await user.click(screen.getByRole('button', { name: /explore/i }));
    expect(onModalChange).toHaveBeenCalledWith(true);
  });

  it('renders the badge journey dialog when modalOpen is true', () => {
    renderPanel(allBadges, { modalOpen: true });

    expect(screen.getByText('Your Badge Journey')).toBeInTheDocument();
    // "Earned (2)" appears in both the inline section and the dialog
    const earnedHeaders = screen.getAllByText(/Earned \(2\)/);
    expect(earnedHeaders.length).toBe(2);
  });

  it('shows loading spinner inside the dialog when still loading', () => {
    renderPanel([], { modalOpen: true, isLoading: true });

    expect(screen.getByText(/Loading badges/)).toBeInTheDocument();
  });

  it('clamps progress percent between 0 and 100', () => {
    const badges: StudentBadgeItem[] = [
      {
        slug: 'overachiever',
        name: 'Overachiever',
        earned: false,
        progress: { current: 5, goal: 3, percent: 150 },
        description: 'Exceeded goal.',
      },
      {
        slug: 'underdog',
        name: 'Underdog',
        earned: false,
        progress: { current: 0, goal: 10, percent: -5 },
        description: 'Negative edge case.',
      },
    ];

    renderPanel(badges);

    // Overachiever: percent clamped to 100
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByText('5 / 3')).toBeInTheDocument();
    // Underdog: percent clamped to 0
    expect(screen.getByText('0%')).toBeInTheDocument();
    expect(screen.getByText('0 / 10')).toBeInTheDocument();
  });

  it('treats non-object progress as null (no progress bar)', () => {
    const badges: StudentBadgeItem[] = [
      {
        slug: 'quirky',
        name: 'Quirky',
        earned: false,
        description: 'Weird data from backend.',
        progress: 'invalid' as unknown as null,
      },
    ];

    renderPanel(badges);

    expect(screen.getByText('Quirky')).toBeInTheDocument();
    // No progress bar should be rendered
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  describe('isBadgeProgress type guard edge cases', () => {
    it('renders progress bar for valid progress {goal: 5, current: 2, percent: 40}', () => {
      const badges: StudentBadgeItem[] = [
        {
          slug: 'valid_progress',
          name: 'Valid Progress',
          earned: false,
          description: 'Standard progress.',
          progress: { current: 2, goal: 5, percent: 40 },
        },
      ];

      renderPanel(badges);

      expect(screen.getByText('40%')).toBeInTheDocument();
      expect(screen.getByText('2 / 5')).toBeInTheDocument();
    });

    it('hides progress bar when percent field is missing', () => {
      // isBadgeProgress checks typeof progress['percent'] === 'number'
      // Missing field returns undefined, typeof undefined !== 'number' -> fails guard
      const badges: StudentBadgeItem[] = [
        {
          slug: 'no_percent',
          name: 'No Percent',
          earned: false,
          description: 'Missing percent field.',
          progress: { current: 2, goal: 5 } as unknown as null,
        },
      ];

      renderPanel(badges);

      expect(screen.getByText('No Percent')).toBeInTheDocument();
      expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    });

    it('renders NaN% when percent is NaN (typeof NaN === "number" passes the guard)', () => {
      // BUG-HUNTING: The isBadgeProgress type guard uses typeof checks.
      // typeof NaN === 'number' is true, so NaN passes the guard.
      // Math.round(NaN) = NaN, Math.min(100, NaN) = NaN, Math.max(0, NaN) = NaN
      // progressPercent = NaN, and NaN !== null is true, so hasProgress = true
      // The component renders "NaN%" text and width: NaN% style — a display bug.
      const badges: StudentBadgeItem[] = [
        {
          slug: 'nan_percent',
          name: 'NaN Percent',
          earned: false,
          description: 'NaN percent sneaks past type guard.',
          progress: { current: 2, goal: 5, percent: NaN },
        },
      ];

      renderPanel(badges);

      expect(screen.getByText('NaN Percent')).toBeInTheDocument();
      // NaN passes the type guard and the hasProgress check (NaN !== null)
      // so the progress bar renders with broken display
      expect(screen.getByText('NaN%')).toBeInTheDocument();
      expect(screen.getByText('2 / 5')).toBeInTheDocument();
    });

    it('hides progress bar when progress is null', () => {
      const badges: StudentBadgeItem[] = [
        {
          slug: 'null_progress',
          name: 'Null Progress',
          earned: false,
          description: 'Null progress from backend.',
          progress: null,
        },
      ];

      renderPanel(badges);

      expect(screen.getByText('Null Progress')).toBeInTheDocument();
      expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    });

    it('hides progress bar when progress is a string', () => {
      // isBadgeProgress: typeof "string" !== 'object' -> returns false
      const badges: StudentBadgeItem[] = [
        {
          slug: 'string_progress',
          name: 'String Progress',
          earned: false,
          description: 'String progress value.',
          progress: 'some string' as unknown as null,
        },
      ];

      renderPanel(badges);

      expect(screen.getByText('String Progress')).toBeInTheDocument();
      expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    });

    it('hides progress bar when goal is zero (even with valid type guard pass)', () => {
      // isBadgeProgress passes (all fields are numbers), but the
      // progressPercent calculation has a guard: progress.goal > 0
      // With goal=0, progressPercent becomes null
      const badges: StudentBadgeItem[] = [
        {
          slug: 'zero_goal',
          name: 'Zero Goal',
          earned: false,
          description: 'Goal is zero — division guard.',
          progress: { current: 0, goal: 0, percent: 0 },
        },
      ];

      renderPanel(badges);

      expect(screen.getByText('Zero Goal')).toBeInTheDocument();
      expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    });

    it('hides progress bar when goal field is missing but current and percent exist', () => {
      // isBadgeProgress: typeof progress['goal'] must be 'number'
      // Missing goal -> undefined -> typeof undefined !== 'number' -> fails
      const badges: StudentBadgeItem[] = [
        {
          slug: 'no_goal',
          name: 'No Goal',
          earned: false,
          description: 'Missing goal field.',
          progress: { current: 3, percent: 75 } as unknown as null,
        },
      ];

      renderPanel(badges);

      expect(screen.getByText('No Goal')).toBeInTheDocument();
      expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    });

    it('hides progress bar when current field is missing', () => {
      const badges: StudentBadgeItem[] = [
        {
          slug: 'no_current',
          name: 'No Current',
          earned: false,
          description: 'Missing current field.',
          progress: { goal: 5, percent: 0 } as unknown as null,
        },
      ];

      renderPanel(badges);

      expect(screen.getByText('No Current')).toBeInTheDocument();
      expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    });

    it('renders progress bar when all fields are NaN (all pass typeof number check)', () => {
      // BUG-HUNTING: Every field is NaN, all pass typeof === 'number'
      // goal: NaN > 0 is false, so progressPercent = null, no progress bar
      // This is actually safe — the goal > 0 guard catches NaN goal
      const badges: StudentBadgeItem[] = [
        {
          slug: 'all_nan',
          name: 'All NaN',
          earned: false,
          description: 'All fields NaN.',
          progress: { current: NaN, goal: NaN, percent: NaN },
        },
      ];

      renderPanel(badges);

      expect(screen.getByText('All NaN')).toBeInTheDocument();
      // NaN > 0 is false, so progressPercent = null, no progress bar
      expect(screen.queryByText('NaN%')).not.toBeInTheDocument();
    });

    it('renders broken display when goal is valid but current and percent are NaN', () => {
      // BUG-HUNTING: goal > 0 passes, but percent is NaN
      // Math.round(NaN) = NaN -> Math.min(100, NaN) = NaN -> Math.max(0, NaN) = NaN
      // progressPercent = NaN, NaN !== null = true -> renders progress bar with NaN%
      const badges: StudentBadgeItem[] = [
        {
          slug: 'nan_current_percent',
          name: 'NaN Current Percent',
          earned: false,
          description: 'Goal is valid but current/percent are NaN.',
          progress: { current: NaN, goal: 5, percent: NaN },
        },
      ];

      renderPanel(badges);

      expect(screen.getByText('NaN Current Percent')).toBeInTheDocument();
      expect(screen.getByText('NaN%')).toBeInTheDocument();
    });
  });
});

describe('StudentBadgesSection (wrapper)', () => {
  it('renders the panel by delegating to useStudentBadges', () => {
    const { useStudentBadges } = require('../useStudentBadges') as {
      useStudentBadges: jest.Mock;
    };
    useStudentBadges.mockReturnValue({
      data: allBadges,
      isLoading: false,
      isError: false,
      error: null,
      refetch: jest.fn(),
    });

    render(<StudentBadgesSection />);

    expect(screen.getByText(/Welcome Aboard/i)).toBeInTheDocument();
    expect(screen.getByText(/Achievements & Badges/i)).toBeInTheDocument();
  });

  it('passes error message from hook error', () => {
    const { useStudentBadges } = require('../useStudentBadges') as {
      useStudentBadges: jest.Mock;
    };
    useStudentBadges.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Badge service unavailable'),
      refetch: jest.fn(),
    });

    render(<StudentBadgesSection />);

    expect(screen.getByText('Badge service unavailable')).toBeInTheDocument();
  });

  it('calls refetch when the retry button is clicked in error state', async () => {
    const user = userEvent.setup();
    const mockRefetch = jest.fn();
    const { useStudentBadges } = require('../useStudentBadges') as {
      useStudentBadges: jest.Mock;
    };
    useStudentBadges.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Network failure'),
      refetch: mockRefetch,
    });

    render(<StudentBadgesSection />);

    // The error message should be rendered
    expect(screen.getByText('Network failure')).toBeInTheDocument();

    // Click the retry button -- this exercises the onRetry={() => void refetch()} callback
    await user.click(screen.getByRole('button', { name: /retry/i }));

    expect(mockRefetch).toHaveBeenCalledTimes(1);
  });
});
