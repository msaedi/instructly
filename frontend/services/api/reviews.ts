import { fetchWithAuth, fetchAPI, getErrorMessage } from '@/lib/api';

export interface ReviewSubmitPayload {
  booking_id: string;
  rating: number;
  review_text?: string | null;
  tip_amount_cents?: number | null;
}

export interface ReviewItem {
  id: string;
  rating: number;
  review_text?: string | null;
  created_at: string;
  instructor_service_id: string;
  reviewer_display_name?: string | null;
}

export interface ReviewSubmitResponse extends ReviewItem {
  tip_status?: string | null;
  tip_client_secret?: string | null;
}

export interface InstructorRatingsResponse {
  overall: { rating: number; total_reviews: number; display_rating?: string | null };
  by_service: Array<{ instructor_service_id: string; rating?: number | null; review_count: number; display_rating?: string | null }>;
  confidence_level: 'new' | 'establishing' | 'established' | 'trusted';
}

export interface SearchRatingResponse {
  primary_rating: number | null;
  review_count: number;
  is_service_specific: boolean;
}

export interface RatingsBatchItem {
  instructor_id: string;
  rating: number | null;
  review_count: number;
}

export interface RatingsBatchResponse {
  results: RatingsBatchItem[];
}

export interface ReviewListPageResponse {
  reviews: ReviewItem[];
  total: number;
  page: number;
  per_page: number;
  has_next: boolean;
  has_prev: boolean;
}

export const reviewsApi = {
  submit: async (payload: ReviewSubmitPayload): Promise<ReviewSubmitResponse> => {
    const res = await fetchWithAuth('/api/reviews/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return res.json();
  },

  getByBooking: async (bookingId: string): Promise<ReviewItem | null> => {
    const res = await fetchWithAuth(`/api/reviews/booking/${bookingId}`);
    if (!res.ok) throw new Error(await getErrorMessage(res));
    const data = await res.json();
    return data && data.id ? (data as ReviewItem) : null;
  },

  getInstructorRatings: async (instructorId: string): Promise<InstructorRatingsResponse> => {
    const res = await fetchAPI(`/api/reviews/instructor/${instructorId}/ratings`);
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return res.json();
  },

  getSearchRating: async (instructorId: string, instructorServiceId?: string): Promise<SearchRatingResponse> => {
    const qs = instructorServiceId ? `?instructor_service_id=${encodeURIComponent(instructorServiceId)}` : '';
    const res = await fetchAPI(`/api/reviews/instructor/${instructorId}/search-rating${qs}`);
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return res.json();
  },

  getRecent: async (
    instructorId: string,
    instructorServiceId?: string,
    limit: number = 10,
    page: number = 1,
    opts?: { minRating?: number; rating?: number; withText?: boolean }
  ): Promise<ReviewListPageResponse> => {
    const p = new URLSearchParams();
    if (instructorServiceId) p.set('instructor_service_id', instructorServiceId);
    p.set('limit', String(limit));
    p.set('page', String(page));
    if (opts?.rating != null) {
      p.set('rating', String(opts.rating));
    } else if (opts?.minRating != null) {
      p.set('min_rating', String(opts.minRating));
    }
    if (opts?.withText != null) p.set('with_text', String(Boolean(opts.withText)));
    const res = await fetchAPI(`/api/reviews/instructor/${instructorId}/recent?${p.toString()}`);
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return res.json();
  },

  getRatingsBatch: async (instructorIds: string[]): Promise<RatingsBatchResponse> => {
    const res = await fetchAPI(`/api/reviews/ratings/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instructor_ids: instructorIds }),
    });
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return res.json();
  },

  getExistingForBookings: async (bookingIds: string[]): Promise<string[]> => {
    const res = await fetchWithAuth(`/api/reviews/booking/existing`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bookingIds),
    });
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return res.json();
  },
};
