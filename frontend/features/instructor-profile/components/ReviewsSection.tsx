import { Star } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useInstructorReviews } from '../hooks/useInstructorReviews';
import { formatDistanceToNow } from 'date-fns';
import { useRouter } from 'next/navigation';
import type { ReviewItem } from '@/services/api/reviews';

interface ReviewsSectionProps {
  instructorId: string;
}

function StarRating({ rating }: { rating: number }) {
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((star) => (
        <Star
          key={star}
          className={`h-4 w-4 ${
            star <= rating
              ? 'fill-yellow-400 text-yellow-400'
              : 'fill-gray-200 text-gray-200'
          }`}
        />
      ))}
    </div>
  );
}

export function ReviewsSection({ instructorId }: ReviewsSectionProps) {
  const router = useRouter();
  const { data, isLoading, error } = useInstructorReviews(instructorId, 1, 12);

  if (isLoading) {
    return (
      <section>
        <h2 className="text-lg text-gray-600 mb-4">Reviews</h2>
        <div className="space-y-4">
          {[1, 2].map((i) => (
            <Card key={i}>
              <CardContent className="pt-6">
                <Skeleton className="h-4 w-24 mb-2" />
                <Skeleton className="h-3 w-full mb-1" />
                <Skeleton className="h-3 w-3/4" />
                <Skeleton className="h-3 w-20 mt-2" />
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    );
  }

  if (error || !data) {
    return (
      <section>
        <h2 className="text-lg text-gray-600 mb-4">Reviews</h2>
        <Card>
          <CardContent className="py-8 text-center">
            <p className="text-muted-foreground">Unable to load reviews</p>
          </CardContent>
        </Card>
      </section>
    );
  }

  if (!data?.reviews || data.reviews.length === 0) {
    return (
      <section>
        <h2 className="text-lg text-gray-600 mb-4">Reviews</h2>
        <Card>
          <CardContent className="py-8 text-center">
            <p className="font-medium">New instructor</p>
            <p className="text-sm text-muted-foreground">No reviews yet.</p>
          </CardContent>
        </Card>
      </section>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg text-gray-600">Recent reviews ({data?.total ?? 0})</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {data?.reviews?.map((review: ReviewItem) => (
          <div
            key={review.id}
            className="p-3 bg-white rounded-lg border border-gray-100"
          >
            <div className="flex items-start gap-3">
              <StarRating rating={review.rating} />
              <div className="flex-1">
                <div className="flex items-baseline gap-2">
                  {review.reviewer_display_name && (
                    <span className="font-medium text-sm">{review.reviewer_display_name}</span>
                  )}
                  <span className="text-xs text-muted-foreground">
                    {formatDistanceToNow(new Date(review.created_at), { addSuffix: true })}
                  </span>
                </div>
                {review.review_text && (
                  <p className="text-sm text-gray-700 mt-1">
                    {review.review_text}
                  </p>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {(data?.total ?? 0) > (data?.per_page ?? 0) && (
        <button
          className="mt-4 text-sm text-[#7E22CE] hover:text-[#7E22CE] hover:underline transition-colors"
          onClick={() => router.push(`/instructors/${instructorId}/reviews`)}
        >
          See all {data?.total ?? 0} reviews
        </button>
      )}
    </div>
  );
}
