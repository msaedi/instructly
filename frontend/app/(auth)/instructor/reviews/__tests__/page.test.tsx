/**
 * @jest-environment jsdom
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import InstructorReviewsPage from '../page';

const mockUseAuth = jest.fn();
const mockUseInstructorRatingsQuery = jest.fn();
const mockUseInstructorReviews = jest.fn();
const mockMutateAsync = jest.fn();

function MockUserProfileDropdown() {
  return <div>User menu</div>;
}

jest.mock('@/components/UserProfileDropdown', () => MockUserProfileDropdown);

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => mockUseAuth(),
}));

jest.mock('@/hooks/queries/useRatings', () => ({
  useInstructorRatingsQuery: (...args: unknown[]) => mockUseInstructorRatingsQuery(...args),
}));

jest.mock('@/features/instructor-profile/hooks/useInstructorReviews', () => ({
  useInstructorReviews: (...args: unknown[]) => mockUseInstructorReviews(...args),
}));

jest.mock('@/src/api/services/reviews', () => ({
  useRespondToReview: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
    variables: undefined,
  }),
}));

jest.mock('../../_embedded/EmbeddedContext', () => ({
  useEmbedded: () => false,
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <InstructorReviewsPage />
    </QueryClientProvider>
  );
}

describe('InstructorReviewsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2026-03-22T12:00:00Z'));

    mockUseAuth.mockReturnValue({
      user: { id: 'instructor-1' },
      isLoading: false,
    });

    mockUseInstructorRatingsQuery.mockReturnValue({
      data: {
        overall: {
          rating: 4,
          display_rating: '4.0★',
          total_reviews: 5,
        },
        confidence_level: 'establishing',
      },
      isLoading: false,
    });

    mockUseInstructorReviews.mockReturnValue({
      data: {
        reviews: [
          {
            id: 'review-1',
            rating: 5,
            review_text: 'Professional and friendly instructor.',
            created_at: '2026-03-22T08:00:00Z',
            instructor_service_id: 'service-1',
            reviewer_display_name: 'Sophia Brown',
            reviewer_first_name: 'Sophia',
            reviewer_last_initial: 'B',
            response: null,
          },
          {
            id: 'review-2',
            rating: 3,
            review_text: null,
            created_at: '2026-03-10T12:00:00Z',
            instructor_service_id: 'service-1',
            reviewer_display_name: 'Alex Williams',
            reviewer_first_name: 'Alex',
            reviewer_last_initial: 'W',
            response: {
              id: 'response-1',
              review_id: 'review-2',
              instructor_id: 'instructor-1',
              response_text: 'Thanks for the thoughtful note.',
              created_at: '2026-03-11T12:00:00Z',
            },
          },
        ],
        total: 5,
        page: 1,
        per_page: 6,
        has_prev: false,
        has_next: false,
      },
      isLoading: false,
      isFetching: false,
      error: null,
    });
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('renders the redesigned summary, timestamps, reviewer names, and reply states', () => {
    const { container } = renderPage();

    expect(screen.getByText('4.0')).toBeInTheDocument();
    expect(screen.getByText('(5 reviews)')).toBeInTheDocument();
    expect(screen.queryByText('(4.00)')).not.toBeInTheDocument();

    expect(screen.getByText('Sophia B.')).toBeInTheDocument();
    expect(screen.getByText('about 4 hours ago')).toBeInTheDocument();
    expect(screen.getByText('Alex W.')).toBeInTheDocument();
    expect(screen.getByText('Mar 10, 2026')).toBeInTheDocument();

    expect(screen.getByRole('button', { name: 'Reply' })).toBeInTheDocument();
    expect(screen.getByText('Instructor reply')).toBeInTheDocument();
    expect(screen.getByText('Thanks for the thoughtful note.')).toBeInTheDocument();
    expect(screen.getByText('Replied')).toBeInTheDocument();

    const metadataRow = container.querySelector('article > div.flex.items-center.gap-3');
    expect(metadataRow).toBeInTheDocument();
  });

  it('updates rating and comments-only filters through the summary controls', async () => {
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    renderPage();

    await user.selectOptions(screen.getByLabelText('All reviews filter'), '4');
    expect(mockUseInstructorReviews).toHaveBeenLastCalledWith(
      'instructor-1',
      1,
      6,
      { rating: 4 }
    );

    await user.click(screen.getByRole('checkbox', { name: 'With comments only' }));
    expect(mockUseInstructorReviews).toHaveBeenLastCalledWith(
      'instructor-1',
      1,
      6,
      { rating: 4, withText: true }
    );
  });

  it('opens a reply form for reviews without an existing response', async () => {
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    renderPage();

    await user.click(screen.getByRole('button', { name: 'Reply' }));

    expect(screen.getByLabelText('Reply to Sophia B.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send reply' })).toBeInTheDocument();
  });
});
