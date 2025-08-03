import { useQuery } from '@tanstack/react-query';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';

interface Review {
  id: number;
  rating: number;
  comment: string;
  reviewer_name: string;
  created_at: string;
  service_name?: string;
}

interface ReviewsResponse {
  reviews: Review[];
  total: number;
  average_rating: number;
  rating_distribution: {
    1: number;
    2: number;
    3: number;
    4: number;
    5: number;
  };
}

// Mock reviews data until the feature is built
const createMockReviews = (instructorId: string): ReviewsResponse => ({
  total: 127,
  average_rating: 4.9,
  rating_distribution: {
    1: 1,
    2: 2,
    3: 5,
    4: 25,
    5: 94,
  },
  reviews: [
    {
      id: 1,
      rating: 5,
      reviewer_name: 'Emma J.',
      created_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(), // 2 days ago
      comment: 'Amazing teacher! Sarah helped my daughter gain confidence in just a few lessons. Very patient and encouraging with beginners.',
      service_name: 'Piano Lessons',
    },
    {
      id: 2,
      rating: 5,
      reviewer_name: 'Michael R.',
      created_at: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(), // 1 week ago
      comment: 'Very knowledgeable and patient. Helped me prepare for my grade 5 exam with excellent results. Highly recommend!',
      service_name: 'Music Theory',
    },
    {
      id: 3,
      rating: 4,
      reviewer_name: 'David L.',
      created_at: new Date(Date.now() - 14 * 24 * 60 * 60 * 1000).toISOString(), // 2 weeks ago
      comment: 'Great instructor, very professional. My son has improved significantly. Would definitely recommend to other parents.',
      service_name: 'Piano Lessons',
    },
    {
      id: 4,
      rating: 5,
      reviewer_name: 'Sarah M.',
      created_at: new Date(Date.now() - 21 * 24 * 60 * 60 * 1000).toISOString(), // 3 weeks ago
      comment: 'Excellent teacher! Makes learning fun and engaging. My daughter looks forward to every lesson.',
      service_name: 'Piano Lessons',
    },
    {
      id: 5,
      rating: 5,
      reviewer_name: 'James K.',
      created_at: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(), // 1 month ago
      comment: 'Professional and patient. Great with adult learners who are starting from scratch.',
      service_name: 'Piano Lessons',
    },
  ],
});

/**
 * Hook to fetch instructor reviews
 * Currently returns mock data until reviews feature is implemented
 */
export function useInstructorReviews(instructorId: string, page: number = 1) {
  return useQuery<ReviewsResponse>({
    queryKey: ['instructors', instructorId, 'reviews', { page }],
    queryFn: async () => {
      // Return mock data for now
      // TODO: Replace with actual API call when reviews endpoint is available
      return createMockReviews(instructorId);
    },
    staleTime: CACHE_TIMES.SLOW * 2, // 30 minutes
    enabled: !!instructorId,
  });
}
