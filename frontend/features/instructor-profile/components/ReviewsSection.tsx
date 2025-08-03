import { Star } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useInstructorReviews } from '../hooks/useInstructorReviews';
import { formatDistanceToNow } from 'date-fns';

interface ReviewsSectionProps {
  instructorId: string | number;
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
        <h2 className="text-xl font-semibold mb-4">Reviews</h2>
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
        <h2 className="text-xl font-semibold mb-4">Reviews</h2>
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
        <h2 className="text-xl font-semibold mb-4">Reviews</h2>
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
      <div className="flex items-center justify-between mb-4 pb-2 border-b">
        <h3 className="text-lg font-semibold">
          Reviews ({data.total})
        </h3>
        <Button variant="outline" size="sm">
          Write Review
        </Button>
      </div>

      <div className="space-y-4">
        {data.reviews.slice(0, 2).map((review) => (
          <div key={review.id} className="pb-4 border-b last:border-0">
            <div className="flex items-start gap-3 mb-2">
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

      {data.total > 2 && (
        <Button
          variant="link"
          className="p-0 h-auto mt-4 text-sm"
          onClick={() => {
            // TODO: Navigate to full reviews page
            console.log('See all reviews');
          }}
        >
          See All {data.total} Reviews →
        </Button>
      )}
    </div>
  );
}
