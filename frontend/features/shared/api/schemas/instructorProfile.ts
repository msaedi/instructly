export async function loadInstructorProfileSchema() {
  if (process.env.NODE_ENV !== 'production') {
    const { z } = await import('zod');
    const PreferredPlace = z.object({
      address: z.string().optional(),
      label: z.string().optional().nullable(),
      approx_lat: z.number().optional(),
      approx_lng: z.number().optional(),
      neighborhood: z.string().optional().nullable(),
    });
    const Service = z.object({
      id: z.string(),
      hourly_rate: z.number(),
      skill: z.string().optional(),
      duration_options: z.array(z.number()).optional().default([60]),
      description: z.string().optional().nullable(),
      location_types: z.array(z.enum(['in_person', 'online'])).optional().default([]),
      offers_travel: z.boolean().optional(),
      offers_at_location: z.boolean().optional(),
      offers_online: z.boolean().optional(),
      levels_taught: z.array(z.string()).optional().default([]),
      age_groups: z.array(z.string()).optional().default([]),
      service_catalog_id: z.string().optional(),
      service_catalog_name: z.string().optional(),
    });
    const Neighborhood = z.object({
      neighborhood_id: z.string(),
      ntacode: z.string().optional().nullable(),
      name: z.string().optional().nullable(),
      borough: z.string().optional().nullable(),
    });
    const Profile = z.object({
      user_id: z.string(),
      services: z.array(Service).default([]),
      bio: z.string().optional().nullable(),
      service_area_summary: z.string().optional().nullable(),
      service_area_boroughs: z.array(z.string()).optional().default([]),
      service_area_neighborhoods: z.array(Neighborhood).optional().default([]),
      preferred_teaching_locations: z.array(PreferredPlace).optional().default([]),
      preferred_public_spaces: z.array(PreferredPlace).optional().default([]),
    });
    return { schema: Profile };
  }
  throw new Error('loadInstructorProfileSchema should not be used in production');
}
