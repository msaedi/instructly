export async function loadMeSchema() {
  const { z } = await import('zod');
  const User = z.object({
    id: z.string(),
    email: z.string().email(),
    first_name: z.string().nullable().optional(),
    last_name: z.string().nullable().optional(),
    roles: z.array(z.string()).optional().default([]),
  });
  return { schema: User };
}
