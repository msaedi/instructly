/**
 * @jest-environment jsdom
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
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

beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, 'hasPointerCapture', {
    configurable: true,
    value: jest.fn(() => false),
  });
  Object.defineProperty(HTMLElement.prototype, 'setPointerCapture', {
    configurable: true,
    value: jest.fn(),
  });
  Object.defineProperty(HTMLElement.prototype, 'releasePointerCapture', {
    configurable: true,
    value: jest.fn(),
  });
});

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
          {
            id: 'review-3',
            rating: 4,
            review_text: 'Great pacing and communication.',
            created_at: '2026-03-18T12:00:00Z',
            instructor_service_id: 'service-1',
            reviewer_display_name: 'Jordan Lee',
            reviewer_first_name: 'Jordan',
            reviewer_last_initial: 'L',
            response: {
              id: 'response-2',
              review_id: 'review-3',
              instructor_id: 'instructor-1',
              response_text: 'Thank you for the kind words.',
              created_at: '2026-03-19T12:00:00Z',
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

  it('renders the redesigned summary, timestamps, reviewer names, amber stars, and reply states', () => {
    const { container } = renderPage();

    expect(screen.getByText('4.0')).toBeInTheDocument();
    expect(screen.getByText('(5 reviews)')).toBeInTheDocument();
    expect(screen.queryByText('(4.00)')).not.toBeInTheDocument();

    expect(screen.getByText('Sophia B.')).toBeInTheDocument();
    expect(screen.getByText('about 4 hours ago')).toBeInTheDocument();
    expect(screen.getByText('Alex W.')).toBeInTheDocument();
    expect(screen.getByText('Mar 10, 2026')).toBeInTheDocument();
    expect(screen.getByText('Jordan L.')).toBeInTheDocument();

    expect(screen.getByRole('button', { name: 'Reply' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    const responseLabels = screen.getAllByText('Instructor reply');
    expect(responseLabels[0]).toHaveClass('text-sm', 'font-medium');
    expect(responseLabels[0]).not.toHaveClass('uppercase');
    expect(screen.getByText('Thanks for the thoughtful note.')).toBeInTheDocument();
    expect(screen.getByText('Thank you for the kind words.')).toBeInTheDocument();
    expect(screen.queryByText('Replied')).not.toBeInTheDocument();
    expect(screen.queryByText('No written feedback')).not.toBeInTheDocument();

    const reviewMeta = screen.getByTestId('review-meta-review-1');
    expect(reviewMeta).toHaveClass('flex', 'flex-col', 'items-end');
    expect(within(reviewMeta).getByText('about 4 hours ago')).toBeInTheDocument();
    expect(within(reviewMeta).getByRole('button', { name: 'Reply' })).toBeInTheDocument();

    const amberStars = Array.from(container.querySelectorAll('svg')).filter((icon) =>
      icon.classList.contains('text-(--color-star-amber)')
    );
    expect(amberStars.length).toBeGreaterThan(0);

    const secondReviewCard = screen.getByText('Alex W.').closest('article');
    expect(secondReviewCard).not.toBeNull();
    expect(
      within(secondReviewCard as HTMLElement).queryByRole('button', { name: /Reply|Edit/i })
    ).not.toBeInTheDocument();
  });

  it('updates rating and comments-only filters through the summary controls', async () => {
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    renderPage();

    const ratingFilter = screen.getByRole('combobox', { name: 'All reviews filter' });
    expect(ratingFilter).toHaveStyle({ backgroundColor: '#FFFFFF' });

    await user.click(ratingFilter);
    await user.click(screen.getByRole('option', { name: '4 stars' }));

    expect(mockUseInstructorReviews).toHaveBeenLastCalledWith(
      'instructor-1',
      1,
      6,
      { rating: 4 }
    );

    const commentsToggle = screen.getByRole('switch', { name: 'With comments' });
    const commentsPill = commentsToggle.parentElement;

    expect(commentsToggle).toHaveAttribute('aria-checked', 'false');
    expect(commentsPill).toHaveClass('border-gray-300', 'bg-white');

    await user.click(commentsToggle);

    expect(commentsToggle).toHaveAttribute('aria-checked', 'true');
    expect(commentsPill).toHaveClass('border-(--color-brand)', 'bg-(--color-brand-lavender)', 'text-(--color-brand)');
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

  it('prefills the existing response when editing a written review reply', async () => {
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    renderPage();

    await user.click(screen.getByRole('button', { name: 'Edit' }));

    expect(screen.getByLabelText('Reply to Jordan L.')).toHaveValue(
      'Thank you for the kind words.'
    );
    expect(screen.getByRole('button', { name: 'Save reply' })).toBeInTheDocument();
  });
});
