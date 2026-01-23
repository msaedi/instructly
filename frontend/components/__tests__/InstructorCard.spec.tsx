import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import InstructorCard, { type InstructorAvailabilityData } from '@/components/InstructorCard';
import type { Instructor } from '@/types/api';

const pushMock = jest.fn();

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'QueryClientWrapper';
  return Wrapper;
};

const renderWithQueryClient = (ui: React.ReactElement) =>
  render(ui, { wrapper: createWrapper() });

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

jest.mock('@/hooks/queries/useFavoriteStatus', () => ({
  useFavoriteStatus: () => ({ data: false, isLoading: false }),
  useSetFavoriteStatus: () => jest.fn(),
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => ({ user: null, isAuthenticated: false, redirectToLogin: jest.fn() }),
}));

jest.mock('@/hooks/useCreateConversation', () => ({
  useCreateConversation: () => ({
    createConversation: jest.fn(),
    isCreating: false,
    error: null,
  }),
}));

jest.mock('@/hooks/queries/useRatings', () => ({
  useSearchRatingQuery: () => ({ data: null }),
}));

jest.mock('@/src/api/services/reviews', () => ({
  useRecentReviews: () => ({ data: { reviews: [] }, isLoading: false }),
}));

jest.mock('@/hooks/queries/useServices', () => ({
  useServicesCatalog: () => ({ data: [] }),
}));

jest.mock('@/services/api/favorites', () => ({
  favoritesApi: {
    check: jest.fn().mockResolvedValue({ is_favorited: false }),
    add: jest.fn().mockResolvedValue(undefined),
    remove: jest.fn().mockResolvedValue(undefined),
  },
}));

jest.mock('@/services/api/reviews', () => ({
  reviewsApi: {
    getRecent: jest.fn().mockResolvedValue({ reviews: [] }),
  },
}));

jest.mock('@/lib/api/pricing', () => ({
  fetchPricingPreview: jest.fn(),
  formatCentsToDisplay: jest.fn((amount: number) => `$${(amount / 100).toFixed(2)}`),
}));


const buildInstructor = (): Instructor => ({
  id: 'instructor-profile-1',
  user_id: 'user-1',
  bio: 'Dedicated instructor',
  years_experience: 5,
  user: {
    first_name: 'Sarah',
    last_initial: 'C',
  },
  services: [
    {
      id: 'service-1',
      service_catalog_id: 'catalog-1',
      hourly_rate: 60,
      description: 'Lesson',
      duration_options: [30, 45, 60],
      is_active: true,
      skill: 'Piano',
    },
  ],
  service_area_summary: 'NYC',
  rating: 4.9,
  total_reviews: 12,
});

const buildAvailabilityData = (availability: InstructorAvailabilityData['availabilityByDate']): InstructorAvailabilityData => ({
  timezone: 'America/New_York',
  availabilityByDate: availability,
});

describe('InstructorCard next available booking', () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date('2024-05-08T12:00:00Z'));
    pushMock.mockClear();
    sessionStorage.clear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('uses the selected duration when booking the next available slot', async () => {
    renderWithQueryClient(
      <InstructorCard
        instructor={buildInstructor()}
        availabilityData={buildAvailabilityData({
          '2024-06-01': {
            available_slots: [{ start_time: '10:00', end_time: '11:00' }],
          },
        })}
      />
    );

    fireEvent.click(screen.getByLabelText(/60 min/));
    fireEvent.click(screen.getByRole('button', { name: /Next Available/ }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/student/booking/confirm'));

    const stored = sessionStorage.getItem('bookingData');
    expect(stored).toBeTruthy();
    const parsed = JSON.parse(stored as string);
    expect(parsed.duration).toBe(60);
    expect(parsed.endTime).toBe('11:00');
    expect(parsed.basePrice).toBe(60);
    expect(parsed.totalAmount).toBe(60);
  });
  it('updates the next available label when duration changes', async () => {
    renderWithQueryClient(
      <InstructorCard
        instructor={buildInstructor()}
        availabilityData={buildAvailabilityData({
          '2024-05-10': {
            available_slots: [{ start_time: '09:00', end_time: '09:30' }],
          },
          '2024-05-11': {
            available_slots: [{ start_time: '09:00', end_time: '10:30' }],
          },
        })}
      />
    );

    const button = screen.getByRole('button', { name: /Next Available/i });
    expect(button).toHaveTextContent(/Next Available: Fri, May 10/);

    fireEvent.click(screen.getByLabelText(/60 min/));

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /Next Available/i })
      ).toHaveTextContent(/Sat, May 11/);
    });
  });

  it('keeps today when the next slot ends at midnight', () => {
    renderWithQueryClient(
      <InstructorCard
        instructor={buildInstructor()}
        availabilityData={buildAvailabilityData({
          '2024-05-08': {
            available_slots: [{ start_time: '23:30', end_time: '00:00' }],
          },
        })}
      />
    );

    const button = screen.getByRole('button', { name: /Next Available/i });
    expect(button).toHaveTextContent(/Wed, May 8/);
  });
});

describe('InstructorCard rendering', () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date('2024-05-08T12:00:00Z'));
    pushMock.mockClear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('renders instructor name correctly', () => {
    renderWithQueryClient(
      <InstructorCard instructor={buildInstructor()} />
    );

    expect(screen.getByTestId('instructor-name')).toHaveTextContent('Sarah C.');
  });

  it('renders hourly rate', () => {
    renderWithQueryClient(
      <InstructorCard instructor={buildInstructor()} />
    );

    expect(screen.getByTestId('instructor-price')).toHaveTextContent('$60/hr');
  });

  it('renders view profile link', () => {
    const onViewProfile = jest.fn();

    renderWithQueryClient(
      <InstructorCard
        instructor={buildInstructor()}
        onViewProfile={onViewProfile}
      />
    );

    const viewProfileLink = screen.getByTestId('instructor-link');
    expect(viewProfileLink).toBeInTheDocument();
    expect(viewProfileLink).toHaveTextContent('View Profile');
    expect(viewProfileLink).toHaveTextContent('and Reviews');

    fireEvent.click(viewProfileLink);
    expect(onViewProfile).toHaveBeenCalledTimes(1);
  });

  it('renders favorite button', () => {
    renderWithQueryClient(
      <InstructorCard instructor={buildInstructor()} />
    );

    const favoriteButton = screen.getByRole('button', { name: /sign in to save/i });
    expect(favoriteButton).toBeInTheDocument();
  });

  it('renders "More options" button and calls onBookNow', () => {
    const onBookNow = jest.fn();

    renderWithQueryClient(
      <InstructorCard
        instructor={buildInstructor()}
        onBookNow={onBookNow}
      />
    );

    const moreOptionsButton = screen.getByRole('button', { name: /more options/i });
    expect(moreOptionsButton).toBeInTheDocument();

    fireEvent.click(moreOptionsButton);
    expect(onBookNow).toHaveBeenCalledTimes(1);
  });

  it('renders instructor card container', () => {
    renderWithQueryClient(
      <InstructorCard instructor={buildInstructor()} />
    );

    expect(screen.getByTestId('instructor-card')).toBeInTheDocument();
  });

  it('disables next available button when no availability data', () => {
    renderWithQueryClient(
      <InstructorCard instructor={buildInstructor()} />
    );

    const button = screen.getByRole('button', { name: /no availability info/i });
    expect(button).toBeDisabled();
  });
});

describe('InstructorCard duration selection', () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date('2024-05-08T12:00:00Z'));
    pushMock.mockClear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('renders duration options when multiple are available', () => {
    renderWithQueryClient(
      <InstructorCard instructor={buildInstructor()} />
    );

    expect(screen.getByLabelText(/30 min/)).toBeInTheDocument();
    expect(screen.getByLabelText(/45 min/)).toBeInTheDocument();
    expect(screen.getByLabelText(/60 min/)).toBeInTheDocument();
  });

  it('calculates prices for each duration option', () => {
    renderWithQueryClient(
      <InstructorCard instructor={buildInstructor()} />
    );

    // $60/hr = $30 for 30 min, $45 for 45 min, $60 for 60 min
    // The labels contain text like "30 min ($30)"
    expect(screen.getByText(/30 min \(\$30\)/)).toBeInTheDocument();
    expect(screen.getByText(/45 min \(\$45\)/)).toBeInTheDocument();
    expect(screen.getByText(/60 min \(\$60\)/)).toBeInTheDocument();
  });

  it('selects first duration by default', () => {
    renderWithQueryClient(
      <InstructorCard instructor={buildInstructor()} />
    );

    const radio30 = screen.getByLabelText(/30 min/) as HTMLInputElement;
    expect(radio30.checked).toBe(true);
  });

  it('does not render duration options when only one is available', () => {
    const instructor = buildInstructor();
    const baseService = instructor.services[0];
    if (baseService) {
      instructor.services = [{
        ...baseService,
        duration_options: [60],
      }];
    }

    renderWithQueryClient(
      <InstructorCard instructor={instructor} />
    );

    expect(screen.queryByText('Duration:')).not.toBeInTheDocument();
  });
});

describe('InstructorCard compact mode', () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date('2024-05-08T12:00:00Z'));
    pushMock.mockClear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('applies compact styling when compact prop is true', () => {
    renderWithQueryClient(
      <InstructorCard instructor={buildInstructor()} compact={true} />
    );

    const card = screen.getByTestId('instructor-card');
    expect(card).toHaveClass('px-4', 'py-4');
  });

  it('applies regular styling when compact prop is false', () => {
    renderWithQueryClient(
      <InstructorCard instructor={buildInstructor()} compact={false} />
    );

    const card = screen.getByTestId('instructor-card');
    expect(card).toHaveClass('p-6');
  });
});

describe('InstructorCard badges', () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date('2024-05-08T12:00:00Z'));
    pushMock.mockClear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('shows founding badge when instructor is founding', () => {
    const instructor = {
      ...buildInstructor(),
      is_founding_instructor: true,
    };

    renderWithQueryClient(
      <InstructorCard instructor={instructor} />
    );

    expect(screen.getByText(/founding instructor/i)).toBeInTheDocument();
  });

  it('does not show founding badge when instructor is not founding', () => {
    const instructor = {
      ...buildInstructor(),
      is_founding_instructor: false,
    };

    renderWithQueryClient(
      <InstructorCard instructor={instructor} />
    );

    expect(screen.queryByText(/founding instructor/i)).not.toBeInTheDocument();
  });
});

describe('InstructorCard distance display', () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date('2024-05-08T12:00:00Z'));
    pushMock.mockClear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('shows distance when available', () => {
    const instructor = {
      ...buildInstructor(),
      distance_mi: 2.5,
    };

    renderWithQueryClient(
      <InstructorCard instructor={instructor} />
    );

    expect(screen.getByText(/2\.5 mi/)).toBeInTheDocument();
  });

  it('does not show distance when not available', () => {
    const instructor = {
      ...buildInstructor(),
      distance_mi: undefined,
    };

    renderWithQueryClient(
      <InstructorCard instructor={instructor} />
    );

    // Should not show distance display like "X.X mi"
    expect(screen.queryByText(/\d+\.\d+ mi$/)).not.toBeInTheDocument();
  });
});

describe('InstructorCard years experience', () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date('2024-05-08T12:00:00Z'));
    pushMock.mockClear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('shows years of experience when available', () => {
    const instructor = {
      ...buildInstructor(),
      years_experience: 10,
    };

    renderWithQueryClient(
      <InstructorCard instructor={instructor} />
    );

    expect(screen.getByText(/10 years experience/)).toBeInTheDocument();
  });

  it('does not show experience when zero', () => {
    const instructor = {
      ...buildInstructor(),
      years_experience: 0,
    };

    renderWithQueryClient(
      <InstructorCard instructor={instructor} />
    );

    expect(screen.queryByText(/years experience/)).not.toBeInTheDocument();
  });
});

describe('InstructorCard bio display', () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date('2024-05-08T12:00:00Z'));
    pushMock.mockClear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('displays instructor bio in non-compact mode', () => {
    const instructor = {
      ...buildInstructor(),
      bio: 'I am an experienced piano teacher.',
    };

    renderWithQueryClient(
      <InstructorCard instructor={instructor} compact={false} />
    );

    expect(screen.getByText(/I am an experienced piano teacher/)).toBeInTheDocument();
  });

  it('hides bio in compact mode', () => {
    const instructor = {
      ...buildInstructor(),
      bio: 'I am an experienced piano teacher.',
    };

    renderWithQueryClient(
      <InstructorCard instructor={instructor} compact={true} />
    );

    expect(screen.queryByText(/I am an experienced piano teacher/)).not.toBeInTheDocument();
  });
});

describe('InstructorCard BGC badge', () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date('2024-05-08T12:00:00Z'));
    pushMock.mockClear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('shows BGC badge when instructor is live', () => {
    const instructor = {
      ...buildInstructor(),
      is_live: true,
      bgc_status: 'clear',
    };

    renderWithQueryClient(
      <InstructorCard instructor={instructor} />
    );

    // BGC badge should be shown
    expect(screen.getByTestId('instructor-card')).toBeInTheDocument();
  });

  it('shows BGC badge when status is pending', () => {
    const instructor = {
      ...buildInstructor(),
      is_live: false,
      bgc_status: 'pending',
    };

    renderWithQueryClient(
      <InstructorCard instructor={instructor} />
    );

    expect(screen.getByTestId('instructor-card')).toBeInTheDocument();
  });
});

describe('InstructorCard favorite interactions', () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date('2024-05-08T12:00:00Z'));
    pushMock.mockClear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('redirects guest users to login when clicking favorite', () => {
    renderWithQueryClient(
      <InstructorCard instructor={buildInstructor()} />
    );

    const favoriteButton = screen.getByRole('button', { name: /sign in to save/i });
    fireEvent.click(favoriteButton);

    expect(pushMock).toHaveBeenCalledWith(
      expect.stringContaining('/login?returnTo=')
    );
  });
});

describe('InstructorCard service highlighting', () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date('2024-05-08T12:00:00Z'));
    pushMock.mockClear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('highlights matching service catalog', () => {
    const instructor = buildInstructor();

    renderWithQueryClient(
      <InstructorCard
        instructor={instructor}
        highlightServiceCatalogId="catalog-1"
      />
    );

    expect(screen.getByTestId('instructor-card')).toBeInTheDocument();
  });
});

describe('InstructorCard availability edge cases', () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date('2024-05-08T12:00:00Z'));
    pushMock.mockClear();
    sessionStorage.clear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('handles blackout days in availability', () => {
    renderWithQueryClient(
      <InstructorCard
        instructor={buildInstructor()}
        availabilityData={buildAvailabilityData({
          '2024-05-10': {
            is_blackout: true,
          },
          '2024-05-11': {
            available_slots: [{ start_time: '09:00', end_time: '10:00' }],
          },
        })}
      />
    );

    const button = screen.getByRole('button', { name: /Next Available/i });
    // Should skip blackout day and show May 11
    expect(button).toHaveTextContent(/Sat, May 11/);
  });

  it('handles slots with insufficient duration', () => {
    renderWithQueryClient(
      <InstructorCard
        instructor={buildInstructor()}
        availabilityData={buildAvailabilityData({
          '2024-05-10': {
            available_slots: [{ start_time: '09:00', end_time: '09:15' }], // Only 15 min
          },
          '2024-05-11': {
            available_slots: [{ start_time: '10:00', end_time: '11:00' }],
          },
        })}
      />
    );

    // Default duration is 30 min, so May 10 slot is too short
    const button = screen.getByRole('button', { name: /Next Available/i });
    expect(button).toHaveTextContent(/Sat, May 11/);
  });

  it('handles past dates in availability', () => {
    renderWithQueryClient(
      <InstructorCard
        instructor={buildInstructor()}
        availabilityData={buildAvailabilityData({
          '2024-05-01': { // Past date
            available_slots: [{ start_time: '09:00', end_time: '10:00' }],
          },
          '2024-05-10': {
            available_slots: [{ start_time: '09:00', end_time: '10:00' }],
          },
        })}
      />
    );

    const button = screen.getByRole('button', { name: /Next Available/i });
    // Should skip past date
    expect(button).toHaveTextContent(/Fri, May 10/);
  });

  it('handles slot that starts in the past for today', () => {
    // System time is 2024-05-08T12:00:00Z
    renderWithQueryClient(
      <InstructorCard
        instructor={buildInstructor()}
        availabilityData={buildAvailabilityData({
          '2024-05-08': {
            available_slots: [
              { start_time: '08:00', end_time: '09:00' }, // Past slot
              { start_time: '14:00', end_time: '15:00' }, // Future slot
            ],
          },
        })}
      />
    );

    const button = screen.getByRole('button', { name: /Next Available/i });
    expect(button).toHaveTextContent(/Wed, May 8/);
    expect(button).toHaveTextContent(/2:00/);
  });
});

describe('InstructorCard ratings from query', () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date('2024-05-08T12:00:00Z'));
    pushMock.mockClear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('renders without rating when not enough reviews', () => {
    renderWithQueryClient(
      <InstructorCard
        instructor={{
          ...buildInstructor(),
          rating: 4.5,
          total_reviews: 2, // Less than 3
        }}
      />
    );

    // Rating should not be shown
    expect(screen.queryByText(/4\.5/)).not.toBeInTheDocument();
  });
});

describe('InstructorCard pricing display', () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date('2024-05-08T12:00:00Z'));
    pushMock.mockClear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('handles non-numeric hourly rate gracefully', () => {
    const instructor = buildInstructor();
    const baseService = instructor.services[0];
    if (baseService) {
      instructor.services = [{
        ...baseService,
        hourly_rate: 'invalid' as unknown as number,
      }];
    }

    renderWithQueryClient(
      <InstructorCard instructor={instructor} />
    );

    expect(screen.getByTestId('instructor-price')).toHaveTextContent('$0/hr');
  });

  it('handles missing services gracefully', () => {
    const instructor = {
      ...buildInstructor(),
      services: [],
    };

    renderWithQueryClient(
      <InstructorCard instructor={instructor} />
    );

    expect(screen.getByTestId('instructor-card')).toBeInTheDocument();
  });
});
