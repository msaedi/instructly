import { buildProgressSnapshot } from '../progressLogging';
import type { OnboardingStatusMap } from '../stepStatus';
import type { OnboardingStatusResponse } from '@/services/api/payments';
import type { InstructorProfile } from '@/types/instructor';

describe('buildProgressSnapshot', () => {
  it('includes pending keys for incomplete steps', () => {
    const statusMap: OnboardingStatusMap = {
      'account-setup': { visited: true, completed: false },
      'skill-selection': { visited: true, completed: false },
      'verify-identity': { visited: false, completed: false },
      'payment-setup': { visited: false, completed: false },
    };

    const profile: Partial<InstructorProfile> = {
      bio: '',
      years_experience: undefined,
      services: [],
      background_check_completed: false,
    };

    const stripe = {
      onboarding_completed: false,
      charges_enabled: false,
      payouts_enabled: false,
    } as OnboardingStatusResponse;

    const snapshot = buildProgressSnapshot({
      instructorId: '123',
      route: '/instructor/onboarding/account-setup',
      activeStep: 'account-setup',
      progressReady: true,
      statusMap,
      data: {
        profile,
        user: { first_name: '', last_name: '' },
        serviceAreas: { items: [] },
        addresses: { items: [] },
        stripe,
      },
    });

    expect(snapshot.status['account-setup'].pending).toEqual(
      expect.arrayContaining([
        'first_name',
        'last_name',
        'zip',
        'bio',
        'years_experience',
        'avatar',
        'service_area',
      ])
    );
    expect(snapshot.status['skill-selection'].pending).toEqual(['skill']);
    expect(snapshot.status['verify-identity'].pending).toEqual(
      expect.arrayContaining(['id_verification', 'background_check'])
    );
    expect(snapshot.status['payment-setup'].pending).toEqual(['stripe_connect']);
  });
});
