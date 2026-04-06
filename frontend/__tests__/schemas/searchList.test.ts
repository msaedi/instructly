import { loadSearchListSchema } from '@/features/shared/api/schemas/searchList';

describe('search list schema', () => {
  test('valid list passes', async () => {
    const { schema } = await loadSearchListSchema();
    const payload = {
      items: [
        {
          id: '01H',
          user_id: '01H',
          bio: 'hi',
          service_area_summary: 'Manhattan',
          service_area_boroughs: ['Manhattan'],
          service_area_neighborhoods: [
            {
              display_key: 'n1',
              display_name: 'Chelsea',
              borough: 'Manhattan',
            },
          ],
          years_experience: 1,
          non_travel_buffer_minutes: 15,
          travel_buffer_minutes: 60,
          overnight_protection_enabled: true,
          created_at: new Date().toISOString(),
          user: { id: '01H', first_name: 'A', last_initial: 'B.' },
          services: [
            {
              id: '01H',
              service_catalog_id: '01H',
              hourly_rate: 50,
              duration_options: [60],
            },
          ],
        },
      ],
      total: 1,
      page: 1,
      per_page: 20,
      has_next: false,
      has_prev: false,
    };
    expect(schema.parse(payload)).toBeTruthy();
  });

  test('invalid list fails', async () => {
    const { schema } = await loadSearchListSchema();
    const badPayload: unknown = { items: [{}], total: 'x', page: 1, per_page: 20, has_next: false, has_prev: false };
    expect(() => schema.parse(badPayload)).toThrow();
  });
});
