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
      // Fetch both instructor profile and service catalog in parallel
      const [profileResponse, catalogResponse] = await Promise.all([
        publicApi.getInstructorProfile(instructorId),
        publicApi.getCatalogServices(),
      ]);

      if (profileResponse.error) {
        throw new Error(profileResponse.error);
      }

      const instructor = profileResponse.data;
      const serviceCatalog = catalogResponse.data || [];

      // Map service names from catalog and fix data structure
      const mappedServices = instructor?.services?.map((service: any) => {
        const catalogService = serviceCatalog.find((s: any) => s.id === service.service_catalog_id);
        return {
          ...service,
          skill: catalogService?.name || service.name || `Service ${service.service_catalog_id}`,
          duration_options: service.duration_options || [60], // Preserve all duration options
        };
      }) || [];

      // Ensure the instructor object has all required fields
      if (!instructor) {
        throw new Error('Instructor not found');
      }

      // Add the id field if missing (use user_id as id)
      const instructorProfile: InstructorProfile = {
        id: instructor.user_id || Number(instructorId),
        user_id: instructor.user_id,
        bio: instructor.bio || '',
        areas_of_service: instructor.areas_of_service || [],
        years_experience: instructor.years_experience || 0,
        user: instructor.user || { first_name: 'Unknown', last_initial: '' },
        services: mappedServices,
        is_verified: instructor.verified,
        background_check_completed: false, // Not provided by API
      };

      return instructorProfile;
    },
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes
    enabled: !!instructorId,
  });
}
