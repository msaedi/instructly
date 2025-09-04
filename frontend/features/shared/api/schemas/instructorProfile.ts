export async function loadInstructorProfileSchema() {
  if (process.env.NODE_ENV !== 'production') {
    const { z } = await import('zod');
    const Service = z.object({
      id: z.string(),
      hourly_rate: z.number(),
      skill: z.string().optional(),
      duration_options: z.array(z.number()).optional().default([60]),
    });
    const Profile = z.object({
      user_id: z.string(),
      services: z.array(Service).default([]),
      bio: z.string().optional().nullable(),
      areas_of_service: z.array(z.string()).optional().default([]),
    });
    return { schema: Profile };
  }
  throw new Error('loadInstructorProfileSchema should not be used in production');
}
