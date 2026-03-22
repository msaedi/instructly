import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PhoneVerificationField } from '@/components/account/PhoneVerificationField';
import type { PhoneVerificationFlow } from '@/features/shared/hooks/usePhoneVerificationFlow';

type MockFlowOverrides = Partial<PhoneVerificationFlow>;

function createFlow(overrides: MockFlowOverrides = {}): PhoneVerificationFlow {
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

describe('PhoneVerificationField', () => {
  it('renders the default verify state and forwards edits/actions', async () => {
    const user = userEvent.setup();
    const flow = createFlow();

    render(
      <PhoneVerificationField
        flow={flow}
        label="Phone verification"
        inputId="phone-input"
        codeInputId="phone-code"
      />
    );

    expect(screen.getByLabelText(/Phone verification/i)).toHaveValue('(212) 555-0101');
    expect(
      screen.getByText(/we'll send a 6-digit verification code to this number/i)
    ).toBeInTheDocument();

    await user.type(screen.getByLabelText(/Phone verification/i), '9');
    expect(flow.handlePhoneInputChange).toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: /^Verify$/i }));
    expect(flow.sendCode).toHaveBeenCalledTimes(1);
  });

  it('renders the verified badge without action buttons', () => {
    const flow = createFlow({
      showVerifiedPhoneState: true,
      showVerifyPhoneAction: false,
    });

    render(
      <PhoneVerificationField
        flow={flow}
        label="Phone verification"
        inputId="phone-input"
        codeInputId="phone-code"
      />
    );

    expect(screen.getByText(/^Verified$/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Verify$/i })).not.toBeInTheDocument();
  });

  it('shows the sending label while the initial verify request is in flight', () => {
    const flow = createFlow({
      updatePhonePending: true,
    });

    render(
      <PhoneVerificationField
        flow={flow}
        label="Phone verification"
        inputId="phone-input"
        codeInputId="phone-code"
      />
    );

    expect(screen.getByRole('button', { name: /Sending/i })).toBeDisabled();
  });

  it('renders the pending state, normalizes the code input, and supports resend + submit', async () => {
    const user = userEvent.setup();
    const flow = createFlow({
      phoneInput: '(212) 555-0199',
      phoneNumber: '+12125550199',
      phoneCode: '12',
      hasPhoneVerificationCodeSent: true,
      showPendingPhoneState: true,
      showVerifyPhoneAction: false,
    });

    render(
      <PhoneVerificationField
        flow={flow}
        label="Phone verification"
        inputId="phone-input"
        codeInputId="phone-code"
      />
    );

    expect(screen.getByText(/^Pending$/i)).toBeInTheDocument();
    expect(screen.getByText(/Code sent to/)).toHaveTextContent('(XXX) XXX-0199');
    expect(screen.getByLabelText(/Phone verification/i)).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText('123456'), {
      target: { value: '12a34b' },
    });
    expect(flow.setPhoneCode).toHaveBeenLastCalledWith('1234');

    await user.click(screen.getByRole('button', { name: /^Submit$/i }));
    expect(flow.confirmCode).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: /^Resend$/i }));
    expect(flow.sendCode).toHaveBeenCalledTimes(1);
  });

  it('shows the cooldown and pending button labels when requests are in flight', () => {
    const flow = createFlow({
      hasPhoneVerificationCodeSent: true,
      showPendingPhoneState: true,
      showVerifyPhoneAction: false,
      resendCooldown: 12,
      sendVerificationPending: true,
      confirmVerificationPending: true,
    });

    render(
      <PhoneVerificationField
        flow={flow}
        label="Phone verification"
        inputId="phone-input"
        codeInputId="phone-code"
      />
    );

    expect(screen.getByRole('button', { name: /Submitting/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Resend \(12s\)/i })).toBeDisabled();
  });

  it('uses the stored phone number when the pending field value is empty and shows resend sending state', () => {
    const flow = createFlow({
      phoneInput: '',
      phoneNumber: '+12125550188',
      hasPhoneVerificationCodeSent: true,
      showPendingPhoneState: true,
      showVerifyPhoneAction: false,
      resendCooldown: 0,
      sendVerificationPending: true,
    });

    render(
      <PhoneVerificationField
        flow={flow}
        label="Phone verification"
        inputId="phone-input"
        codeInputId="phone-code"
      />
    );

    expect(screen.getByText(/Code sent to/)).toHaveTextContent('(XXX) XXX-0188');
    expect(screen.getByRole('button', { name: /^Sending…$/i })).toBeDisabled();
  });
});
