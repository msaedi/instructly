import { logger } from '@/lib/logger';

export interface PreferredTeachingLocationPayload {
  address: string;
  label?: string;
}

export interface PreferredPublicSpacePayload {
  address: string;
}

export interface InstructorUpdatePayload {
  bio: string;
  areas_of_service: string[];
  years_experience: number;
  min_advance_booking_hours?: number;
  buffer_time_minutes?: number;
  preferred_teaching_locations?: PreferredTeachingLocationPayload[];
  preferred_public_spaces?: PreferredPublicSpacePayload[];
}

export interface AddressCreatePayload {
  street_line1: string;
  street_line2?: string;
  locality: string;
  administrative_area: string;
  postal_code: string;
  country_code: string;
  is_default: boolean;
  place_id?: string;
  latitude?: number;
  longitude?: number;
}

export interface ServiceAreasUpdatePayload {
  neighborhood_ids: string[];
}

export function debugProfilePayload(name: string, payload: unknown): void {
  if (process.env['NEXT_PUBLIC_PROFILE_SAVE_DEBUG'] !== '1') return;
  try {
    const obj = (payload ?? {}) as Record<string, unknown>;
    const keys = Object.keys(obj);
    logger.warn('[PROFILE_DEBUG] payload keys', { name, keys });
  } catch (error) {
    logger.warn('[PROFILE_DEBUG] failed to inspect payload', { name, error });
  }
}
