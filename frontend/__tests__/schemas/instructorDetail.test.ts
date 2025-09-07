import { loadInstructorProfileSchema } from '@/features/shared/api/schemas/instructorProfile';

describe('instructor detail schema', () => {
  it('parses valid profile with defaults', async () => {
    const { schema } = await loadInstructorProfileSchema();
    const payload = {
      user_id: '01U',
      bio: null,
      services: [
        {
          id: '01S',
          hourly_rate: 50,
          duration_options: [60],
        },
      ],
      areas_of_service: [],
    };
    const parsed = schema.parse(payload);
    expect(parsed.user_id).toBe('01U');
    expect(Array.isArray(parsed.services)).toBe(true);
  });

  it('rejects invalid shape', async () => {
    const { schema } = await loadInstructorProfileSchema();
    const bad: unknown = { user_id: 123, services: [{}] };
    expect(() => schema.parse(bad)).toThrow();
  });
});
