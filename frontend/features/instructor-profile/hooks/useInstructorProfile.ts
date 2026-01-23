import { useMemo } from 'react';
import type { InstructorProfile, InstructorService, ServiceAreaNeighborhood, ServiceLocationType } from '@/types/instructor';
import { useInstructor } from '@/src/api/services/instructors';

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
    location_types?: ServiceLocationType[];
    offers_travel?: boolean;
    offers_at_location?: boolean;
    offers_online?: boolean;
    levels_taught?: string[];
    age_groups?: string[];
    service_catalog_name?: string;
  }>;
  bio?: string;
  service_area_boroughs?: string[];
  service_area_neighborhoods?: ServiceAreaNeighborhood[];
  service_area_summary?: string | null;
  preferred_teaching_locations?: Array<{
    address?: string | null;
    label?: string | null;
    approx_lat?: number | null;
    approx_lng?: number | null;
    neighborhood?: string | null;
  }>;
  preferred_public_spaces?: Array<{ address?: string; label?: string | null }>;
  years_experience?: number;
  favorited_count?: number;
  verified?: unknown;
  is_favorited?: unknown;
  has_profile_picture?: boolean;
  profile_picture_version?: number;
  is_live?: boolean;
  is_founding_instructor?: boolean;
  bgc_status?: string | null;
  background_check_status?: string | null;
  background_check_verified?: boolean | null;
  background_check_completed?: boolean | null;
  bgc_completed_at?: string | null;
};

/**
 * Hook to fetch detailed instructor profile with service names
 * Uses 5-minute cache as profile data can change
 *
 * ✅ MIGRATED TO V1 - Uses /api/v1/instructors/{id} endpoint
 */
export function useInstructorProfile(instructorId: string) {
  // Use v1 service to fetch instructor
  const v1Result = useInstructor(instructorId);

  // Transform v1 response to legacy format using useMemo to avoid recalculation
  const transformedData = useMemo(() => {
    if (!v1Result.data) return undefined;

    const serverInst = v1Result.data as unknown as ServerInstructorProfileResult;

    // Map service names from catalog and fix data structure
    const mappedServices: InstructorService[] = (serverInst?.services || []).map((svc) => {
      const hourlyRate = typeof svc.hourly_rate === 'number' ? svc.hourly_rate : Number.parseFloat(String(svc.hourly_rate ?? '0'));
      const result: InstructorService = {
        id: svc.id || '',
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

      if (typeof svc.offers_travel === 'boolean') {
        result.offers_travel = svc.offers_travel;
      }

      if (typeof svc.offers_at_location === 'boolean') {
        result.offers_at_location = svc.offers_at_location;
      }

      if (typeof svc.offers_online === 'boolean') {
        result.offers_online = svc.offers_online;
      }

      if (Array.isArray(svc.levels_taught) && svc.levels_taught.length) {
        result.levels_taught = svc.levels_taught;
      }

      if (Array.isArray(svc.age_groups) && svc.age_groups.length) {
        result.age_groups = svc.age_groups;
      }

      return result;
    });

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

    const bgcStatusRaw = typeof (serverInst as Record<string, unknown>)['bgc_status'] === 'string'
      ? String((serverInst as Record<string, unknown>)['bgc_status'])
      : typeof (serverInst as Record<string, unknown>)['background_check_status'] === 'string'
        ? String((serverInst as Record<string, unknown>)['background_check_status'])
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
              const labelRaw = typeof loc.label === 'string' ? loc.label.trim() : '';
              const approxLat = typeof loc.approx_lat === 'number' ? loc.approx_lat : undefined;
              const approxLng = typeof loc.approx_lng === 'number' ? loc.approx_lng : undefined;
              const neighborhood = typeof loc.neighborhood === 'string' ? loc.neighborhood.trim() : '';

              if (!address && !labelRaw && !Number.isFinite(approxLat) && !Number.isFinite(approxLng) && !neighborhood) {
                return null;
              }

              const payload: {
                address?: string;
                label?: string;
                approx_lat?: number;
                approx_lng?: number;
                neighborhood?: string;
              } = {};
              if (address) payload.address = address;
              if (labelRaw) payload.label = labelRaw;
              if (typeof approxLat === 'number' && Number.isFinite(approxLat)) {
                payload.approx_lat = approxLat;
              }
              if (typeof approxLng === 'number' && Number.isFinite(approxLng)) {
                payload.approx_lng = approxLng;
              }
              if (neighborhood) payload.neighborhood = neighborhood;
              return payload;
            })
            .filter(
              (
                loc
              ): loc is {
                address?: string;
                label?: string;
                approx_lat?: number;
                approx_lng?: number;
                neighborhood?: string;
              } => loc !== null
            )
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
      ...(typeof serverInst.is_live === 'boolean' && { is_live: serverInst.is_live }),
      ...(typeof serverInst.is_founding_instructor === 'boolean' && {
        is_founding_instructor: serverInst.is_founding_instructor,
      }),
      // Only include optional properties when they have actual values
      ...(typeof (serverInst as Record<string, unknown>)['verified'] !== 'undefined' && { is_verified: Boolean((serverInst as Record<string, unknown>)['verified']) }),
      ...(typeof (serverInst as Record<string, unknown>)['is_favorited'] !== 'undefined' && { is_favorited: Boolean((serverInst as Record<string, unknown>)['is_favorited']) }),
      ...(typeof bgcStatusRaw === 'string' && {
        bgc_status: bgcStatusRaw,
      }),
      ...(typeof (serverInst as Record<string, unknown>)['background_check_verified'] === 'boolean' && {
        background_check_completed: Boolean(
          (serverInst as Record<string, unknown>)['background_check_verified']
        ),
      }),
      ...(typeof (serverInst as Record<string, unknown>)['background_check_completed'] === 'boolean' && {
        background_check_completed: Boolean(
          (serverInst as Record<string, unknown>)['background_check_completed']
        ),
      }),
      ...(typeof (serverInst as Record<string, unknown>)['bgc_completed_at'] === 'string' && {
        bgc_completed_at: String((serverInst as Record<string, unknown>)['bgc_completed_at']),
      }),
    };

    return instructorProfile;
  }, [v1Result.data, instructorId]);

  // Return the v1 result shape but with transformed data
  return {
    ...v1Result,
    data: transformedData,
  };
}
