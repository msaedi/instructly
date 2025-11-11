import { isAccountSetupComplete } from '../stepStatus';

describe('isAccountSetupComplete', () => {
  const baseProfile = {
    bio: 'Piano instructor with 8 years experience',
    years_experience: 8,
    has_profile_picture: true,
    user: {
      first_name: 'Test',
      last_name: 'Instructor',
      last_initial: 'I',
    },
  };

  const user = {
    first_name: 'Test',
    last_name: 'Instructor',
    last_initial: 'I',
    zip_code: '10001',
  };

  const serviceAreas = { items: [{}] };

  it('returns false when avatar is missing', () => {
    expect(
      isAccountSetupComplete({
        profile: { ...baseProfile, has_profile_picture: false },
        user,
        serviceAreas,
      })
    ).toBe(false);
  });

  it('returns true when all required fields are present', () => {
    expect(
      isAccountSetupComplete({
        profile: baseProfile,
        user,
        serviceAreas,
      })
    ).toBe(true);
  });

  it('returns false when service areas are missing', () => {
    expect(
      isAccountSetupComplete({
        profile: baseProfile,
        user,
        serviceAreas: { items: [] },
      })
    ).toBe(false);
  });
});
