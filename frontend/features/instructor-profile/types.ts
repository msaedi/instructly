import type { ServiceAreaNeighborhood } from '@/types/instructor';
export type { NYCZipCheckResponse as NYCZipCheck, ServiceAreaItem, ServiceAreasResponse } from '@/features/shared/api/types';

export type ProfileFormState = {
  first_name: string;
  last_name: string;
  postal_code: string;
  bio: string;
  service_area_summary?: string | null;
  service_area_boroughs: string[];
  service_area_neighborhoods?: ServiceAreaNeighborhood[];
  years_experience: number;
  min_advance_booking_hours?: number;
  buffer_time_hours?: number;
  street_line1?: string;
  street_line2?: string;
  locality?: string;
  administrative_area?: string;
  country_code?: string;
  place_id?: string;
  latitude?: number | null;
  longitude?: number | null;
};

// Service area response types are re-exported from the OpenAPI shim.
