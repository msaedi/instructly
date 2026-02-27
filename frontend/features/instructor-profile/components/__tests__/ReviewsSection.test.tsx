import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ReviewsSection } from '../ReviewsSection';
import { useRecentReviews } from '@/src/api/services/reviews';
import { useRouter } from 'next/navigation';

jest.mock('@/src/api/services/reviews', () => ({
  useRecentReviews: jest.fn(),
}));

const mockUseRecentReviews = useRecentReviews as jest.Mock;

describe('ReviewsSection', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows a loading skeleton while reviews load', () => {
    mockUseRecentReviews.mockReturnValue({ data: null, isLoading: true, error: null });

    const { container } = render(<ReviewsSection instructorId="inst-1" />);

    expect(screen.getByText(/reviews/i)).toBeInTheDocument();
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });

  it('shows an error state when reviews fail to load', () => {
    mockUseRecentReviews.mockReturnValue({ data: null, isLoading: false, error: new Error('fail') });

    render(<ReviewsSection instructorId="inst-1" />);

    expect(screen.getByText(/unable to load reviews/i)).toBeInTheDocument();
  });

  it('shows a new instructor state when there are no reviews', () => {
    mockUseRecentReviews.mockReturnValue({ data: { reviews: [], total: 0, per_page: 12 }, isLoading: false, error: null });

    render(<ReviewsSection instructorId="inst-1" />);

    expect(screen.getByText(/new instructor/i)).toBeInTheDocument();
    expect(screen.getByText(/no reviews yet/i)).toBeInTheDocument();
  });

  it('renders reviews and links to all reviews', async () => {
    const user = userEvent.setup();
    const push = jest.fn();
    (useRouter as jest.Mock).mockReturnValue({ push });

    mockUseRecentReviews.mockReturnValue({
      data: {
        total: 20,
        per_page: 12,
        reviews: [
          {
            id: 'rev-1',
            rating: 4,
            reviewer_display_name: 'Alex',
            review_text: 'Great lesson',
            created_at: '2024-01-01T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    render(<ReviewsSection instructorId="inst-1" />);

    expect(screen.getByText(/alex/i)).toBeInTheDocument();
    expect(screen.getByText(/great lesson/i)).toBeInTheDocument();
    expect(screen.getByText(/recent reviews \(20\)/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /see all 20 reviews/i }));
    expect(push).toHaveBeenCalledWith('/instructors/inst-1/reviews');
  });

  it('shows error state when data is null without explicit error', () => {
    mockUseRecentReviews.mockReturnValue({ data: null, isLoading: false, error: null });

    render(<ReviewsSection instructorId="inst-1" />);

    expect(screen.getByText(/unable to load reviews/i)).toBeInTheDocument();
  });

  it('renders review without reviewer_display_name', () => {
    mockUseRecentReviews.mockReturnValue({
      data: {
        total: 1,
        per_page: 12,
        reviews: [
          {
            id: 'rev-anon',
            rating: 5,
            reviewer_display_name: '',
            review_text: 'Anonymous review',
            created_at: '2024-06-15T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    render(<ReviewsSection instructorId="inst-1" />);

    expect(screen.getByText(/anonymous review/i)).toBeInTheDocument();
    // Empty reviewer_display_name should not render a name span
    const nameSpans = document.querySelectorAll('span.font-medium.text-sm');
    expect(nameSpans).toHaveLength(0);
  });

  it('renders review without review_text', () => {
    mockUseRecentReviews.mockReturnValue({
      data: {
        total: 1,
        per_page: 12,
        reviews: [
          {
            id: 'rev-no-text',
            rating: 3,
            reviewer_display_name: 'Sam',
            review_text: '',
            created_at: '2024-06-15T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    render(<ReviewsSection instructorId="inst-1" />);

    expect(screen.getByText('Sam')).toBeInTheDocument();
    // The review text paragraph should not be rendered
    const paragraphs = document.querySelectorAll('p.text-sm.text-gray-700');
    expect(paragraphs).toHaveLength(0);
  });

  it('hides "See all" button when total <= per_page', () => {
    mockUseRecentReviews.mockReturnValue({
      data: {
        total: 5,
        per_page: 12,
        reviews: [
          {
            id: 'rev-1',
            rating: 4,
            reviewer_display_name: 'Alex',
            review_text: 'Great',
            created_at: '2024-01-01T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    render(<ReviewsSection instructorId="inst-1" />);

    expect(screen.getByText(/recent reviews \(5\)/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /see all/i })).not.toBeInTheDocument();
  });

  it('handles data with undefined total and per_page', () => {
    mockUseRecentReviews.mockReturnValue({
      data: {
        reviews: [
          {
            id: 'rev-1',
            rating: 4,
            reviewer_display_name: 'Bob',
            review_text: 'Nice',
            created_at: '2024-01-01T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    render(<ReviewsSection instructorId="inst-1" />);

    // total ?? 0 and per_page ?? 0 should both default to 0
    expect(screen.getByText(/recent reviews \(0\)/i)).toBeInTheDocument();
    // 0 > 0 is false, so "See all" button should not show
    expect(screen.queryByRole('button', { name: /see all/i })).not.toBeInTheDocument();
  });

  it('shows empty state when data.reviews is null', () => {
    mockUseRecentReviews.mockReturnValue({
      data: { reviews: null, total: 0, per_page: 12 },
      isLoading: false,
      error: null,
    });

    render(<ReviewsSection instructorId="inst-1" />);

    expect(screen.getByText(/new instructor/i)).toBeInTheDocument();
    expect(screen.getByText(/no reviews yet/i)).toBeInTheDocument();
  });

  it('renders star rating with partial stars correctly', () => {
    mockUseRecentReviews.mockReturnValue({
      data: {
        total: 1,
        per_page: 12,
        reviews: [
          {
            id: 'rev-partial',
            rating: 2,
            reviewer_display_name: 'TestUser',
            review_text: 'Okay lesson',
            created_at: '2024-01-01T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    render(<ReviewsSection instructorId="inst-1" />);

    // Rating of 2 means 2 filled stars and 3 unfilled
    const stars = document.querySelectorAll('svg');
    const filledStars = Array.from(stars).filter(svg =>
      svg.classList.contains('fill-yellow-400')
    );
    const emptyStars = Array.from(stars).filter(svg =>
      svg.classList.contains('fill-gray-200')
    );
    expect(filledStars).toHaveLength(2);
    expect(emptyStars).toHaveLength(3);
  });
});
