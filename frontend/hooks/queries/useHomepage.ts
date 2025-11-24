import { useQuery, useQueries } from '@tanstack/react-query';
import { queryFn, convertApiResponse } from '@/lib/react-query/api';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { publicApi, TopServicesResponse } from '@/features/shared/api/client';
import { useCurrentUser } from '@/src/api/hooks/useSession';
import type { BookingListResponse } from '@/features/shared/api/types';
import { SearchHistoryItem } from '@/lib/searchTracking';
import { httpJson } from '@/features/shared/api/http';
import { withApiBase } from '@/lib/apiBase';
import { loadBookingListSchema } from '@/features/shared/api/schemas/bookingList';

/**
 * Homepage-specific React Query hooks
 *
 * These hooks fetch all the data needed for the homepage with proper
 * caching strategies to minimize API calls and improve performance.
 */

/**
 * Hook to fetch user's upcoming bookings
 *
 * @example
 * ```tsx
 * function UpcomingLessons() {
 *   const { data: bookings, isLoading } = useUpcomingBookings();
 *
 *   if (isLoading) return <SkeletonCards />;
 *   if (!bookings?.length) return null;
 *
 *   return <BookingCards bookings={bookings} />;
 * }
 * ```
 */
export function useUpcomingBookings(limit: number = 2) {
  const user = useCurrentUser();
  const isAuthenticated = !!user;

  return useQuery<BookingListResponse>({
    queryKey: queryKeys.bookings.upcoming(limit),
    queryFn: queryFn(`/bookings/upcoming?limit=${limit}`, {
      requireAuth: true,
    }),
    enabled: isAuthenticated, // Only run if user is authenticated
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes - bookings can change
    gcTime: CACHE_TIMES.FREQUENT * 2, // Keep in cache for 10 minutes
    refetchInterval: 1000 * 60 * 5, // Refetch every 5 minutes for updates
  });
}

/**
 * Hook to fetch recent search history
 * Works for both authenticated users and guests
 *
 * @example
 * ```tsx
 * function RecentSearches() {
 *   const { data: searches, isLoading } = useRecentSearches();
 *
 *   return (
 *     <div>
 *       {searches?.map(search => (
 *         <SearchItem key={search.id} {...search} />
 *       ))}
 *     </div>
 *   );
 * }
 * ```
 */
export function useRecentSearches(limit: number = 3) {
  return useQuery({
    queryKey: [...queryKeys.search.recent, { limit }] as const,
    queryFn: async () => {
      const response = await publicApi.getRecentSearches(limit);
      return convertApiResponse(response);
    },
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes
    gcTime: CACHE_TIMES.SLOW, // 15 minutes
    // Refetch when window focuses to sync cross-tab changes
    refetchOnWindowFocus: true,
  });
}

/**
 * Hook to fetch featured services/categories with top services
 * This powers the dynamic service pills on the homepage
 *
 * @example
 * ```tsx
 * function ServiceCategories() {
 *   const { data: categories, isLoading } = useFeaturedServices();
 *
 *   return (
 *     <div className="grid grid-cols-7">
 *       {categories?.map(category => (
 *         <CategoryCard key={category.id} {...category} />
 *       ))}
 *     </div>
 *   );
 * }
 * ```
 */
export function useFeaturedServices() {
  return useQuery({
    queryKey: queryKeys.services?.featured || (['services', 'featured'] as const),
    queryFn: async () => {
      const response = await publicApi.getTopServicesPerCategory();
      return convertApiResponse(response);
    },
    staleTime: CACHE_TIMES.STATIC, // 1 hour - rarely changes
    gcTime: CACHE_TIMES.STATIC * 2, // Keep for 2 hours
  });
}

/**
 * Hook to fetch completed bookings for "Book Again" section
 * Only for authenticated users
 */
export function useBookingHistory(limit: number = 50) {
  const user = useCurrentUser();
  const isAuthenticated = !!user;

  return useQuery({
    queryKey: [...queryKeys.bookings.history(), { status: 'COMPLETED', limit }] as const,
    queryFn: async () =>
      httpJson<BookingListResponse>(
        withApiBase(`/bookings/?status=COMPLETED&per_page=${limit}`),
        { method: 'GET' },
        loadBookingListSchema,
        { endpoint: 'GET /bookings' }
      ),
    enabled: isAuthenticated,
    staleTime: CACHE_TIMES.SLOW, // 15 minutes - historical data
    gcTime: CACHE_TIMES.SLOW * 2, // 30 minutes
  });
}

/**
 * Interface for homepage data result
 */
interface HomepageData {
  upcomingBookings: {
    data?: BookingListResponse;
    isLoading: boolean;
    error: Error | null;
  };
  recentSearches: {
    data?: SearchHistoryItem[];
    isLoading: boolean;
    error: Error | null;
  };
  featuredServices: {
    data?: TopServicesResponse;
    isLoading: boolean;
    error: Error | null;
  };
  bookingHistory: {
    data?: BookingListResponse;
    isLoading: boolean;
    error: Error | null;
  };
  isAnyLoading: boolean;
  isInitialLoading: boolean;
}

/**
 * Composite hook that fetches all homepage data in parallel
 * This is the recommended way to load homepage data efficiently
 *
 * @example
 * ```tsx
 * function Homepage() {
 *   const {
 *     upcomingBookings,
 *     recentSearches,
 *     featuredServices,
 *     isInitialLoading
 *   } = useHomepageData();
 *
 *   if (isInitialLoading) return <HomepageSkeleton />;
 *
 *   return (
 *     <div>
 *       {upcomingBookings.data && <UpcomingLessons bookings={upcomingBookings.data} />}
 *       {recentSearches.data && <RecentSearches searches={recentSearches.data} />}
 *       {featuredServices.data && <ServiceGrid categories={featuredServices.data} />}
 *     </div>
 *   );
 * }
 * ```
 */
export function useHomepageData(): HomepageData {
  const user = useCurrentUser();
  const isAuthenticated = !!user;

  // Define all queries
  const queries = useQueries({
    queries: [
      // Upcoming bookings - only if authenticated
      {
        queryKey: queryKeys.bookings.upcoming(2),
        queryFn: queryFn<BookingListResponse>('/bookings/upcoming?limit=2', {
          requireAuth: true,
        }),
        enabled: isAuthenticated,
        staleTime: CACHE_TIMES.FREQUENT,
        gcTime: CACHE_TIMES.FREQUENT * 2,
        refetchInterval: 1000 * 60 * 5,
      },
      // Recent searches - always fetch
      {
        queryKey: queryKeys.search.recent,
        queryFn: async () => {
          const response = await publicApi.getRecentSearches(3);
          return convertApiResponse(response);
        },
        staleTime: CACHE_TIMES.FREQUENT,
        gcTime: CACHE_TIMES.SLOW,
        refetchOnWindowFocus: true,
      },
      // Featured services - always fetch
      {
        queryKey: queryKeys.services?.featured || (['services', 'featured'] as const),
        queryFn: async () => {
          const response = await publicApi.getTopServicesPerCategory();
          return convertApiResponse(response);
        },
        staleTime: CACHE_TIMES.STATIC,
        gcTime: CACHE_TIMES.STATIC * 2,
      },
      // Booking history - only if authenticated
      {
        queryKey: queryKeys.bookings.history(1), // Page 1 for BookAgain component
        queryFn: async () =>
          httpJson<BookingListResponse>(
            withApiBase('/bookings/?status=COMPLETED&per_page=50'),
            { method: 'GET' },
            loadBookingListSchema,
            { endpoint: 'GET /bookings' }
          ),
        enabled: isAuthenticated,
        staleTime: CACHE_TIMES.SLOW,
        gcTime: CACHE_TIMES.SLOW * 2,
      },
    ],
  });

  // Map query results
  const [upcomingQuery, searchesQuery, servicesQuery, historyQuery] = queries;

  return {
    upcomingBookings: {
      ...(upcomingQuery.data && { data: upcomingQuery.data }),
      isLoading: upcomingQuery.isLoading,
      error: upcomingQuery.error,
    },
    recentSearches: {
      data: searchesQuery.data as unknown as SearchHistoryItem[],
      isLoading: searchesQuery.isLoading,
      error: searchesQuery.error,
    },
    featuredServices: {
      ...(servicesQuery.data && { data: servicesQuery.data }),
      isLoading: servicesQuery.isLoading,
      error: servicesQuery.error,
    },
    bookingHistory: {
      ...(historyQuery.data && { data: historyQuery.data }),
      isLoading: historyQuery.isLoading,
      error: historyQuery.error,
    },
    // Aggregate loading states
    isAnyLoading: queries.some((q) => q.isLoading),
    isInitialLoading: queries.some((q) => q.isLoading && !q.data),
  };
}
