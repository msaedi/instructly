import { loadCreateBookingSchema } from '../booking';

describe('loadCreateBookingSchema', () => {
  const originalEnv = process.env.NODE_ENV;
  const setNodeEnv = (value: string) => {
    (process.env as Record<string, string | undefined>)['NODE_ENV'] = value;
  };

  afterEach(() => {
    setNodeEnv(originalEnv ?? '');
  });

  it('loads schema in non-production and validates data', async () => {
    setNodeEnv('test');

    const { schema } = await loadCreateBookingSchema();

    const parsed = schema.parse({
      id: 'booking-1',
      booking_date: '2024-01-01',
      start_time: '10:00:00',
      end_time: '11:00:00',
      status: 'CONFIRMED',
      instructor_id: 'inst-1',
      total_price: 120,
    });

    expect(parsed.id).toBe('booking-1');
  });

  it('throws in production', async () => {
    setNodeEnv('production');

    await expect(loadCreateBookingSchema()).rejects.toThrow(
      'loadCreateBookingSchema should not be used in production'
    );
  });
});
