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
});
