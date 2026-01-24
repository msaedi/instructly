import { loadBookingListSchema } from '../bookingList';
import { loadInstructorProfileSchema } from '../instructorProfile';
import { loadMeSchema } from '../me';
import { loadSearchListSchema } from '../searchList';

describe('schema loaders production guard', () => {
  const originalEnv = process.env.NODE_ENV;
  const setNodeEnv = (value: string) => {
    (process.env as Record<string, string | undefined>)['NODE_ENV'] = value;
  };

  afterEach(() => {
    setNodeEnv(originalEnv ?? '');
  });

  it('throws in production for booking list schema', async () => {
    setNodeEnv('production');
    await expect(loadBookingListSchema()).rejects.toThrow(
      'loadBookingListSchema should not be used in production'
    );
  });

  it('loads booking list schema in non-production', async () => {
    setNodeEnv('test');
    const { schema } = await loadBookingListSchema();
    const parsed = schema.parse({
      items: [
        {
          id: 'booking-1',
          booking_date: '2024-01-01',
          start_time: '10:00',
          end_time: '11:00',
          status: 'confirmed',
          instructor_id: 'inst-1',
          total_price: 120,
        },
      ],
      total: 1,
    });
    expect(parsed.items).toHaveLength(1);
  });

  it('throws in production for instructor profile schema', async () => {
    setNodeEnv('production');
    await expect(loadInstructorProfileSchema()).rejects.toThrow(
      'loadInstructorProfileSchema should not be used in production'
    );
  });

  it('loads instructor profile schema in non-production', async () => {
    setNodeEnv('test');
    const { schema } = await loadInstructorProfileSchema();
    const parsed = schema.parse({
      user_id: 'inst-1',
      services: [],
    });
    expect(parsed.user_id).toBe('inst-1');
  });

  it('throws in production for me schema', async () => {
    setNodeEnv('production');
    await expect(loadMeSchema()).rejects.toThrow(
      'loadMeSchema should not be used in production'
    );
  });

  it('loads me schema in non-production', async () => {
    setNodeEnv('test');
    const { schema } = await loadMeSchema();
    const parsed = schema.parse({
      id: 'user-1',
      email: 'test@example.com',
    });
    expect(parsed.email).toBe('test@example.com');
  });

  it('throws in production for search list schema', async () => {
    setNodeEnv('production');
    await expect(loadSearchListSchema()).rejects.toThrow(
      'loadSearchListSchema should not be used in production'
    );
  });

  it('loads search list schema in non-production', async () => {
    setNodeEnv('test');
    const { schema } = await loadSearchListSchema();
    const parsed = schema.parse({
      items: [
        {
          id: 'inst-1',
          user_id: 'user-1',
          bio: 'Bio',
          years_experience: 5,
          created_at: '2024-01-01T00:00:00Z',
          user: {
            id: 'user-1',
            first_name: 'Jane',
            last_initial: 'D',
          },
          services: [
            {
              id: 'svc-1',
              service_catalog_id: 'catalog-1',
              hourly_rate: 100,
              duration_options: [60],
            },
          ],
        },
      ],
      total: 1,
      page: 1,
      per_page: 10,
      has_next: false,
      has_prev: false,
    });
    expect(parsed.items[0]?.user.first_name).toBe('Jane');
  });
});
