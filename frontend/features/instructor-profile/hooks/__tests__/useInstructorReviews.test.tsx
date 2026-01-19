import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useInstructorReviews } from '../useInstructorReviews';
import { reviewsApi } from '@/services/api/reviews';
import type { ReactNode } from 'react';

// Mock the reviews API
jest.mock('@/services/api/reviews', () => ({
  reviewsApi: {
    getRecent: jest.fn(),
  },
}));

const reviewsApiMock = reviewsApi as jest.Mocked<typeof reviewsApi>;

// Create wrapper with QueryClient
const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return Wrapper;
};

describe('useInstructorReviews', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  const mockReviewsResponse = {
    reviews: [
      {
        id: 'rev-1',
        instructor_service_id: 'svc-1',
        rating: 5,
        review_text: 'Great teacher!',
        reviewer_display_name: 'John',
        created_at: '2025-01-15',
      },
      {
        id: 'rev-2',
        instructor_service_id: 'svc-1',
        rating: 4,
        review_text: 'Good lesson',
        reviewer_display_name: 'Jane',
        created_at: '2025-01-14',
      },
    ],
    total: 2,
    page: 1,
    per_page: 12,
    has_next: false,
    has_prev: false,
  };

  it('fetches reviews with default parameters', async () => {
    reviewsApiMock.getRecent.mockResolvedValue(mockReviewsResponse);

    const { result } = renderHook(
      () => useInstructorReviews('instructor-123'),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(reviewsApiMock.getRecent).toHaveBeenCalledWith(
      'instructor-123',
      undefined,
      12,
      1,
      undefined
    );
    expect(result.current.data).toEqual(mockReviewsResponse);
  });

  it('fetches reviews with custom page and limit', async () => {
    reviewsApiMock.getRecent.mockResolvedValue(mockReviewsResponse);

    renderHook(
      () => useInstructorReviews('instructor-123', 2, 20),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(reviewsApiMock.getRecent).toHaveBeenCalledWith(
        'instructor-123',
        undefined,
        20,
        2,
        undefined
      );
    });
  });

  it('fetches reviews with minRating option', async () => {
    reviewsApiMock.getRecent.mockResolvedValue(mockReviewsResponse);

    renderHook(
      () => useInstructorReviews('instructor-123', 1, 12, { minRating: 4 }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(reviewsApiMock.getRecent).toHaveBeenCalledWith(
        'instructor-123',
        undefined,
        12,
        1,
        { minRating: 4 }
      );
    });
  });

  it('fetches reviews with rating filter', async () => {
    reviewsApiMock.getRecent.mockResolvedValue(mockReviewsResponse);

    renderHook(
      () => useInstructorReviews('instructor-123', 1, 12, { rating: 5 }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(reviewsApiMock.getRecent).toHaveBeenCalledWith(
        'instructor-123',
        undefined,
        12,
        1,
        { rating: 5 }
      );
    });
  });

  it('fetches reviews with withText filter', async () => {
    reviewsApiMock.getRecent.mockResolvedValue(mockReviewsResponse);

    renderHook(
      () => useInstructorReviews('instructor-123', 1, 12, { withText: true }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(reviewsApiMock.getRecent).toHaveBeenCalledWith(
        'instructor-123',
        undefined,
        12,
        1,
        { withText: true }
      );
    });
  });

  it('fetches reviews with instructorServiceId', async () => {
    reviewsApiMock.getRecent.mockResolvedValue(mockReviewsResponse);

    renderHook(
      () => useInstructorReviews('instructor-123', 1, 12, { instructorServiceId: 'svc-1' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(reviewsApiMock.getRecent).toHaveBeenCalledWith(
        'instructor-123',
        'svc-1',
        12,
        1,
        undefined
      );
    });
  });

  it('does not fetch when instructorId is empty', async () => {
    const { result } = renderHook(
      () => useInstructorReviews(''),
      { wrapper: createWrapper() }
    );

    expect(result.current.isLoading).toBe(false);
    expect(result.current.isFetching).toBe(false);
    expect(reviewsApiMock.getRecent).not.toHaveBeenCalled();
  });

  it('handles fetch error', async () => {
    reviewsApiMock.getRecent.mockRejectedValue(new Error('Failed to fetch reviews'));

    const { result } = renderHook(
      () => useInstructorReviews('instructor-error'),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toBeDefined();
  });

  it('combines multiple filter options', async () => {
    reviewsApiMock.getRecent.mockResolvedValue(mockReviewsResponse);

    renderHook(
      () => useInstructorReviews('instructor-123', 1, 12, {
        minRating: 3,
        rating: 5,
        withText: true,
        instructorServiceId: 'svc-1',
      }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(reviewsApiMock.getRecent).toHaveBeenCalledWith(
        'instructor-123',
        'svc-1',
        12,
        1,
        { minRating: 3, rating: 5, withText: true }
      );
    });
  });

  it('returns loading state initially', () => {
    reviewsApiMock.getRecent.mockImplementation(() => new Promise(() => {}));

    const { result } = renderHook(
      () => useInstructorReviews('instructor-loading'),
      { wrapper: createWrapper() }
    );

    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });
});
