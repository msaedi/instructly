import { useQuery } from '@tanstack/react-query';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import type { InstructorProfile, InstructorService, ServiceAreaNeighborhood } from '@/types/instructor';
import { httpJson } from '@/features/shared/api/http';
import { loadInstructorProfileSchema } from '@/features/shared/api/schemas/instructorProfile';
import { normalizeInstructorServices } from '@/lib/instructorServices';

type ServerInstructorProfileResult = {
  id?: string;
  user_id: string;
  user?: { first_name: string; last_initial: string; has_profile_picture?: boolean; profile_picture_version?: number };
  services?: Array<{
    id?: string;
    service_catalog_id?: string;
    name?: string;
    skill?: string;
    duration_options?: number[];
    hourly_rate?: number | string;
    description?: string | null;
    location_types?: string[];
    levels_taught?: string[];
  }>;
  bio?: string;
  service_area_boroughs?: string[];
  service_area_neighborhoods?: ServiceAreaNeighborhood[];
  service_area_summary?: string | null;
  preferred_teaching_locations?: Array<{ address?: string; label?: string | null }>;
  preferred_public_spaces?: Array<{ address?: string; label?: string | null }>;
  years_experience?: number;
  favorited_count?: number;
  verified?: unknown;
  is_favorited?: unknown;
  has_profile_picture?: boolean;
  profile_picture_version?: number;
};

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

      const [instructor] = await Promise.all([
        runWithRateLimitRetry(async () => {
          const data = await httpJson<ServerInstructorProfileResult>(
            `/instructors/${instructorId}`,
            { method: 'GET' },
            loadInstructorProfileSchema,
            { endpoint: 'GET /instructors/:id' }
          );
          return { data, status: 200 } as { data: unknown; status: number } & { error?: string; retryAfterSeconds?: number };
        }),
      ]);
      const serverInst = instructor as ServerInstructorProfileResult;

      const normalizedServices = await normalizeInstructorServices(serverInst?.services || []);

      // Map service names from catalog and fix data structure
      const mappedServices: InstructorService[] = normalizedServices.map((svc) => {
        const hourlyRate = typeof svc.hourly_rate === 'number' ? svc.hourly_rate : Number.parseFloat(String(svc.hourly_rate ?? '0'));
        const result: InstructorService = {
          id: svc.id,
          duration_options: Array.isArray(svc.duration_options) && svc.duration_options.length > 0 ? svc.duration_options : [60],
          hourly_rate: Number.isFinite(hourlyRate) ? hourlyRate : 0,
          description: svc.description ?? null,
        };

        const catalogId = svc.service_catalog_id?.trim();
        if (catalogId) {
          result.service_catalog_id = catalogId;
        }

        const catalogName = (svc.service_catalog_name ?? svc.name ?? svc.skill)?.toString().trim();
        if (catalogName) {
          result.service_catalog_name = catalogName;
        }

        const skillValue = (svc.skill ?? svc.service_catalog_name ?? svc.name)?.toString().trim();
        if (skillValue) {
          result.skill = skillValue;
        }

        if (Array.isArray(svc.location_types) && svc.location_types.length) {
          result.location_types = svc.location_types;
        }

        if (Array.isArray(svc.levels_taught) && svc.levels_taught.length) {
          result.levels_taught = svc.levels_taught;
        }

        if (Array.isArray(svc.age_groups) && svc.age_groups.length) {
          result.age_groups = svc.age_groups;
        }

        return result;
      });

      // Ensure the instructor object has all required fields
      if (!serverInst) {
        throw new Error('Instructor not found');
      }

      // Add the id field if missing (use user_id as id)
      const canonicalId = typeof (serverInst as Record<string, unknown>)['id'] === 'string'
        ? String((serverInst as Record<string, unknown>)['id'])
        : (serverInst.user_id || instructorId);

      const userHasProfilePicture = typeof serverInst.user?.has_profile_picture !== 'undefined'
        ? Boolean(serverInst.user?.has_profile_picture)
        : undefined;
      const userProfilePictureVersion = typeof serverInst.user?.profile_picture_version !== 'undefined'
        ? Number(serverInst.user?.profile_picture_version)
        : undefined;
      const topLevelHasProfilePicture = typeof (serverInst as Record<string, unknown>)['has_profile_picture'] !== 'undefined'
        ? Boolean((serverInst as Record<string, unknown>)['has_profile_picture'])
        : undefined;
      const topLevelProfilePictureVersion = typeof (serverInst as Record<string, unknown>)['profile_picture_version'] !== 'undefined'
        ? Number((serverInst as Record<string, unknown>)['profile_picture_version'])
        : undefined;

      const instructorProfile: InstructorProfile = {
        id: canonicalId,
        user_id: serverInst.user_id || canonicalId,
        bio: serverInst.bio || '',
        service_area_boroughs: serverInst.service_area_boroughs || [],
        service_area_neighborhoods: serverInst.service_area_neighborhoods || [],
        service_area_summary: serverInst.service_area_summary ?? null,
        preferred_teaching_locations: Array.isArray(serverInst.preferred_teaching_locations)
          ? serverInst.preferred_teaching_locations
              .map((loc) => {
                if (!loc || typeof loc !== 'object') return null;
                const address = typeof loc.address === 'string' ? loc.address.trim() : '';
                if (!address) return null;
                const labelRaw = typeof loc.label === 'string' ? loc.label.trim() : '';
                return labelRaw ? { address, label: labelRaw } : { address };
              })
              .filter((loc): loc is { address: string; label?: string } => loc !== null)
          : [],
        preferred_public_spaces: Array.isArray(serverInst.preferred_public_spaces)
          ? serverInst.preferred_public_spaces
              .map((loc) => {
                if (!loc || typeof loc !== 'object') return null;
                const address = typeof loc.address === 'string' ? loc.address.trim() : '';
                if (!address) return null;
                const label = typeof (loc as { label?: unknown }).label === 'string'
                  ? ((loc as { label?: string }).label ?? '').trim()
                  : '';
                return label ? { address, label } : { address };
              })
              .filter((loc): loc is { address: string; label?: string } => loc !== null)
          : [],
        years_experience: serverInst.years_experience || 0,
        user: {
          first_name: serverInst.user?.first_name || 'Unknown',
          last_initial: serverInst.user?.last_initial || '',
          ...(typeof userHasProfilePicture !== 'undefined' ? { has_profile_picture: userHasProfilePicture } : {}),
          ...(typeof userProfilePictureVersion !== 'undefined' ? { profile_picture_version: userProfilePictureVersion } : {}),
        },
        ...(typeof topLevelHasProfilePicture !== 'undefined' ? { has_profile_picture: topLevelHasProfilePicture } : {}),
        ...(typeof topLevelProfilePictureVersion !== 'undefined' ? { profile_picture_version: topLevelProfilePictureVersion } : {}),
        services: mappedServices,
        favorited_count: serverInst.favorited_count || 0,
        // Only include optional properties when they have actual values
        ...(typeof (serverInst as Record<string, unknown>)['verified'] !== 'undefined' && { is_verified: Boolean((serverInst as Record<string, unknown>)['verified']) }),
        ...(typeof (serverInst as Record<string, unknown>)['is_favorited'] !== 'undefined' && { is_favorited: Boolean((serverInst as Record<string, unknown>)['is_favorited']) }),
        ...(typeof (serverInst as Record<string, unknown>)['bgc_status'] === 'string' && {
          bgc_status: String((serverInst as Record<string, unknown>)['bgc_status']),
        }),
        ...(typeof (serverInst as Record<string, unknown>)['bgc_completed_at'] === 'string' && {
          bgc_completed_at: String((serverInst as Record<string, unknown>)['bgc_completed_at']),
        }),
      };

      return instructorProfile;
    },
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes
    enabled: !!instructorId,
  });
}
