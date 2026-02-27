/**
 * useInstructorProfileMe - Instructor profile hook (migrated to Phase 3 pattern)
 *
 * This hook now uses the new Orval-generated API client via our instructor service layer.
 * It provides the existing interface while using the new Orval-generated architecture.
 *
 * Migration notes:
 * - Uses useInstructorMe() from @/src/api/services/instructors
 * - Still returns InstructorProfile type for the existing interface
 * - Query key now managed by centralized queryKeys factory
 */

import { useGetMyProfileApiV1InstructorsMeGet } from '@/src/api/generated/instructors-v1/instructors-v1';
import { queryKeys } from '@/src/api/queryKeys';
import type { InstructorProfile } from '@/types/instructor';

/**
 * Get current instructor profile (/api/v1/instructors/me).
 *
 * @param enabled - Whether to enable the query (default: true)
 * @returns React Query result with InstructorProfile data
 *
 * @example
 * ```tsx
 * function InstructorDashboard() {
 *   const { data: profile, isLoading, error } = useInstructorProfileMe();
 *
 *   if (isLoading) return <div>Loading...</div>;
 *   if (error) return <div>Error loading profile</div>;
 *   if (!profile) return <div>No profile found</div>;
 *
 *   return <div>Welcome, {profile.user?.first_name}!</div>;
 * }
 * ```
 */
export function useInstructorProfileMe(enabled: boolean = true) {
  const result = useGetMyProfileApiV1InstructorsMeGet({
    query: {
      queryKey: queryKeys.instructors.me,
      staleTime: 1000 * 60 * 15, // 15 minutes
      enabled,
    },
  });

  // Transform the response to match the expected InstructorProfile type
  // The Orval-generated response is compatible, but we cast for type safety
  return {
    ...result,
    data: result.data as InstructorProfile | undefined,
  };
}
