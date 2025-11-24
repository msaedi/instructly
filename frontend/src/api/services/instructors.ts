/**
 * Instructor Service Layer
 *
 * Domain-friendly wrappers around Orval-generated instructor hooks.
 * This is the ONLY layer that should directly import from generated/instructors-v1.
 *
 * Components should use these hooks, not the raw Orval-generated ones.
 */

import { queryKeys } from '@/src/api/queryKeys';
import {
  useListInstructorsApiV1InstructorsGet,
  useGetMyProfileApiV1InstructorsMeGet,
  useGetInstructorApiV1InstructorsInstructorIdGet,
  useGetCoverageApiV1InstructorsInstructorIdCoverageGet,
  useCreateProfileApiV1InstructorsMePost,
  useUpdateProfileApiV1InstructorsMePut,
  useDeleteProfileApiV1InstructorsMeDelete,
  useGoLiveApiV1InstructorsMeGoLivePost,
} from '@/src/api/generated/instructors-v1/instructors-v1';
import type {
  ListInstructorsApiV1InstructorsGetParams,
  InstructorProfileResponse,
  InstructorProfileCreate,
  InstructorProfileUpdate,
} from '@/src/api/generated/instructly.schemas';

/**
 * List instructors with optional filters.
 *
 * @param params - Filter parameters (service_catalog_id required)
 * @example
 * ```tsx
 * function InstructorList() {
 *   const { data, isLoading } = useInstructorsList({
 *     service_catalog_id: 'yoga-123'
 *   });
 *
 *   if (isLoading) return <div>Loading...</div>;
 *
 *   return <div>{data?.items.length} instructors</div>;
 * }
 * ```
 */
export function useInstructorsList(params: ListInstructorsApiV1InstructorsGetParams) {
  return useListInstructorsApiV1InstructorsGet(params, {
    query: {
      queryKey: queryKeys.instructors.list(params),
      staleTime: 1000 * 60 * 5, // 5 minutes
    },
  });
}

/**
 * Get current instructor profile (/instructors/me).
 *
 * Returns the authenticated user's instructor profile.
 * Use this for instructor dashboard, profile settings, etc.
 *
 * @example
 * ```tsx
 * function InstructorDashboard() {
 *   const { data: profile, isLoading } = useInstructorMe();
 *
 *   if (isLoading) return <div>Loading...</div>;
 *   if (!profile) return <div>No instructor profile found</div>;
 *
 *   return <div>Welcome, {profile.bio}</div>;
 * }
 * ```
 */
export function useInstructorMe() {
  return useGetMyProfileApiV1InstructorsMeGet({
    query: {
      queryKey: queryKeys.instructors.me,
      staleTime: 1000 * 60 * 15, // 15 minutes
    },
  });
}

/**
 * Get instructor profile by ID.
 *
 * @param instructorId - ULID of the instructor
 * @example
 * ```tsx
 * function InstructorProfile({ instructorId }: { instructorId: string }) {
 *   const { data: instructor, isLoading } = useInstructor(instructorId);
 *
 *   if (isLoading) return <div>Loading...</div>;
 *   if (!instructor) return <div>Instructor not found</div>;
 *
 *   return <div>{instructor.bio}</div>;
 * }
 * ```
 */
export function useInstructor(instructorId: string) {
  return useGetInstructorApiV1InstructorsInstructorIdGet(instructorId, {
    query: {
      queryKey: queryKeys.instructors.detail(instructorId),
      staleTime: 1000 * 60 * 15, // 15 minutes
    },
  });
}

/**
 * Get instructor service area coverage (GeoJSON).
 *
 * @param instructorId - ULID of the instructor
 * @example
 * ```tsx
 * function CoverageMap({ instructorId }: { instructorId: string }) {
 *   const { data: coverage } = useInstructorCoverage(instructorId);
 *
 *   if (!coverage) return null;
 *
 *   return <Map geojson={coverage} />;
 * }
 * ```
 */
export function useInstructorCoverage(instructorId: string) {
  return useGetCoverageApiV1InstructorsInstructorIdCoverageGet(instructorId, {
    query: {
      queryKey: queryKeys.instructors.coverage(instructorId),
      staleTime: 1000 * 60 * 60, // 1 hour (coverage changes rarely)
    },
  });
}

/**
 * Create instructor profile mutation.
 *
 * @example
 * ```tsx
 * function CreateProfileForm() {
 *   const createProfile = useCreateInstructorProfile();
 *
 *   const handleSubmit = async (data: InstructorProfileCreate) => {
 *     await createProfile.mutateAsync({ data });
 *   };
 *
 *   return <form onSubmit={handleSubmit}>...</form>;
 * }
 * ```
 */
export function useCreateInstructorProfile() {
  return useCreateProfileApiV1InstructorsMePost();
}

/**
 * Update instructor profile mutation.
 *
 * @example
 * ```tsx
 * function EditProfileForm() {
 *   const updateProfile = useUpdateInstructorProfile();
 *
 *   const handleSubmit = async (data: InstructorProfileUpdate) => {
 *     await updateProfile.mutateAsync({ data });
 *   };
 *
 *   return <form onSubmit={handleSubmit}>...</form>;
 * }
 * ```
 */
export function useUpdateInstructorProfile() {
  return useUpdateProfileApiV1InstructorsMePut();
}

/**
 * Delete instructor profile mutation.
 *
 * @example
 * ```tsx
 * function DeleteProfileButton() {
 *   const deleteProfile = useDeleteInstructorProfile();
 *
 *   const handleDelete = async () => {
 *     if (confirm('Are you sure?')) {
 *       await deleteProfile.mutateAsync();
 *     }
 *   };
 *
 *   return <button onClick={handleDelete}>Delete Profile</button>;
 * }
 * ```
 */
export function useDeleteInstructorProfile() {
  return useDeleteProfileApiV1InstructorsMeDelete();
}

/**
 * Go live mutation - activate instructor profile.
 *
 * @example
 * ```tsx
 * function GoLiveButton() {
 *   const goLive = useGoLiveInstructor();
 *
 *   const handleGoLive = async () => {
 *     await goLive.mutateAsync();
 *   };
 *
 *   return <button onClick={handleGoLive}>Go Live</button>;
 * }
 * ```
 */
export function useGoLiveInstructor() {
  return useGoLiveApiV1InstructorsMeGoLivePost();
}

/**
 * Type exports for convenience
 */
export type {
  InstructorProfileResponse,
  InstructorProfileCreate,
  InstructorProfileUpdate,
  ListInstructorsApiV1InstructorsGetParams as InstructorListParams,
};
