'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Star, ArrowLeft, ChevronLeft, ChevronRight } from 'lucide-react';
import { reviewsApi, ReviewItem, ReviewListPageResponse } from '@/services/api/reviews';
import { formatDistanceToNow } from 'date-fns';

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
  const instructorId = params.id as string;
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(12);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrev, setHasPrev] = useState(false);
  const [total, setTotal] = useState(0);

  const [minRating, setMinRating] = useState<number | undefined>(undefined);
  const [withText, setWithText] = useState<boolean>(false);

  const ratingOptions = useMemo(() => [
    { label: 'All ratings', value: undefined },
    { label: '5 stars', value: 5 },
    { label: '4 stars & up', value: 4 },
    { label: '3 stars & up', value: 3 },
    { label: '2 stars & up', value: 2 },
    { label: '1 star & up', value: 1 },
  ], []);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    (async () => {
      try {
        const res: ReviewListPageResponse = await reviewsApi.getRecent(
          instructorId,
          undefined,
          perPage,
          page,
          { minRating, withText }
        );
        if (!mounted) return;
        setReviews(res.reviews || []);
        setHasNext(res.has_next);
        setHasPrev(res.has_prev);
        setTotal(res.total);
      } catch (e: any) {
        if (mounted) setError(e?.message || 'Failed to load reviews');
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [instructorId, page, perPage, minRating, withText]);

  return (
    <div className="min-h-screen bg-background">
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4 sticky top-0 z-50">
        <div className="flex items-center justify-between max-w-full">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push(`/instructors/${instructorId}`)}
              className="flex items-center gap-2 text-gray-600 hover:text-gray-900 cursor-pointer"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Profile
            </button>
          </div>
        </div>
      </header>

      <div className="container mx-auto px-4 py-6 max-w-4xl">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-semibold text-gray-700">All Reviews</h1>
          <div className="text-sm text-muted-foreground">{total} total</div>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-4 mb-6">
          <label className="text-sm text-gray-700">
            Min rating
            <select
              className="ml-2 border rounded px-2 py-1 text-sm"
              value={minRating ?? ''}
              onChange={(e) => {
                const v = e.target.value;
                setPage(1);
                setMinRating(v === '' ? undefined : Number(v));
              }}
            >
              {ratingOptions.map((o) => (
                <option key={String(o.value)} value={o.value ?? ''}>{o.label}</option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={withText}
              onChange={(e) => { setWithText(e.target.checked); setPage(1); }}
            />
            With comments only
          </label>

          <label className="text-sm text-gray-700">
            Per page
            <select
              className="ml-2 border rounded px-2 py-1 text-sm"
              value={perPage}
              onChange={(e) => { setPerPage(Number(e.target.value)); setPage(1); }}
            >
              {[12, 24, 36].map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </label>
        </div>

        {loading && (
          <p className="text-muted-foreground">Loading reviews…</p>
        )}
        {error && (
          <p className="text-red-600">{error}</p>
        )}

        {!loading && !error && reviews.length === 0 && (
          <p className="text-muted-foreground">No reviews match your filters.</p>
        )}

        <div className="grid grid-cols-1 gap-4">
          {reviews.map((r) => (
            <div key={r.id} className="p-4 bg-white rounded-lg border border-gray-100">
              <div className="flex items-start gap-3">
                <StarRating rating={r.rating} />
                <div className="flex-1">
                  <div className="flex items-baseline gap-2">
                    {r.reviewer_display_name && (
                      <span className="font-medium text-sm">{r.reviewer_display_name}</span>
                    )}
                    <span className="text-xs text-muted-foreground">
                      {formatDistanceToNow(new Date(r.created_at), { addSuffix: true })}
                    </span>
                  </div>
                  {r.review_text && (
                    <p className="text-sm text-gray-700 mt-1">{r.review_text}</p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Pager */}
        <div className="mt-6 flex items-center justify-between">
          <button
            className="flex items-center gap-1 text-sm text-gray-700 disabled:opacity-50"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={!hasPrev}
          >
            <ChevronLeft className="h-4 w-4" /> Prev
          </button>
          <div className="text-sm text-gray-600">Page {page}</div>
          <button
            className="flex items-center gap-1 text-sm text-gray-700 disabled:opacity-50"
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
