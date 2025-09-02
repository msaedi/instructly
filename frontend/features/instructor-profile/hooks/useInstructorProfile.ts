import { useQuery } from '@tanstack/react-query';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { publicApi } from '@/features/shared/api/client';
import type { InstructorProfile } from '@/types/instructor';

/**
 * Hook to fetch detailed instructor profile with service names
 * Uses 5-minute cache as profile data can change
 */
export function useInstructorProfile(instructorId: string) {
  return useQuery<InstructorProfile>({
    queryKey: queryKeys.instructors.detail(instructorId),
    queryFn: async () => {
      // Fetch both instructor profile and service catalog.
      // If either returns a rate limit, wait and retry once in this hook to avoid surfacing errors.
      const runWithRateLimitRetry = async <T>(fn: () => Promise<{ data?: T; error?: string; status: number; retryAfterSeconds?: number }>): Promise<T> => {
        const res = await fn();
        if (res.status === 429) {
          const waitMs = res.retryAfterSeconds ? res.retryAfterSeconds * 1000 : 0;
          if (waitMs > 0) {
            await new Promise((r) => setTimeout(r, waitMs));
            const res2 = await fn();
            if (res2.status === 429) {
              throw new Error(res2.error || 'Temporarily busy. Please try again.');
            }
            if (res2.error) throw new Error(res2.error);
            return res2.data as T;
          }
        }
        if (res.error) throw new Error(res.error);
        return res.data as T;
      };

      const [instructor, serviceCatalog] = await Promise.all([
        runWithRateLimitRetry(() => publicApi.getInstructorProfile(instructorId)),
        runWithRateLimitRetry(() => publicApi.getCatalogServices()),
      ]);

      const catalogList = serviceCatalog || [];

      // Map service names from catalog and fix data structure
      const mappedServices = instructor?.services?.map((service: unknown) => {
        const svc = service as { service_catalog_id: string; name?: string; duration_options?: number[]; [key: string]: unknown };
        const catalogService = catalogList.find((s: { id: string; name: string }) => s.id === svc.service_catalog_id);
        return {
          ...svc,
          skill: catalogService?.name || svc.name || `Service ${svc.service_catalog_id}`,
          duration_options: svc.duration_options || [60], // Preserve all duration options
        };
      }) || [];

      // Ensure the instructor object has all required fields
      if (!instructor) {
        throw new Error('Instructor not found');
      }

      // Add the id field if missing (use user_id as id)
      const instructorProfile: InstructorProfile = {
        id: instructor.user_id || instructorId,
        user_id: instructor.user_id,
        bio: instructor.bio || '',
        areas_of_service: instructor.areas_of_service || [],
        years_experience: instructor.years_experience || 0,
        user: instructor.user || { first_name: 'Unknown', last_initial: '' },
        services: mappedServices,
        is_verified: instructor.verified,
        background_check_completed: false, // Not provided by API
        favorited_count: instructor.favorited_count || 0,
        is_favorited: instructor.is_favorited,
      };

      return instructorProfile;
    },
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes
    enabled: !!instructorId,
  });
}
