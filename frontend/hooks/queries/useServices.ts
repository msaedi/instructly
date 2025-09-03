import React from 'react';
import { useQuery, useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { convertApiResponse } from '@/lib/react-query/api';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { publicApi } from '@/features/shared/api/client';
import type { ServiceCategory, CatalogService } from '@/features/shared/api/client';
import { env } from '@/lib/env';

/**
 * Services page React Query hooks
 *
 * These hooks provide efficient data fetching for the services catalog
 * with proper caching and progressive loading support.
 */

/**
 * Hook to fetch all service categories
 * Used for navigation and filtering
 *
 * @example
 * ```tsx
 * function ServiceFilters() {
 *   const { data: categories, isLoading } = useServiceCategories();
 *
 *   return (
 *     <div>
 *       {categories?.map(category => (
 *         <FilterButton key={category.id} {...category} />
 *       ))}
 *     </div>
 *   );
 * }
 * ```
 */
export function useServiceCategories() {
  return useQuery<ServiceCategory[]>({
    queryKey: queryKeys.services.categories,
    queryFn: async () => {
      const response = await publicApi.getServiceCategories();
      return convertApiResponse(response);
    },
    staleTime: CACHE_TIMES.STATIC, // 1 hour - categories rarely change
    gcTime: CACHE_TIMES.STATIC * 2, // Keep for 2 hours
  });
}

/**
 * Hook to fetch all services with instructor counts
 * This is the main hook for the services page
 *
 * @example
 * ```tsx
 * function ServicesPage() {
 *   const { data, isLoading, error } = useAllServicesWithInstructors();
 *
 *   if (isLoading) return <LoadingSpinner />;
 *
 *   return (
 *     <div>
 *       {data?.categories.map(category => (
 *         <CategorySection key={category.id} {...category} />
 *       ))}
 *     </div>
 *   );
 * }
 * ```
 */
export function useAllServicesWithInstructors() {
  return useQuery({
    queryKey: queryKeys.services.withInstructors,
    queryFn: async () => {
      const response = await publicApi.getAllServicesWithInstructors();
      return convertApiResponse(response);
    },
    staleTime: CACHE_TIMES.SLOW, // 15 minutes - service counts change moderately
    gcTime: CACHE_TIMES.SLOW * 2, // 30 minutes
  });
}

/**
 * Hook to fetch services by category
 * Used when filtering by a specific category
 */
export function useServicesByCategory(categorySlug: string, enabled: boolean = true) {
  return useQuery<CatalogService[]>({
    queryKey: queryKeys.services.byCategory(categorySlug),
    queryFn: async () => {
      const response = await publicApi.getCatalogServices(categorySlug);
      return convertApiResponse(response);
    },
    enabled: enabled && !!categorySlug,
    staleTime: CACHE_TIMES.SLOW, // 15 minutes
    gcTime: CACHE_TIMES.SLOW * 2, // 30 minutes
  });
}

/**
 * Interface for service search filters
 */
interface ServiceSearchFilters {
  query?: string;
  category?: string;
  minPrice?: number;
  maxPrice?: number;
  onlineOnly?: boolean;
  certificationRequired?: boolean;
}

/**
 * Hook for infinite scroll service search
 * Use this when implementing search with pagination
 *
 * @example
 * ```tsx
 * function ServiceSearch() {
 *   const {
 *     data,
 *     fetchNextPage,
 *     hasNextPage,
 *     isFetchingNextPage
 *   } = useServicesInfiniteSearch({ category: 'music' });
 *
 *   return (
 *     <InfiniteScroll
 *       dataLength={data?.pages.length || 0}
 *       next={fetchNextPage}
 *       hasMore={hasNextPage}
 *       loader={<LoadingSpinner />}
 *     >
 *       {data?.pages.map((page, i) => (
 *         <React.Fragment key={i}>
 *           {page.services.map(service => (
 *             <ServiceCard key={service.id} {...service} />
 *           ))}
 *         </React.Fragment>
 *       ))}
 *     </InfiniteScroll>
 *   );
 * }
 * ```
 */
export function useServicesInfiniteSearch(filters: ServiceSearchFilters) {
  return useInfiniteQuery({
    queryKey: [...queryKeys.services.all, 'search', filters] as const,
    queryFn: async ({ pageParam = 0 }) => {
      // Build query string from filters
      const params = new URLSearchParams();
      if (filters.query) params.append('q', filters.query);
      if (filters.category) params.append('category', filters.category);
      if (filters.minPrice) params.append('min_price', filters.minPrice.toString());
      if (filters.maxPrice) params.append('max_price', filters.maxPrice.toString());
      if (filters.onlineOnly) params.append('online_only', 'true');
      if (filters.certificationRequired) params.append('certification_required', 'true');
      params.append('page', pageParam.toString());
      params.append('limit', '20');

      const response = await fetch(
        `${env.get('NEXT_PUBLIC_API_BASE') || 'http://localhost:8000'}/services/search?${params}`
      );

      if (!response.ok) {
        throw new Error('Failed to fetch services');
      }

      return response.json();
    },
    getNextPageParam: (lastPage, _pages) => {
      // Assume the API returns { services: [], hasMore: boolean, nextPage: number }
      return lastPage.hasMore ? lastPage.nextPage : undefined;
    },
    initialPageParam: 0,
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes for search results
    gcTime: CACHE_TIMES.SLOW, // 15 minutes
  });
}

/**
 * Progressive loading configuration for services page
 */
export const PROGRESSIVE_LOADING = {
  INITIAL_COUNT: 15,
  LOAD_MORE_COUNT: 10,
} as const;

/**
 * Hook to manage progressive loading state
 * This helps implement the scroll-based loading on the services page
 *
 * @example
 * ```tsx
 * function CategoryServices({ category, services }) {
 *   const { visibleCount, loadMore, hasMore } = useProgressiveLoading(
 *     services.length,
 *     PROGRESSIVE_LOADING.INITIAL_COUNT
 *   );
 *
 *   const visibleServices = services.slice(0, visibleCount);
 *
 *   return (
 *     <>
 *       {visibleServices.map(service => (
 *         <ServiceItem key={service.id} {...service} />
 *       ))}
 *       {hasMore && (
 *         <div ref={loadMoreRef} />
 *       )}
 *     </>
 *   );
 * }
 * ```
 */
export function useProgressiveLoading(
  totalItems: number,
  initialCount: number = PROGRESSIVE_LOADING.INITIAL_COUNT
) {
  const [visibleCount, setVisibleCount] = React.useState(initialCount);

  const loadMore = React.useCallback(() => {
    setVisibleCount((current) =>
      Math.min(current + PROGRESSIVE_LOADING.LOAD_MORE_COUNT, totalItems)
    );
  }, [totalItems]);

  const hasMore = visibleCount < totalItems;

  const reset = React.useCallback(() => {
    setVisibleCount(initialCount);
  }, [initialCount]);

  // Reset when total items changes (e.g., new search)
  React.useEffect(() => {
    reset();
  }, [totalItems, reset]);

  return {
    visibleCount,
    loadMore,
    hasMore,
    reset,
  };
}

/**
 * Hook to prefetch service data for better UX
 * Use this on hover or when user is likely to navigate
 *
 * @example
 * ```tsx
 * function ServiceLink({ categorySlug }) {
 *   const prefetch = usePrefetchServices();
 *
 *   return (
 *     <Link
 *       href={`/services/${categorySlug}`}
 *       onMouseEnter={() => prefetch.byCategory(categorySlug)}
 *     >
 *       View Services
 *     </Link>
 *   );
 * }
 * ```
 */
export function usePrefetchServices() {
  const queryClient = useQueryClient();

  return {
    all: () => {
      queryClient.prefetchQuery({
        queryKey: queryKeys.services.withInstructors,
        queryFn: async () => {
          const response = await publicApi.getAllServicesWithInstructors();
          return convertApiResponse(response);
        },
        staleTime: CACHE_TIMES.SLOW,
      });
    },
    byCategory: (categorySlug: string) => {
      queryClient.prefetchQuery({
        queryKey: queryKeys.services.byCategory(categorySlug),
        queryFn: async () => {
          const response = await publicApi.getCatalogServices(categorySlug);
          return convertApiResponse(response);
        },
        staleTime: CACHE_TIMES.SLOW,
      });
    },
    categories: () => {
      queryClient.prefetchQuery({
        queryKey: queryKeys.services.categories,
        queryFn: async () => {
          const response = await publicApi.getServiceCategories();
          return convertApiResponse(response);
        },
        staleTime: CACHE_TIMES.STATIC,
      });
    },
  };
}
