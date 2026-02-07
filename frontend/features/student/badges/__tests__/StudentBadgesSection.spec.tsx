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
});
