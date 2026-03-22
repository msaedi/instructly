import { render, screen } from '@testing-library/react';
import type { PhoneVerificationFlow } from '@/features/shared/hooks/usePhoneVerificationFlow';
import { PersonalInfoCard } from '../PersonalInfoCard';

function createFlow(overrides: Partial<PhoneVerificationFlow> = {}): PhoneVerificationFlow {
  return {
    phoneNumber: '',
    phoneVerified: false,
    phoneLoading: false,
    phoneInput: '(212) 555-0101',
    phoneCode: '',
    resendCooldown: 0,
    hasPhoneVerificationCodeSent: false,
    showVerifiedPhoneState: false,
    showPendingPhoneState: false,
    showVerifyPhoneAction: true,
    updatePhonePending: false,
    sendVerificationPending: false,
    confirmVerificationPending: false,
    handlePhoneInputChange: jest.fn(),
    setPhoneCode: jest.fn(),
    sendCode: jest.fn(async () => undefined),
    confirmCode: jest.fn(async () => undefined),
    ...overrides,
  };
}

const baseProfile = {
  first_name: 'Alex',
  last_name: 'Rivera',
  postal_code: '10001',
  bio: '',
  service_area_summary: null,
  service_area_boroughs: [],
  years_experience: 1,
};

describe('PersonalInfoCard', () => {
  it('renders the inline phone verification field during onboarding', () => {
    render(
      <PersonalInfoCard
        context="onboarding"
        profile={baseProfile}
        phoneVerificationFlow={createFlow()}
        onProfileChange={jest.fn()}
      />
    );

    expect(screen.getByText(/personal information/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/phone number/i)).toHaveValue('(212) 555-0101');
    expect(screen.getByRole('button', { name: /^verify$/i })).toBeInTheDocument();
  });

  it('does not render phone verification on the dashboard profile form', () => {
    render(
      <PersonalInfoCard
        context="dashboard"
        profile={baseProfile}
        phoneVerificationFlow={createFlow()}
        onProfileChange={jest.fn()}
      />
    );

    expect(screen.queryByLabelText(/phone number/i)).not.toBeInTheDocument();
  });

  it('does not render phone verification when onboarding has no flow available', () => {
    render(
      <PersonalInfoCard
        context="onboarding"
        profile={baseProfile}
        phoneVerificationFlow={null}
        onProfileChange={jest.fn()}
      />
    );

    expect(screen.queryByLabelText(/phone number/i)).not.toBeInTheDocument();
  });
});
