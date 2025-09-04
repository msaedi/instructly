export async function loadCreateBookingSchema() {
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
  return { schema: Booking };
}
