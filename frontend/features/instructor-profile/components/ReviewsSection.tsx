import { Star } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useInstructorReviews } from '../hooks/useInstructorReviews';
import { formatDistanceToNow } from 'date-fns';

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
  const { data, isLoading, error } = useInstructorReviews(instructorId.toString());

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

  if (data.reviews.length === 0) {
    return (
      <section>
        <h2 className="text-lg text-gray-600 mb-4">Reviews</h2>
        <Card>
          <CardContent className="py-8 text-center">
            <Star className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
            <p className="font-medium">New instructor</p>
            <p className="text-sm text-muted-foreground">Be the first to review!</p>
          </CardContent>
        </Card>
      </section>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg text-gray-600">
          Reviews ({data.total})
        </h2>
        <button
          className="bg-white text-purple-700 py-1.5 px-4 rounded-lg font-medium border-2 border-purple-700 hover:bg-purple-50 transition-colors cursor-pointer"
        >
          Write Review
        </button>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {data.reviews.slice(0, 4).map((review) => (
          <div
            key={review.id}
            className="p-3 bg-white rounded-lg border border-gray-100"
          >
            <div className="flex items-start gap-3">
              <StarRating rating={review.rating} />
              <div className="flex-1">
                <div className="flex items-baseline gap-2">
                  <span className="font-medium text-sm">{review.reviewer_name}</span>
                  <span className="text-xs text-muted-foreground">
                    · {formatDistanceToNow(new Date(review.created_at), { addSuffix: true })}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground mt-1">
                  {review.comment}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {data.total > 4 && (
        <button
          className="mt-4 text-xs text-purple-700 hover:text-purple-800 hover:underline transition-colors"
          onClick={() => {
            // TODO: Navigate to full reviews page
            console.log('See all reviews');
          }}
        >
          See all {data.total} reviews
        </button>
      )}
    </div>
  );
}
