import type { ServiceAreaNeighborhood } from '@/types/instructor';

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

export type ServiceAreaItem = {
  id: string;
  neighborhood_id?: string;
  ntacode?: string | null;
  name?: string | null;
  borough?: string | null;
  code?: string | null;
};

export type ServiceAreasResponse = { items: ServiceAreaItem[]; total: number };
export type NYCZipCheck = { is_nyc: boolean; borough?: string | null };
