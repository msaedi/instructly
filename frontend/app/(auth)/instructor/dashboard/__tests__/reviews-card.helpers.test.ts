import { getReviewFillPercent, getReviewsCardSummary } from '@/lib/dashboardReviews';

describe('dashboard reviews card helpers', () => {
  it('formats inline review summary text', () => {
    expect(getReviewsCardSummary('4.5', 3)).toBe('4.5★ (3)');
    expect(getReviewsCardSummary('5.0', 1)).toBe('5.0★ (1)');
    expect(getReviewsCardSummary(null, 0)).toBe('Not yet available');
  });

  it('computes proportional star fill percentages', () => {
    expect(getReviewFillPercent(5)).toBe(100);
    expect(getReviewFillPercent(4.5)).toBe(90);
    expect(getReviewFillPercent(3)).toBe(60);
    expect(getReviewFillPercent(null)).toBe(0);
  });
});
