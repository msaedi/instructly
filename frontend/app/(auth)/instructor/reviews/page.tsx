'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useQueryClient } from '@tanstack/react-query';
import { format, formatDistanceToNow } from 'date-fns';
import { Star as PhosphorStar } from '@phosphor-icons/react';
import { ArrowLeft, Star } from 'lucide-react';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { SectionHeroCard } from '@/components/dashboard/SectionHeroCard';
import { ToggleSwitch } from '@/components/ui/ToggleSwitch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useInstructorReviews } from '@/features/instructor-profile/hooks/useInstructorReviews';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useInstructorRatingsQuery } from '@/hooks/queries/useRatings';
import { getReviewFillPercent } from '@/lib/dashboardReviews';
import { formatStudentDisplayName } from '@/lib/studentName';
import { useRespondToReview } from '@/src/api/services/reviews';
import { queryKeys } from '@/src/api/queryKeys';

import { useEmbedded } from '../_embedded/EmbeddedContext';

type RatingFilter = 'all' | 5 | 4 | 3 | 2 | 1;

function SummaryRatingStar({ rating }: { rating?: number | null }) {
  const fillPercent = getReviewFillPercent(rating);

  return (
    <div className="relative h-10 w-10 shrink-0" aria-hidden="true">
      <PhosphorStar
        weight="regular"
        className="absolute inset-0 h-full w-full text-(--color-star-amber)"
      />
      <div className="absolute inset-y-0 left-0 overflow-hidden" style={{ width: `${fillPercent}%` }}>
        <PhosphorStar weight="fill" className="h-full w-full text-(--color-star-amber)" />
      </div>
    </div>
  );
}

function ReviewStars({ rating }: { rating: number }) {
  return (
    <div className="flex items-center gap-0.5" aria-label={`${rating} star rating`}>
      {[1, 2, 3, 4, 5].map((value) => (
        <PhosphorStar
          key={value}
          weight={value <= rating ? 'fill' : 'regular'}
          className="h-4 w-4 text-(--color-star-amber)"
        />
      ))}
    </div>
  );
}

function formatReviewTimestamp(createdAt: string): string {
  const createdDate = new Date(createdAt);
  const ageMs = Date.now() - createdDate.getTime();
  const sevenDaysMs = 7 * 24 * 60 * 60 * 1000;

  if (ageMs < sevenDaysMs) {
    return formatDistanceToNow(createdDate, { addSuffix: true });
  }

  return format(createdDate, 'MMM d, yyyy');
}

function getReviewerDisplayName(
  reviewerFirstName?: string | null,
  reviewerLastInitial?: string | null,
  reviewerDisplayName?: string | null
): string {
  if (reviewerFirstName && reviewerLastInitial) {
    return formatStudentDisplayName(reviewerFirstName, reviewerLastInitial);
  }

  const fallbackName = reviewerDisplayName?.trim();
  return fallbackName || 'Student';
}

function ReviewsPageImpl() {
  const embedded = useEmbedded();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<RatingFilter>('all');
  const [withCommentsOnly, setWithCommentsOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [activeReplyId, setActiveReplyId] = useState<string | null>(null);
  const [replyDrafts, setReplyDrafts] = useState<Record<string, string>>({});
  const [replyErrorByReviewId, setReplyErrorByReviewId] = useState<Record<string, string>>({});
  const { user, isLoading: authLoading } = useAuth();
  const instructorId = user?.id ?? '';
  const respondToReview = useRespondToReview();
  const perPage = 6;
  const selectedRating = filter === 'all' ? undefined : filter;
  const { data: ratingsData, isLoading: ratingsLoading } = useInstructorRatingsQuery(instructorId);

  const reviewFilters = useMemo(() => {
    const filters: { rating?: number; withText?: boolean } = {};
    if (selectedRating !== undefined) {
      filters.rating = selectedRating;
    }
    if (withCommentsOnly) {
      filters.withText = true;
    }
    return filters;
  }, [selectedRating, withCommentsOnly]);

  const {
    data: reviewsData,
    isLoading: reviewsLoading,
    error: reviewsError,
    isFetching: reviewsFetching,
  } = useInstructorReviews(instructorId, page, perPage, reviewFilters);

  const reviews = reviewsData?.reviews ?? [];
  const totalReviews = ratingsData?.overall?.total_reviews ?? reviewsData?.total ?? 0;
  const averageRating = ratingsData?.overall?.rating ?? null;
  const hasVisibleRating = ratingsData?.overall?.display_rating != null;
  const ratingDisplay =
    hasVisibleRating && averageRating != null ? averageRating.toFixed(1) : '—';
  const loading = authLoading || ratingsLoading || reviewsLoading;
  const effectiveLoading = loading || (reviewsFetching && !reviewsLoading);
  const showEmptyState = !effectiveLoading && totalReviews === 0;
  const noFilteredResults = !effectiveLoading && reviews.length === 0 && totalReviews > 0;
  const countLabel = `${totalReviews} review${totalReviews === 1 ? '' : 's'}`;
  const isSubmittingReply = respondToReview.isPending
    && respondToReview.variables?.reviewId === activeReplyId;

  const handleReplySubmit = async (reviewId: string) => {
    const responseText = replyDrafts[reviewId]?.trim() ?? '';
    if (!responseText) {
      setReplyErrorByReviewId((prev) => ({
        ...prev,
        [reviewId]: 'Reply text is required.',
      }));
      return;
    }

    setReplyErrorByReviewId((prev) => {
      const next = { ...prev };
      delete next[reviewId];
      return next;
    });

    try {
      await respondToReview.mutateAsync({
        reviewId,
        data: { response_text: responseText },
      });
      setActiveReplyId(null);
      setReplyDrafts((prev) => {
        const next = { ...prev };
        delete next[reviewId];
        return next;
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.instructors.reviews(instructorId) });
    } catch (error) {
      setReplyErrorByReviewId((prev) => ({
        ...prev,
        [reviewId]: error instanceof Error ? error.message : 'Failed to send reply.',
      }));
    }
  };

  const handleReplyToggle = (reviewId: string, existingResponseText?: string | null) => {
    setActiveReplyId((current) => (current === reviewId ? null : reviewId));
    setReplyErrorByReviewId((prev) => {
      const next = { ...prev };
      delete next[reviewId];
      return next;
    });
    if (typeof existingResponseText === 'string') {
      setReplyDrafts((prev) => ({
        ...prev,
        [reviewId]: existingResponseText,
      }));
    }
  };

  return (
    <div className="min-h-screen insta-dashboard-page">
      {!embedded ? (
        <header className="relative px-4 py-4 sm:px-6 insta-dashboard-header">
          <div className="flex max-w-full items-center justify-between">
            <Link href="/instructor/dashboard" className="inline-block">
              <h1 className="pl-0 text-3xl font-bold text-(--color-brand) transition-colors hover:text-purple-900 dark:hover:text-purple-300 sm:pl-4">
                iNSTAiNSTRU
              </h1>
            </Link>
            <div className="pr-0 sm:pr-4">
              <UserProfileDropdown />
            </div>
          </div>
          <div className="pointer-events-none absolute inset-x-0 top-1/2 hidden -translate-y-1/2 sm:block">
            <div className="pointer-events-auto container mx-auto max-w-6xl px-8 lg:px-32">
              <Link href="/instructor/dashboard" className="inline-flex items-center gap-1 text-(--color-brand)">
                <ArrowLeft className="h-4 w-4" />
                <span>Back to dashboard</span>
              </Link>
            </div>
          </div>
        </header>
      ) : null}

      <div className={embedded ? 'max-w-none px-0 py-0' : 'container mx-auto max-w-6xl px-8 py-8 lg:px-32'}>
        {!embedded ? (
          <div className="mb-2 sm:hidden">
            <Link href="/instructor/dashboard" aria-label="Back to dashboard" className="inline-flex items-center gap-1 text-(--color-brand)">
              <ArrowLeft className="h-5 w-5" />
              <span className="sr-only">Back to dashboard</span>
            </Link>
          </div>
        ) : null}

        <SectionHeroCard
          id={embedded ? 'reviews-first-card' : undefined}
          icon={Star}
          title="Reviews"
          subtitle="See what students are saying and keep an eye on your ratings."
        />

        <div className="insta-surface-card p-6">
          <div className="flex flex-col gap-8 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-4">
              <SummaryRatingStar rating={hasVisibleRating ? averageRating : null} />
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                <span className="text-4xl font-semibold tracking-tight text-gray-900 dark:text-gray-100 sm:text-5xl">
                  {effectiveLoading ? '—' : ratingDisplay}
                </span>
                <span className="text-lg font-medium text-gray-500 dark:text-gray-400">
                  ({countLabel})
                </span>
              </div>
            </div>

            <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-stretch lg:w-[32rem]">
              <div className="min-w-0 flex-1">
                <span className="sr-only">Filter reviews by rating</span>
                <Select
                  value={String(filter)}
                  onValueChange={(value) => {
                    const nextValue = value === 'all' ? 'all' : Number(value);
                    setFilter(nextValue as RatingFilter);
                    setPage(1);
                  }}
                >
                  <SelectTrigger
                    aria-label="All reviews filter"
                    data-testid="reviews-rating-filter"
                    className="h-12 rounded-full border-gray-200 bg-white px-4 text-sm font-medium text-gray-700 shadow-none dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
                    style={{ backgroundColor: '#FFFFFF' }}
                  >
                    <SelectValue placeholder="All reviews" />
                  </SelectTrigger>
                  <SelectContent
                    className="bg-white dark:bg-gray-900"
                    style={{ backgroundColor: '#FFFFFF' }}
                  >
                    <SelectItem value="all">All reviews</SelectItem>
                    <SelectItem value="5">5 stars</SelectItem>
                    <SelectItem value="4">4 stars</SelectItem>
                    <SelectItem value="3">3 stars</SelectItem>
                    <SelectItem value="2">2 stars</SelectItem>
                    <SelectItem value="1">1 star</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div
                className={`flex min-h-12 flex-1 items-center justify-between gap-4 rounded-2xl border px-5 py-3 text-sm font-medium shadow-sm transition-colors focus-within:border-(--color-focus-brand) ${
                  withCommentsOnly
                    ? 'border-(--color-brand) bg-(--color-brand-lavender) text-(--color-brand) dark:border-purple-700 dark:bg-purple-900/30 dark:text-purple-300'
                    : 'border-gray-300 bg-white text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200'
                }`}
              >
                <span>With comments</span>
                <ToggleSwitch
                  checked={withCommentsOnly}
                  onChange={() => {
                    setWithCommentsOnly((current) => !current);
                    setPage(1);
                  }}
                  ariaLabel="With comments"
                />
              </div>
            </div>
          </div>

          {showEmptyState ? (
            <div className="mt-6 space-y-3 text-gray-500 dark:text-gray-400">
              <p>You don’t have any reviews yet, but you’re just getting started.</p>
              <p>After each lesson, invite students to share feedback so your rating can take shape.</p>
            </div>
          ) : null}
        </div>

        <div className="mt-6 space-y-4">
          {reviewsError ? (
            <p className="text-red-600">
              {reviewsError instanceof Error ? reviewsError.message : 'Failed to load reviews'}
            </p>
          ) : null}

          {effectiveLoading ? (
            <p className="text-gray-500 dark:text-gray-400">Loading reviews…</p>
          ) : (
            <>
              {noFilteredResults ? (
                <p className="text-gray-500 dark:text-gray-400">No reviews match your filters.</p>
              ) : null}

              {reviews.map((review) => {
                const reviewerName = getReviewerDisplayName(
                  review.reviewer_first_name,
                  review.reviewer_last_initial,
                  review.reviewer_display_name
                );
                const replyError = replyErrorByReviewId[review.id];
                const hasResponse = review.response != null;
                const reviewText = review.review_text?.trim() ?? '';
                const isReplyable = reviewText.length > 0;
                const isReplyOpen = activeReplyId === review.id;
                const reviewTimestamp = formatReviewTimestamp(review.created_at);

                return (
                  <article key={review.id} className="insta-surface-card p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0 space-y-2">
                        <ReviewStars rating={review.rating} />
                        <span className="block min-w-0 truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
                          {reviewerName}
                        </span>
                      </div>

                      <div
                        className="flex shrink-0 flex-col items-end gap-2 text-right"
                        data-testid={`review-meta-${review.id}`}
                      >
                        <span className="text-sm text-gray-500 dark:text-gray-400">
                          {reviewTimestamp}
                        </span>
                        {isReplyable ? (
                          <button
                            type="button"
                            onClick={() =>
                              handleReplyToggle(
                                review.id,
                                hasResponse ? review.response?.response_text ?? '' : undefined,
                              )
                            }
                            className="text-sm font-semibold text-(--color-brand) transition-colors hover:text-[#5f1aa4]"
                          >
                            {hasResponse ? 'Edit' : 'Reply'}
                          </button>
                        ) : null}
                      </div>
                    </div>

                    <div className="mt-3 space-y-3">
                      {reviewText ? (
                        <p className="text-sm leading-6 text-gray-700 dark:text-gray-300">
                          {reviewText}
                        </p>
                      ) : null}

                      {hasResponse ? (
                        <div className="rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3 dark:border-gray-700 dark:bg-gray-900/70">
                          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                            Instructor reply
                          </p>
                          <p className="mt-2 text-sm leading-6 text-gray-700 dark:text-gray-300">
                            {review.response?.response_text}
                          </p>
                        </div>
                      ) : null}

                      {isReplyable && isReplyOpen ? (
                        <form
                          className="space-y-3"
                          onSubmit={(event) => {
                            event.preventDefault();
                            void handleReplySubmit(review.id);
                          }}
                        >
                          <label className="sr-only" htmlFor={`reply-${review.id}`}>
                            Reply to {reviewerName}
                          </label>
                          <textarea
                            id={`reply-${review.id}`}
                            value={replyDrafts[review.id] ?? ''}
                            onChange={(event) => {
                              const nextValue = event.target.value;
                              setReplyDrafts((prev) => ({
                                ...prev,
                                [review.id]: nextValue,
                              }));
                            }}
                            rows={3}
                            className="w-full rounded-2xl border border-gray-300 bg-white px-4 py-3 text-sm text-gray-900 shadow-sm transition-colors focus:border-(--color-focus-brand) focus:outline-none dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                            placeholder="Write a thoughtful reply..."
                          />
                          {replyError ? (
                            <p className="text-sm text-red-600">{replyError}</p>
                          ) : null}
                          <div className="flex items-center gap-3">
                            <button
                              type="submit"
                              disabled={isSubmittingReply}
                              className="rounded-full bg-(--color-brand) px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-(--color-brand) disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              {isSubmittingReply
                                ? hasResponse
                                  ? 'Saving…'
                                  : 'Sending…'
                                : hasResponse
                                  ? 'Save reply'
                                  : 'Send reply'}
                            </button>
                            <button
                              type="button"
                              onClick={() => setActiveReplyId(null)}
                              className="text-sm font-medium text-gray-500 transition-colors hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                            >
                              Cancel
                            </button>
                          </div>
                        </form>
                      ) : null}
                    </div>
                  </article>
                );
              })}
            </>
          )}
        </div>

        {(reviewsData?.has_prev || reviewsData?.has_next) && !showEmptyState ? (
          <div className="mt-6 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              disabled={page === 1 || reviewsFetching}
              className="insta-secondary-btn inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300"
            >
              <span>Previous</span>
            </button>
            <span className="text-sm text-gray-600 dark:text-gray-400">Page {page}</span>
            <button
              type="button"
              onClick={() => setPage((prev) => prev + 1)}
              disabled={!reviewsData?.has_next || reviewsFetching}
              className="insta-secondary-btn inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300"
            >
              <span>Next</span>
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default function InstructorReviewsPage() {
  return <ReviewsPageImpl />;
}
