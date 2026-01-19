import { fetchWithAuth, fetchAPI, getErrorMessage } from '@/lib/api';
import type {
  components,
  RatingsBatchResponse,
  ReviewSubmitResponse,
  SearchRatingResponse,
} from '@/features/shared/api/types';

type RawInstructorRatingsResponse = components['schemas']['InstructorRatingsResponse'];
export type InstructorRatingsResponse = Omit<RawInstructorRatingsResponse, 'overall'> & {
  overall: {
    rating?: number;
    display_rating?: string;
    total_reviews?: number;
  } | null;
};
export type { RatingsBatchResponse, SearchRatingResponse };
export type RatingsBatchItem = components['schemas']['RatingsBatchItem'];

type ReviewSubmitPayload = components['schemas']['ReviewSubmitRequest'];
export type ReviewItem = components['schemas']['ReviewItem'];
export type ReviewListPageResponse = components['schemas']['ReviewListPageResponse'];
type ExistingReviewIdsResponse = components['schemas']['ExistingReviewIdsResponse'];

export const reviewsApi = {
  submit: async (payload: ReviewSubmitPayload): Promise<ReviewSubmitResponse> => {
    const res = await fetchWithAuth('/api/v1/reviews', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return res.json() as Promise<ReviewSubmitResponse>;
  },

  getByBooking: async (bookingId: string): Promise<ReviewItem | null> => {
    const res = await fetchWithAuth(`/api/v1/reviews/booking/${bookingId}`);
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return (await res.json()) as ReviewItem | null;
  },

  getInstructorRatings: async (instructorId: string): Promise<InstructorRatingsResponse> => {
    const res = await fetchAPI(`/api/v1/reviews/instructor/${instructorId}/ratings`);
    if (!res.ok) throw new Error(await getErrorMessage(res));
    const payload = (await res.json()) as RawInstructorRatingsResponse;
    const overall = payload?.overall && typeof payload.overall === 'object'
      ? (payload.overall as Record<string, unknown>)
      : {};
    const normalizedOverall: NonNullable<InstructorRatingsResponse['overall']> = {};
    const ratingValue = overall['rating'];
    if (typeof ratingValue === 'number') {
      normalizedOverall.rating = ratingValue;
    }
    const displayRating = overall['display_rating'];
    if (typeof displayRating === 'string') {
      normalizedOverall.display_rating = displayRating;
    }
    const totalReviews = overall['total_reviews'];
    if (typeof totalReviews === 'number') {
      normalizedOverall.total_reviews = totalReviews;
    }
    const hasOverall = Object.keys(normalizedOverall).length > 0;
    return {
      ...payload,
      overall: hasOverall ? normalizedOverall : null,
    };
  },

  getSearchRating: async (instructorId: string, instructorServiceId?: string): Promise<SearchRatingResponse> => {
    const qs = instructorServiceId ? `?instructor_service_id=${encodeURIComponent(instructorServiceId)}` : '';
    const res = await fetchAPI(`/api/v1/reviews/instructor/${instructorId}/search-rating${qs}`);
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return res.json() as Promise<SearchRatingResponse>;
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
    const res = await fetchAPI(`/api/v1/reviews/instructor/${instructorId}/recent?${p.toString()}`);
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return res.json() as Promise<ReviewListPageResponse>;
  },

  getRatingsBatch: async (instructorIds: string[]): Promise<RatingsBatchResponse> => {
    const res = await fetchAPI(`/api/v1/reviews/ratings/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instructor_ids: instructorIds }),
    });
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return res.json() as Promise<RatingsBatchResponse>;
  },

  getExistingForBookings: async (bookingIds: string[]): Promise<string[]> => {
    const res = await fetchWithAuth(`/api/v1/reviews/booking/existing`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bookingIds),
    });
    if (!res.ok) throw new Error(await getErrorMessage(res));
    return res.json() as Promise<ExistingReviewIdsResponse>;
  },
};
