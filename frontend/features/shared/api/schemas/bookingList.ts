export async function loadBookingListSchema() {
  const { z } = await import('zod');
  const Booking = z.object({
    id: z.string(),
    booking_date: z.string(),
    start_time: z.string(),
    end_time: z.string(),
    status: z.string(),
    instructor_id: z.string(),
    total_price: z.number(),
  });
  const Paginated = z.object({
    items: z.array(Booking),
    total: z.number().int().nonnegative(),
    page: z.number().int().nonnegative().optional(),
    per_page: z.number().int().positive().optional(),
  });
  return { schema: Paginated };
}
