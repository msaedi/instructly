import { buildProfileUpdateBody } from '@/lib/profileSchemaDebug';

describe('buildProfileUpdateBody', () => {
  it('removes legacy areas_of_service from payload', () => {
    const existing = {
      bio: 'Existing',
      areas_of_service: ['Manhattan'],
      years_experience: 3,
    } as Record<string, unknown>;

    const form = {
      bio: 'Updated bio',
      years_experience: 5,
    };

    const payload = buildProfileUpdateBody(existing, form);

    expect('areas_of_service' in payload).toBe(false);
    expect(payload.bio).toBe('Updated bio');
    expect(payload.years_experience).toBe(5);
  });
});
