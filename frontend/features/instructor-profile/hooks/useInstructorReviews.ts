import { useQuery } from '@tanstack/react-query';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';
import { reviewsApi, ReviewItem as ApiReviewItem, ReviewListPageResponse } from '@/services/api/reviews';

export interface ReviewItem {
  id: string;
  rating: number;
  review_text?: string | null;
  created_at: string;
  instructor_service_id: string;
  reviewer_display_name?: string | null;
}

export interface ReviewsResponse {
  reviews: ReviewItem[];
  total: number;
  page: number;
  per_page: number;
  has_next: boolean;
  has_prev: boolean;
}

export function useInstructorReviews(
  instructorId: string,
  page: number = 1,
  limit: number = 12,
  opts?: { minRating?: number; withText?: boolean; instructorServiceId?: string }
) {
  return useQuery<ReviewsResponse>({
    queryKey: ['instructors', instructorId, 'reviews', { page, limit, opts }],
    queryFn: async () => {
      const res: ReviewListPageResponse = await reviewsApi.getRecent(
        instructorId,
        opts?.instructorServiceId,
        limit,
        page,
        { minRating: opts?.minRating, withText: opts?.withText }
      );
      const items: ApiReviewItem[] = res.reviews || [];
      return {
        reviews: items.map((r) => ({
          id: r.id,
          rating: r.rating,
          review_text: r.review_text,
          created_at: r.created_at,
          instructor_service_id: r.instructor_service_id,
          reviewer_display_name: (r as any).reviewer_display_name ?? null,
        })),
        total: res.total,
        page: res.page,
        per_page: res.per_page,
        has_next: res.has_next,
        has_prev: res.has_prev,
      };
    },
    staleTime: CACHE_TIMES.SLOW,
    enabled: !!instructorId,
  });
}
