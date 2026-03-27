'use client';

import { Star as PhosphorStar } from '@phosphor-icons/react';

type ReviewsStatCardValueProps = {
  reviewAverageDisplay: string | null;
  reviewCount: number;
};

export function ReviewsStatCardValue({
  reviewAverageDisplay,
  reviewCount,
}: ReviewsStatCardValueProps) {
  if (!(reviewCount > 0 && reviewAverageDisplay)) {
    return (
      <p
        className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white group-hover:text-gray-900 dark:group-hover:text-white"
        data-testid="reviews-summary"
      >
        Not yet available
      </p>
    );
  }

  return (
    <div
      className="mt-1 flex items-center gap-1.5 text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white group-hover:text-gray-900 dark:group-hover:text-white"
      data-testid="reviews-summary"
    >
      <span data-testid="reviews-rating-value">{reviewAverageDisplay}</span>
      <PhosphorStar
        data-testid="reviews-rating-star"
        weight="regular"
        className="h-5 w-5 sm:h-6 sm:w-6 text-(--color-brand-dark)"
        aria-hidden="true"
      />
      <span data-testid="reviews-rating-count">({reviewCount})</span>
    </div>
  );
}

export function ReviewsStatCardIcon() {
  return (
    <PhosphorStar
      data-testid="reviews-card-icon"
      weight="regular"
      className="w-5 h-5 sm:w-6 sm:h-6 text-(--color-brand-dark)"
      aria-hidden="true"
    />
  );
}
