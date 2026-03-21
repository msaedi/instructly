export function getReviewFillPercent(rating?: number | null): number {
  if (typeof rating !== 'number' || Number.isNaN(rating)) {
    return 0;
  }

  return Math.max(0, Math.min(100, (rating / 5) * 100));
}

export function getReviewsCardSummary(reviewAverageDisplay: string | null, reviewCount: number): string {
  if (reviewCount > 0 && reviewAverageDisplay) {
    return `${reviewAverageDisplay}★ (${reviewCount})`;
  }

  return 'Not yet available';
}
