/**
 * useKidsAvailableServices - Hook for fetching kids-available services
 *
 * Provides cached access to the list of services available for kids.
 * Uses React Query to prevent duplicate API calls and provide caching.
 *
 * @example
 * ```tsx
 * function KidsServicesSection() {
 *   const { data: kidsServices, isLoading } = useKidsAvailableServices();
 *
 *   if (isLoading) return <LoadingSkeleton />;
 *
 *   return (
 *     <div>
 *       {kidsServices?.map(service => (
 *         <ServiceBadge key={service.id} name={service.name} />
 *       ))}
 *     </div>
 *   );
 * }
 * ```
 */
import { useQuery } from '@tanstack/react-query';
import { publicApi } from '@/features/shared/api/client';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';

interface KidsService {
  id: string;
  name: string;
  slug: string;
}

/**
 * Hook to fetch the list of services that are available for kids.
 *
 * @param enabled - Whether to enable the query (default: true)
 * @returns React Query result with array of kids-available services
 */
export function useKidsAvailableServices(enabled: boolean = true) {
  return useQuery<KidsService[]>({
    queryKey: ['services', 'kids-available'],
    queryFn: async () => {
      const response = await publicApi.getKidsAvailableServices();
      return response.data ?? [];
    },
    enabled,
    staleTime: CACHE_TIMES.STATIC, // 1 hour - kids services list rarely changes
    gcTime: CACHE_TIMES.STATIC * 2, // 2 hours
  });
}
