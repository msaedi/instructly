'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { formatDistanceToNow } from 'date-fns';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { ArrowLeft, ChevronDown, Star } from 'lucide-react';
import { SectionHeroCard } from '@/components/dashboard/SectionHeroCard';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useInstructorReviews } from '@/features/instructor-profile/hooks/useInstructorReviews';
import { useInstructorRatingsQuery } from '@/hooks/queries/useRatings';

import { useEmbedded } from '../_embedded/EmbeddedContext';

function StarRating({ rating }: { rating: number }) {
  return (
    <div className="flex gap-0.5" aria-label={`${rating} star rating`}>
      {[1, 2, 3, 4, 5].map((s) => (
        <Star
          key={s}
          className={`h-4 w-4 ${s <= rating ? 'fill-yellow-400 text-yellow-400' : 'fill-gray-200 text-gray-200'}`}
        />
      ))}
    </div>
  );
}

function ReviewsPageImpl() {
  const embedded = useEmbedded();
  const [filter, setFilter] = useState<'all' | 5 | 4 | 3 | 2 | 1>('all');
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const filterRef = useRef<HTMLDivElement | null>(null);
  const [hoveredOpt, setHoveredOpt] = useState<'all' | 5 | 4 | 3 | 2 | 1 | 'comments' | null>(null);
  const { user, isLoading: authLoading } = useAuth();
  const instructorId = user?.id ?? '';
  const [withCommentsOnly, setWithCommentsOnly] = useState(false);
  const [page, setPage] = useState(1);
  const perPage = 6;
  const selectedRating = filter === 'all' ? undefined : filter;
  const { data: ratingsData, isLoading: ratingsLoading } = useInstructorRatingsQuery(instructorId);
  const reviewFilters: { rating?: number; withText?: boolean } = {};
  if (selectedRating !== undefined) {
    reviewFilters.rating = selectedRating;
  }
  if (withCommentsOnly) {
    reviewFilters.withText = true;
  }

  const {
    data: reviewsData,
    isLoading: reviewsLoading,
    error: reviewsError,
    isFetching: reviewsFetching,
  } = useInstructorReviews(instructorId, page, perPage, reviewFilters);
  const reviews = reviewsData?.reviews ?? [];
  const totalReviews = ratingsData?.overall?.total_reviews ?? reviewsData?.total ?? 0;
  const averageRating = ratingsData?.overall?.rating ?? null;
  const averageRatingDisplay = averageRating != null ? averageRating.toFixed(1) : null;
  const loading = authLoading || ratingsLoading || reviewsLoading;
  const isRefetching = reviewsFetching && !reviewsLoading;
  const effectiveLoading = loading || isRefetching;
  const showEmptyState = !effectiveLoading && totalReviews === 0;
  const noFilteredResults = !effectiveLoading && reviews.length === 0 && totalReviews > 0;

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (!filterRef.current) return;
      if (!filterRef.current.contains(e.target as Node)) setIsFilterOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  useEffect(() => {
    setPage(1);
  }, [selectedRating, withCommentsOnly, instructorId]);

  const filterLabel = withCommentsOnly
    ? 'With comments only'
    : filter === 'all'
      ? 'All reviews'
      : `${filter} stars`;
  return (
    <div className="min-h-screen">
      {/* Header hidden when embedded */}
      {!embedded && (
        <header className="relative bg-white backdrop-blur-sm border-b border-gray-200 px-4 sm:px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <Link href="/instructor/dashboard" className="inline-block">
              <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-0 sm:pl-4">iNSTAiNSTRU</h1>
            </Link>
            <div className="pr-0 sm:pr-4">
              <UserProfileDropdown />
            </div>
          </div>
          <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 hidden sm:block">
            <div className="container mx-auto px-8 lg:px-32 max-w-6xl pointer-events-none">
              <Link href="/instructor/dashboard" className="inline-flex items-center gap-1 text-[#7E22CE] pointer-events-auto">
                <ArrowLeft className="w-4 h-4" />
                <span>Back to dashboard</span>
              </Link>
            </div>
          </div>
        </header>
      )}

      <div className={embedded ? 'max-w-none px-0 lg:px-0 py-0' : 'container mx-auto px-8 lg:px-32 py-8 max-w-6xl'}>
        {!embedded && (
          <div className="sm:hidden mb-2">
            <Link href="/instructor/dashboard" aria-label="Back to dashboard" className="inline-flex items-center gap-1 text-[#7E22CE]">
              <ArrowLeft className="w-5 h-5" />
              <span className="sr-only">Back to dashboard</span>
            </Link>
          </div>
        )}
        <SectionHeroCard
          id={embedded ? 'reviews-first-card' : undefined}
          icon={Star}
          title="Reviews"
          subtitle="See what students are saying and keep an eye on your ratings."
          actions={!embedded ? (
            <Link href="/instructor/dashboard" className="text-[#7E22CE] sm:hidden">
              Dashboard
            </Link>
          ) : undefined}
        />

        {/* Ratings summary */}
        <div className="bg-white rounded-lg p-4 border border-gray-200">
          <div className="flex flex-row flex-wrap items-start justify-between gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <Star className={`h-6 w-6 ${averageRating != null ? 'fill-yellow-400 text-yellow-400' : 'text-gray-300'}`} />
                <span className="text-3xl font-bold text-[#7E22CE] leading-none">
                  {loading ? '—' : averageRatingDisplay ?? '—'}
                </span>
              </div>
              <p className="text-[#7E22CE] text-base font-semibold leading-tight">
                {loading ? 'Loading…' : `${totalReviews} total reviews`}
              </p>
            </div>
            <div className="relative sm:self-center ml-auto pr-4 sm:pr-0 mt-4 sm:mt-0" ref={filterRef}>
              <button
                type="button"
                onClick={() => setIsFilterOpen((v) => !v)}
                className="inline-flex items-center gap-1 text-[#7E22CE] font-semibold hover:text-[#5f1aa4]"
                aria-haspopup="listbox"
                aria-expanded={isFilterOpen}
              >
                <span>{filterLabel}</span>
                <ChevronDown className={`w-4 h-4 transition-transform ${isFilterOpen ? 'rotate-180' : ''}`} />
              </button>
              {isFilterOpen && (
                <ul
                  role="listbox"
                  className="absolute right-0 z-10 mt-2 w-56 max-w-[calc(100vw-2rem)] rounded-md border border-gray-200 bg-white shadow-md p-1"
                >
                  {(['all', 5, 4, 3, 2, 1] as const).map((opt) => (
                    <li key={String(opt)}>
                      <button
                        type="button"
                        role="option"
                        aria-selected={filter === opt && !withCommentsOnly}
                        onClick={() => {
                          setWithCommentsOnly(false);
                          setFilter(opt);
                          setPage(1);
                          setIsFilterOpen(false);
                        }}
                        onMouseEnter={() => setHoveredOpt(opt)}
                        onMouseLeave={() => setHoveredOpt((h) => (h === opt ? null : h))}
                        className={`w-full text-left px-3 py-2 rounded-md transition-colors cursor-pointer ${
                          hoveredOpt === opt ? 'bg-purple-50 text-[#7E22CE]' : ''
                        } ${
                          filter === opt && !withCommentsOnly
                            ? 'bg-purple-100 text-[#7E22CE] font-semibold'
                            : 'text-gray-800'
                        }`}
                      >
                        {opt === 'all' ? 'All reviews' : `${opt} stars`}
                      </button>
                    </li>
                  ))}
                  <li>
                    <button
                      type="button"
                      role="option"
                      aria-selected={withCommentsOnly}
                      onClick={() => {
                        setWithCommentsOnly((prev) => {
                          const next = !prev;
                          if (!next) {
                            setFilter('all');
                          }
                          return next;
                        });
                        setPage(1);
                        setIsFilterOpen(false);
                      }}
                      onMouseEnter={() => setHoveredOpt('comments')}
                      onMouseLeave={() => setHoveredOpt((h) => (h === 'comments' ? null : h))}
                      className={`w-full text-left px-3 py-2 rounded-md transition-colors cursor-pointer ${
                        hoveredOpt === 'comments' ? 'bg-purple-50 text-[#7E22CE]' : ''
                      } ${
                        withCommentsOnly ? 'bg-purple-100 text-[#7E22CE] font-semibold' : 'text-gray-800'
                      }`}
                    >
                      With comments only
                    </button>
                  </li>
                </ul>
              )}
            </div>

          </div>

          {showEmptyState && (
            <div className="mt-6 space-y-3 text-gray-500">
              <p>You don’t have any reviews yet — but you’re just getting started!</p>
              <p>Happy students leave great feedback. After each lesson, kindly remind them to rate their experience.</p>
            </div>
          )}
        </div>

        <div className="mt-6 space-y-4">
          {reviewsError ? (
            <p className="text-red-600">
              {reviewsError instanceof Error ? reviewsError.message : 'Failed to load reviews'}
            </p>
          ) : null}

          {effectiveLoading ? (
            <p className="text-muted-foreground">Loading reviews…</p>
          ) : (
            <>
              {noFilteredResults && (
                <p className="text-muted-foreground">No reviews match your filters.</p>
              )}

              {reviews.length > 0 && (
                <div className="grid grid-cols-1 gap-4">
                  {reviews.map((review) => (
                    <article key={review.id} className="p-4 bg-white rounded-lg border border-gray-200">
                      <div className="flex items-start gap-3">
                        <StarRating rating={review.rating} />
                        <div className="flex-1">
                          <div className="flex flex-wrap items-baseline gap-2">
                            <span className="text-sm font-medium text-gray-900">{review.reviewer_display_name || 'Student'}</span>
                            <span className="text-xs text-gray-500">
                              {formatDistanceToNow(new Date(review.created_at), { addSuffix: true })}
                            </span>
                          </div>
                          {review.review_text ? (
                            <p className="text-sm text-gray-700 mt-1">{review.review_text}</p>
                          ) : (
                            <p className="text-xs text-gray-500 mt-1">No written feedback</p>
                          )}
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {(reviewsData?.has_prev || reviewsData?.has_next) && !showEmptyState && (
          <div className="mt-6 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              disabled={page === 1 || reviewsFetching}
              className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 disabled:opacity-50"
            >
              <span>Previous</span>
            </button>
            <span className="text-sm text-gray-600">Page {page}</span>
            <button
              type="button"
              onClick={() => setPage((prev) => prev + 1)}
              disabled={!reviewsData?.has_next || reviewsFetching}
              className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 disabled:opacity-50"
            >
              <span>Next</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function InstructorReviewsPage() {
  return <ReviewsPageImpl />;
}
