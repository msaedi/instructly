import { loadBookingListSchema } from '@/features/shared/api/schemas/bookingList';

describe('bookings list schema', () => {
  it('parses valid payload', async () => {
    const { schema } = await loadBookingListSchema();
    const payload = {
      items: [
        {
          id: '01H',
          booking_date: '2025-01-01',
          start_time: '10:00',
          end_time: '11:00',
          status: 'confirmed',
          instructor_id: '01I',
          total_price: 5000,
        },
      ],
      total: 1,
      page: 1,
      per_page: 50,
    };
    expect(schema.parse(payload)).toBeTruthy();
  });

  it('rejects missing required fields', async () => {
    const { schema } = await loadBookingListSchema();
    const bad: unknown = {
      items: [{ id: 123 }],
      total: 'one',
    };
    expect(() => schema.parse(bad)).toThrow();
  });
});
