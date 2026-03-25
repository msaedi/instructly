import { fireEvent, render, screen } from '@testing-library/react';
import { BioCard } from '@/app/(auth)/instructor/onboarding/account-setup/components/BioCard';
import type { ProfileFormState } from '@/features/instructor-profile/types';

jest.mock('@/components/user/ProfilePictureUpload', () => ({
  ProfilePictureUpload: ({ ariaLabel }: { ariaLabel?: string }) => (
    <button type="button" aria-label={ariaLabel ?? 'Upload profile photo'}>
      Upload
    </button>
  ),
}));

function createProfile(overrides?: Partial<ProfileFormState>): ProfileFormState {
  return {
    first_name: 'Taylor',
    last_name: 'Swift',
    postal_code: '10001',
    bio: 'A'.repeat(420),
    service_area_boroughs: ['Manhattan'],
    years_experience: 3,
    ...overrides,
  };
}

describe('BioCard', () => {
  it('allows the years field to be cleared by default on dashboard', () => {
    const onProfileChange = jest.fn();
    const setBioTouched = jest.fn();
    const { rerender } = render(
      <BioCard
        context="dashboard"
        profile={createProfile()}
        onProfileChange={onProfileChange}
        bioTouched={false}
        bioTooShort={false}
        setBioTouched={setBioTouched}
        onGenerateBio={jest.fn()}
      />
    );

    const yearsInput = screen.getByLabelText(/years of experience/i);
    fireEvent.change(yearsInput, { target: { value: '' } });

    expect(onProfileChange).toHaveBeenLastCalledWith({ years_experience: 0 });

    rerender(
      <BioCard
        context="dashboard"
        profile={createProfile({ years_experience: 0 })}
        onProfileChange={onProfileChange}
        bioTouched={false}
        bioTooShort={false}
        setBioTouched={setBioTouched}
        onGenerateBio={jest.fn()}
      />
    );

    expect(screen.getByLabelText(/years of experience/i)).toHaveDisplayValue('');
  });

  it('lets the next typed value replace the cleared years value', () => {
    const onProfileChange = jest.fn();
    const setBioTouched = jest.fn();
    const { rerender } = render(
      <BioCard
        context="dashboard"
        profile={createProfile()}
        onProfileChange={onProfileChange}
        bioTouched={false}
        bioTooShort={false}
        setBioTouched={setBioTouched}
        onGenerateBio={jest.fn()}
      />
    );

    fireEvent.change(screen.getByLabelText(/years of experience/i), { target: { value: '' } });

    rerender(
      <BioCard
        context="dashboard"
        profile={createProfile({ years_experience: 0 })}
        onProfileChange={onProfileChange}
        bioTouched={false}
        bioTooShort={false}
        setBioTouched={setBioTouched}
        onGenerateBio={jest.fn()}
      />
    );

    fireEvent.change(screen.getByLabelText(/years of experience/i), { target: { value: '2' } });

    expect(onProfileChange).toHaveBeenLastCalledWith({ years_experience: 2 });
  });
});
