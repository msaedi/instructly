import { render, screen } from '@testing-library/react';
import { StudentBadgesPanel } from '../StudentBadgesSection';
import type { StudentBadgeItem } from '@/types/badges';

function renderPanel(badges: StudentBadgeItem[]) {
  return render(
    <StudentBadgesPanel
      badges={badges}
      isLoading={false}
      isError={false}
      errorMessage={undefined}
      onRetry={jest.fn()}
      modalOpen={false}
      onModalChange={jest.fn()}
    />
  );
}

describe('StudentBadgesPanel', () => {
  it('renders earned, pending, progress, and locked sections', () => {
    const badges: StudentBadgeItem[] = [
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

    renderPanel(badges);

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
});
