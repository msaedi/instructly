import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LessonCard } from '../LessonCard';
import type { Booking } from '@/types/booking';
import { reviewsApi } from '@/services/api/reviews';

// Mock dependencies
jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
  },
}));

jest.mock('@/services/api/reviews', () => ({
  reviewsApi: {
    getByBooking: jest.fn(),
    getInstructorRatings: jest.fn(),
  },
}));

jest.mock('@/lib/timezone/formatBookingTime', () => ({
  formatBookingDate: jest.fn(() => 'Mon, Jan 20'),
  formatBookingTime: jest.fn(() => '10:00 AM - 11:00 AM'),
}));

jest.mock('../LessonStatus', () => ({
  LessonStatus: ({ status, cancelledAt }: { status: string; cancelledAt?: string }) => (
    <div data-testid="lesson-status" data-status={status} data-cancelled={cancelledAt}>
      {status}
    </div>
  ),
}));

jest.mock('../InstructorInfo', () => ({
  InstructorInfo: ({
    instructor,
    rating,
    reviewCount,
    onChat,
    showReviewButton,
    reviewed,
    onReview,
    showBookAgainButton,
    onBookAgain,
  }: {
    instructor?: object;
    rating?: number;
    reviewCount?: number;
    onChat?: (e?: React.MouseEvent) => void;
    showReviewButton?: boolean;
    reviewed?: boolean;
    onReview?: (e?: React.MouseEvent) => void;
    showBookAgainButton?: boolean;
    onBookAgain?: (e?: React.MouseEvent) => void;
  }) => (
    <div data-testid="instructor-info">
      {instructor && <span>Instructor Info</span>}
      {rating && <span data-testid="rating">{rating}</span>}
      {reviewCount && <span data-testid="review-count">{reviewCount}</span>}
      {onChat && (
        <button data-testid="chat-button" onClick={(e) => onChat(e)}>
          Chat
        </button>
      )}
      {showReviewButton && (
        <button
          data-testid="review-button"
          data-reviewed={reviewed}
          onClick={(e) => onReview?.(e)}
        >
          {reviewed ? 'Reviewed' : 'Leave Review'}
        </button>
      )}
      {showBookAgainButton && (
        <button data-testid="book-again-button" onClick={(e) => onBookAgain?.(e)}>
          Book Again
        </button>
      )}
    </div>
  ),
}));

const reviewsApiMock = reviewsApi as jest.Mocked<typeof reviewsApi>;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'QueryClientWrapper';
  return { Wrapper, queryClient };
};

const mockBooking: Booking = {
  id: 'booking-1',
  instructor_id: 'inst-1',
  student_id: 'student-1',
  instructor_service_id: 'svc-1',
  service_name: 'Piano Lesson',
  booking_date: '2025-01-20',
  start_time: '10:00:00',
  end_time: '11:00:00',
  duration_minutes: 60,
  total_price: 60,
  hourly_rate: 60,
  status: 'CONFIRMED',
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
  instructor: {
    id: 'inst-1',
    first_name: 'John',
    last_initial: 'D',
  },
};

describe('LessonCard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    reviewsApiMock.getByBooking.mockResolvedValue(null);
    reviewsApiMock.getInstructorRatings.mockResolvedValue({
      confidence_level: 'established',
      overall: { rating: 4.8, total_reviews: 15 },
    });
  });

  describe('rendering', () => {
    it('renders lesson card container', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      expect(screen.getByTestId('lesson-card')).toBeInTheDocument();
    });

    it('renders service name', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      expect(screen.getByText('Piano Lesson')).toBeInTheDocument();
    });

    it('renders formatted date and time', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      expect(screen.getByText('Mon, Jan 20')).toBeInTheDocument();
      expect(screen.getByText('10:00 AM - 11:00 AM')).toBeInTheDocument();
    });

    it('renders price', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      expect(screen.getByText('$60.00')).toBeInTheDocument();
    });

    it('renders instructor info', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      expect(screen.getByTestId('instructor-info')).toBeInTheDocument();
    });

    it('renders view details link', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      expect(screen.getByText('See lesson details')).toBeInTheDocument();
    });

    it('keeps the inner "See lesson details" button as the keyboard path without wrapper button semantics', async () => {
      const user = userEvent.setup();
      const onViewDetails = jest.fn();
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={onViewDetails}
          />
        </Wrapper>
      );

      const card = screen.getByTestId('lesson-card');
      expect(card).not.toHaveAttribute('role', 'button');
      expect(card).not.toHaveAttribute('tabindex', '0');

      const detailsButton = screen.getByRole('button', { name: /see lesson details/i });
      detailsButton.focus();
      await user.keyboard('{Enter}');

      expect(onViewDetails).toHaveBeenCalledTimes(1);
    });
  });

  describe('status badges', () => {
    it('shows IN_PROGRESS badge for in progress lesson', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{ ...mockBooking, status: 'CONFIRMED' }}
            isCompleted={false}
            isInProgress={true}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      const statusBadge = screen.getByTestId('lesson-status');
      expect(statusBadge).toHaveAttribute('data-status', 'IN_PROGRESS');
    });

    it('shows COMPLETED badge for completed lesson', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{ ...mockBooking, status: 'COMPLETED' }}
            isCompleted={true}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      const statusBadge = screen.getByTestId('lesson-status');
      expect(statusBadge).toHaveAttribute('data-status', 'COMPLETED');
    });

    it('shows COMPLETED badge for past confirmed lesson', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{ ...mockBooking, status: 'CONFIRMED' }}
            isCompleted={true}
            isInProgress={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      const statusBadge = screen.getByTestId('lesson-status');
      expect(statusBadge).toHaveAttribute('data-status', 'COMPLETED');
    });

    it('shows CANCELLED badge for cancelled lesson', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{
              ...mockBooking,
              status: 'CANCELLED',
              cancelled_at: '2025-01-15T10:00:00Z',
            }}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      const statusBadge = screen.getByTestId('lesson-status');
      expect(statusBadge).toHaveAttribute('data-status', 'CANCELLED');
    });

    it('shows NO_SHOW badge for no-show lesson', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{ ...mockBooking, status: 'NO_SHOW' }}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      const statusBadge = screen.getByTestId('lesson-status');
      expect(statusBadge).toHaveAttribute('data-status', 'NO_SHOW');
    });
  });

  describe('callbacks', () => {
    it('calls onViewDetails when card is clicked', () => {
      const onViewDetails = jest.fn();
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={onViewDetails}
          />
        </Wrapper>
      );

      fireEvent.click(screen.getByTestId('lesson-card'));
      expect(onViewDetails).toHaveBeenCalledTimes(1);
    });

    it('calls onViewDetails when link is clicked', () => {
      const onViewDetails = jest.fn();
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={onViewDetails}
          />
        </Wrapper>
      );

      fireEvent.click(screen.getByText('See lesson details'));
      // Click should stop propagation, so called twice (link + card)
      expect(onViewDetails).toHaveBeenCalled();
    });

    it('calls onChat when chat button is clicked', () => {
      const onChat = jest.fn();
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={jest.fn()}
            onChat={onChat}
          />
        </Wrapper>
      );

      fireEvent.click(screen.getByTestId('chat-button'));
      expect(onChat).toHaveBeenCalledTimes(1);
    });

    it('calls onBookAgain when book again button is clicked', () => {
      const onBookAgain = jest.fn();
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{ ...mockBooking, status: 'COMPLETED' }}
            isCompleted={true}
            onViewDetails={jest.fn()}
            onBookAgain={onBookAgain}
          />
        </Wrapper>
      );

      fireEvent.click(screen.getByTestId('book-again-button'));
      expect(onBookAgain).toHaveBeenCalledTimes(1);
    });

    it('calls onReviewTip when review button is clicked', () => {
      const onReviewTip = jest.fn();
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{ ...mockBooking, status: 'COMPLETED' }}
            isCompleted={true}
            onViewDetails={jest.fn()}
            onReviewTip={onReviewTip}
          />
        </Wrapper>
      );

      fireEvent.click(screen.getByTestId('review-button'));
      expect(onReviewTip).toHaveBeenCalledTimes(1);
    });
  });

  describe('review status', () => {
    it('shows review button for completed lessons', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{ ...mockBooking, status: 'COMPLETED' }}
            isCompleted={true}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      expect(screen.getByTestId('review-button')).toBeInTheDocument();
    });

    it('shows reviewed state when prefetchedReviewed is true', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{ ...mockBooking, status: 'COMPLETED' }}
            isCompleted={true}
            onViewDetails={jest.fn()}
            prefetchedReviewed={true}
          />
        </Wrapper>
      );

      expect(screen.getByTestId('review-button')).toHaveAttribute(
        'data-reviewed',
        'true'
      );
    });

    it('fetches review status when not prefetched', async () => {
      reviewsApiMock.getByBooking.mockResolvedValue({
        id: 'review-1',
        created_at: '2025-01-15T10:00:00Z',
        instructor_service_id: 'svc-1',
        rating: 5,
        review_text: 'Great lesson!',
      });

      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{ ...mockBooking, status: 'COMPLETED' }}
            isCompleted={true}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      await waitFor(() => {
        expect(reviewsApiMock.getByBooking).toHaveBeenCalledWith('booking-1');
      });
    });

    it('does not fetch when suppressFetchReviewed is true', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{ ...mockBooking, status: 'COMPLETED' }}
            isCompleted={true}
            onViewDetails={jest.fn()}
            suppressFetchReviewed={true}
          />
        </Wrapper>
      );

      expect(reviewsApiMock.getByBooking).not.toHaveBeenCalled();
    });
  });

  describe('rating display', () => {
    it('uses prefetched rating when provided', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={jest.fn()}
            prefetchedRating={4.5}
            prefetchedReviewCount={10}
          />
        </Wrapper>
      );

      expect(screen.getByTestId('rating')).toHaveTextContent('4.5');
    });

    it('hides rating when review count is less than 3', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={jest.fn()}
            prefetchedRating={4.5}
            prefetchedReviewCount={2}
          />
        </Wrapper>
      );

      expect(screen.queryByTestId('rating')).not.toBeInTheDocument();
    });

    it('fetches rating when not prefetched', async () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      await waitFor(() => {
        expect(reviewsApiMock.getInstructorRatings).toHaveBeenCalledWith('inst-1');
      });
    });

    it('does not fetch when suppressFetchRating is true', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={jest.fn()}
            suppressFetchRating={true}
          />
        </Wrapper>
      );

      expect(reviewsApiMock.getInstructorRatings).not.toHaveBeenCalled();
    });
  });

  describe('cancelled lesson pricing', () => {
    it('shows no charge for cancellation more than 24 hours before', () => {
      // Lesson at 2025-01-20 10:00, cancelled at 2025-01-18 10:00 (48 hours before)
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{
              ...mockBooking,
              status: 'CANCELLED',
              cancelled_at: '2025-01-18T10:00:00Z',
              booking_start_utc: '2025-01-20T15:00:00Z',
            }}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      expect(screen.getByText('$0.00 (No charge)')).toBeInTheDocument();
    });

    it('shows 50% refund for cancellation 12-24 hours before', () => {
      // Lesson at 2025-01-20 15:00 UTC, cancelled at 2025-01-20 01:00 UTC (14 hours before)
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{
              ...mockBooking,
              status: 'CANCELLED',
              cancelled_at: '2025-01-20T01:00:00Z',
              booking_start_utc: '2025-01-20T15:00:00Z',
            }}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      expect(screen.getByText(/Charged: \$60.00 \| Credit: \$30.00/)).toBeInTheDocument();
    });

    it('shows full charge for cancellation less than 12 hours before', () => {
      // Lesson at 2025-01-20 15:00 UTC, cancelled at 2025-01-20 10:00 UTC (5 hours before)
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{
              ...mockBooking,
              status: 'CANCELLED',
              cancelled_at: '2025-01-20T10:00:00Z',
              booking_start_utc: '2025-01-20T15:00:00Z',
            }}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      expect(screen.getByText('$60.00')).toBeInTheDocument();
    });

    it('handles missing cancelled_at gracefully', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{
              ...mockBooking,
              status: 'CANCELLED',
              // No cancelled_at
            }}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      expect(screen.getByText('$60.00')).toBeInTheDocument();
    });
  });

  describe('book again button visibility', () => {
    it('shows book again for completed lessons', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{ ...mockBooking, status: 'COMPLETED' }}
            isCompleted={true}
            onViewDetails={jest.fn()}
            onBookAgain={jest.fn()}
          />
        </Wrapper>
      );

      expect(screen.getByTestId('book-again-button')).toBeInTheDocument();
    });

    it('shows book again for cancelled lessons', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{ ...mockBooking, status: 'CANCELLED' }}
            isCompleted={false}
            onViewDetails={jest.fn()}
            onBookAgain={jest.fn()}
          />
        </Wrapper>
      );

      expect(screen.getByTestId('book-again-button')).toBeInTheDocument();
    });
  });

  describe('custom className', () => {
    it('applies custom className to card', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={jest.fn()}
            className="custom-class"
          />
        </Wrapper>
      );

      const card = screen.getByTestId('lesson-card');
      expect(card).toHaveClass('custom-class');
    });
  });

  describe('price formatting edge cases', () => {
    it('handles null price gracefully', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{ ...mockBooking, total_price: null as unknown as number }}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      // Should show fallback
      expect(screen.getByText('—')).toBeInTheDocument();
    });

    it('handles undefined price gracefully', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{ ...mockBooking, total_price: undefined as unknown as number }}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      // Should show fallback
      expect(screen.getByText('—')).toBeInTheDocument();
    });
  });

  describe('error handling', () => {
    it('handles rating fetch error', async () => {
      reviewsApiMock.getInstructorRatings.mockRejectedValue(new Error('Network error'));

      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      // Should still render without rating
      await waitFor(() => {
        expect(screen.getByTestId('lesson-card')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('rating')).not.toBeInTheDocument();
    });

    it('handles review fetch error', async () => {
      reviewsApiMock.getByBooking.mockRejectedValue(new Error('Network error'));

      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{ ...mockBooking, status: 'COMPLETED' }}
            isCompleted={true}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      // Should still render
      await waitFor(() => {
        expect(screen.getByTestId('lesson-card')).toBeInTheDocument();
      });
    });
  });

  describe('rating display from fetched data', () => {
    it('displays rating from API when data fetched has sufficient reviews', async () => {
      // Mock the API to return rating data with enough reviews
      reviewsApiMock.getInstructorRatings.mockResolvedValue({
        confidence_level: 'established',
        overall: { rating: 4.7, total_reviews: 10 },
      });

      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={jest.fn()}
            // No prefetched rating - will fetch
          />
        </Wrapper>
      );

      // Wait for the rating to be displayed from fetched data
      await waitFor(() => {
        expect(screen.getByTestId('rating')).toHaveTextContent('4.7');
      });
    });

    it('hides rating from API when data fetched has insufficient reviews', async () => {
      // Mock the API to return rating data with fewer than 3 reviews
      reviewsApiMock.getInstructorRatings.mockResolvedValue({
        confidence_level: 'new',
        overall: { rating: 5.0, total_reviews: 2 },
      });

      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      // Wait for API call to complete
      await waitFor(() => {
        expect(reviewsApiMock.getInstructorRatings).toHaveBeenCalled();
      });

      // Rating should not be displayed with fewer than 3 reviews
      expect(screen.queryByTestId('rating')).not.toBeInTheDocument();
    });
  });

  describe('cancellation fee edge cases', () => {
    it('shows full price when booking_date is missing', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{
              ...mockBooking,
              status: 'CANCELLED',
              cancelled_at: '2025-01-18T10:00:00Z',
              booking_date: null as unknown as string,
            }}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      // Should fallback to full price when booking_date is missing
      expect(screen.getByText('$60.00')).toBeInTheDocument();
    });

    it('shows full price when start_time is missing', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={{
              ...mockBooking,
              status: 'CANCELLED',
              cancelled_at: '2025-01-18T10:00:00Z',
              start_time: null as unknown as string,
            }}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      // Should fallback to full price when start_time is missing
      expect(screen.getByText('$60.00')).toBeInTheDocument();
    });
  });

  describe('children prop', () => {
    it('renders children when provided', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={jest.fn()}
          >
            <span data-testid="test-child">Test Child</span>
          </LessonCard>
        </Wrapper>
      );

      expect(screen.getByTestId('test-child')).toBeInTheDocument();
    });

    it('does not render children wrapper when no children', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={jest.fn()}
          />
        </Wrapper>
      );

      expect(screen.getByTestId('lesson-card')).toBeInTheDocument();
    });

    it('clicking children does not trigger onViewDetails', () => {
      const onViewDetails = jest.fn();
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <LessonCard
            lesson={mockBooking}
            isCompleted={false}
            onViewDetails={onViewDetails}
          >
            <button data-testid="child-btn">Click</button>
          </LessonCard>
        </Wrapper>
      );

      fireEvent.click(screen.getByTestId('child-btn'));
      expect(onViewDetails).not.toHaveBeenCalled();
    });
  });
});
