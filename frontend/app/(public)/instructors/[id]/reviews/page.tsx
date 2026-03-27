'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { Star, ArrowLeft, ChevronLeft, ChevronRight, Check } from 'lucide-react';
import { useInstructorReviews } from '@/features/instructor-profile/hooks/useInstructorReviews';
import { formatDistanceToNow } from 'date-fns';
import { Button } from '@/components/ui/button';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { Select, SelectTrigger, SelectContent, SelectItem } from '@/components/ui/select';

function StarRating({ rating }: { rating: number }) {
  return (
    <div className="flex gap-0.5" aria-label={`${rating} star rating`}>
      {[1, 2, 3, 4, 5].map((s) => (
        <Star
          key={s}
          className={`h-4 w-4 ${s <= rating ? 'fill-yellow-400 text-yellow-400' : 'fill-gray-200 text-gray-200'}`}
        />)
      )}
    </div>
  );
}

export default function InstructorAllReviewsPage() {
  const params = useParams();
  const router = useRouter();
  const instructorId = params['id'] as string;
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(12);

  const [minRating, setMinRating] = useState<number | undefined>(undefined);
  const [withText, setWithText] = useState<boolean>(false);

  // Build options object conditionally to satisfy exactOptionalPropertyTypes
  const reviewsOpts = {
    ...(minRating !== undefined && { minRating }),
    ...(withText && { withText }),
  };

  // Use React Query hook for reviews (prevents duplicate API calls)
  const { data, isLoading: loading, error: queryError } = useInstructorReviews(
    instructorId,
    page,
    perPage,
    Object.keys(reviewsOpts).length > 0 ? reviewsOpts : undefined
  );

  const reviews = data?.reviews ?? [];
  const hasNext = data?.has_next ?? false;
  const hasPrev = data?.has_prev ?? false;
  const total = data?.total ?? 0;
  const error = queryError ? (queryError as Error).message || 'Failed to load reviews' : null;

  return (
    <div className="min-h-screen bg-white dark:bg-gray-900">
      <header className="bg-white/90 dark:bg-gray-800/90 backdrop-blur-sm border-b border-gray-200 dark:border-gray-700 px-6 py-4 sticky top-0 z-50">
        <div className="flex items-center justify-between max-w-full">
          <div className="flex items-center gap-4">
            <Link className="inline-block" href="/">
              <span className="text-3xl font-bold text-(--color-brand-dark) hover:text-purple-900 dark:hover:text-purple-300 transition-colors cursor-pointer pl-4">iNSTAiNSTRU</span>
            </Link>
            <Button
              variant="ghost"
              onClick={() => router.push(`/instructors/${instructorId}`)}
              className="flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Profile
            </Button>
          </div>
          <div className="pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      <div className="container mx-auto px-4 py-6 max-w-4xl">
        <div className="bg-white dark:bg-gray-800 rounded-lg p-6 mb-6 border border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-semibold text-gray-700 dark:text-gray-300">All Reviews</h1>
            <div className="text-sm text-gray-500 dark:text-gray-400">{total} total</div>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700 mb-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Min rating */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Min rating</label>
              <Select
                value={minRating !== undefined ? String(minRating) : 'all'}
                onValueChange={(v) => { setPage(1); setMinRating(v === 'all' ? undefined : Number(v)); }}
              >
                <SelectTrigger />
                <SelectContent>
                  <SelectItem value="all">All ratings</SelectItem>
                  <SelectItem value="5">5 stars</SelectItem>
                  <SelectItem value="4">4 stars & up</SelectItem>
                  <SelectItem value="3">3 stars & up</SelectItem>
                  <SelectItem value="2">2 stars & up</SelectItem>
                  <SelectItem value="1">1 star & up</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* With comments only */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Text filter</label>
              <button
                type="button"
                aria-pressed={withText}
                onClick={() => { setWithText((v) => !v); setPage(1); }}
                className={`inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors ${withText ? 'border-purple-300 bg-purple-50 text-(--color-brand-dark)' : 'border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300'} hover:bg-gray-50 dark:hover:bg-gray-700`}
              >
                {withText ? <Check className="h-4 w-4" /> : <span className="h-4 w-4 inline-block border border-gray-300 dark:border-gray-700 rounded-sm" />}
                With comments only
              </button>
            </div>

            {/* Per page */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Per page</label>
              <Select value={String(perPage)} onValueChange={(v) => { setPerPage(Number(v)); setPage(1); }}>
                <SelectTrigger />
                <SelectContent>
                  <SelectItem value="12">12</SelectItem>
                  <SelectItem value="24">24</SelectItem>
                  <SelectItem value="36">36</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        {loading && (
          <p className="text-gray-500 dark:text-gray-400">Loading reviews…</p>
        )}
        {error && (
          <p className="text-red-600">{error}</p>
        )}

        {!loading && !error && reviews.length === 0 && (
          <p className="text-gray-500 dark:text-gray-400">No reviews match your filters.</p>
        )}

        <div className="grid grid-cols-1 gap-4">
          {reviews.map((r) => (
            <div key={r.id} className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-100 dark:border-gray-700">
              <div className="flex items-start gap-3">
                <StarRating rating={r.rating} />
                <div className="flex-1">
                  <div className="flex items-baseline gap-2">
                    {r.reviewer_display_name && (
                      <span className="font-medium text-sm">{r.reviewer_display_name}</span>
                    )}
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {formatDistanceToNow(new Date(r.created_at), { addSuffix: true })}
                    </span>
                  </div>
                  {r.review_text && (
                    <p className="text-sm text-gray-700 dark:text-gray-300 mt-1">{r.review_text}</p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Pager */}
        <div className="mt-6 flex items-center justify-between">
          <button
            className="flex items-center gap-1 text-sm text-gray-700 dark:text-gray-300 disabled:opacity-50"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={!hasPrev}
          >
            <ChevronLeft className="h-4 w-4" /> Prev
          </button>
          <div className="text-sm text-gray-600 dark:text-gray-400">Page {page}</div>
          <button
            className="flex items-center gap-1 text-sm text-gray-700 dark:text-gray-300 disabled:opacity-50"
            onClick={() => setPage((p) => p + 1)}
            disabled={!hasNext}
          >
            Next <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

export const dynamic = 'force-dynamic';
export const dynamicParams = true;
