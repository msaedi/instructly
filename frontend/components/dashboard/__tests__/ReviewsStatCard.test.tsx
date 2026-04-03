import { render, screen } from '@testing-library/react';
import { ReviewsStatCardIcon, ReviewsStatCardValue } from '@/components/dashboard/ReviewsStatCard';

describe('ReviewsStatCard', () => {
  it('renders the populated reviews summary with the outlined star format', () => {
    render(
      <div className="group">
        <ReviewsStatCardValue reviewAverageDisplay="4.4" reviewCount={5} />
        <ReviewsStatCardIcon />
      </div>
    );

    expect(screen.getByTestId('reviews-rating-value')).toHaveTextContent('4.4');
    expect(screen.getByTestId('reviews-rating-count')).toHaveTextContent('(5)');
    expect(screen.queryByTestId('reviews-rating-star')).not.toBeInTheDocument();
    expect(screen.getByTestId('reviews-card-icon')).toBeInTheDocument();
  });

  it('renders the empty-state copy when there are no reviews', () => {
    render(<ReviewsStatCardValue reviewAverageDisplay={null} reviewCount={0} />);

    expect(screen.getByTestId('reviews-summary')).toHaveTextContent('Not yet available');
  });
});
