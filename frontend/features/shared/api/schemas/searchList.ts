export async function loadSearchListSchema() {
  if (process.env.NODE_ENV !== 'production') {
    const { z } = await import('zod');

    const User = z.object({
      id: z.string(),
      first_name: z.string(),
      last_initial: z.string(),
    });

    const Service = z.object({
      id: z.string(),
      service_catalog_id: z.string(),
      hourly_rate: z.number(),
      description: z.string().optional(),
      duration_options: z.array(z.number()).nonempty(),
      is_active: z.boolean().optional(),
    });

    const InstructorItem = z.object({
      id: z.string(),
      user_id: z.string(),
      bio: z.string(),
      service_area_summary: z.string().optional().nullable(),
      service_area_boroughs: z.array(z.string()).optional().default([]),
      service_area_neighborhoods: z
        .array(
          z.object({
            neighborhood_id: z.string(),
            ntacode: z.string().optional().nullable(),
            name: z.string().optional().nullable(),
            borough: z.string().optional().nullable(),
          }),
        )
        .optional()
        .default([]),
      years_experience: z.number(),
      min_advance_booking_hours: z.number().optional(),
      buffer_time_minutes: z.number().optional(),
      created_at: z.string(),
      updated_at: z.string().optional(),
      user: User,
      services: z.array(Service),
    });

    const Paginated = z.object({
      items: z.array(InstructorItem),
      total: z.number().int().nonnegative(),
      page: z.number().int().nonnegative(),
      per_page: z.number().int().positive(),
      has_next: z.boolean(),
      has_prev: z.boolean(),
    });

    return { schema: Paginated };
  }
  throw new Error('loadSearchListSchema should not be used in production');
}
