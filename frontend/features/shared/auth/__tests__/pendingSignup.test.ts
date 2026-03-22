import {
  buildRegistrationPayload,
  clearPendingSignup,
  formatSignupPhoneForApi,
  type PendingSignupData,
  readPendingSignup,
  savePendingSignup,
  PENDING_SIGNUP_STORAGE_KEY,
  updatePendingSignupVerificationToken,
} from '@/features/shared/auth/pendingSignup';
import { RoleName } from '@/types/enums';

describe('pendingSignup', () => {
  const baseSignup: PendingSignupData = {
    firstName: 'Alex',
    lastName: 'Morgan',
    email: 'alex@example.com',
    phone: '(212) 555-0101',
    zipCode: '10001',
    password: 'Secret123!',
    confirmPassword: 'Secret123!',
    role: RoleName.INSTRUCTOR,
    redirect: '/instructor/onboarding/welcome',
    referralCode: 'REF123',
    founding: true,
    inviteCode: 'INVITE123',
    emailVerificationToken: null,
  };

  beforeEach(() => {
    sessionStorage.clear();
  });

  it('persists and restores pending signup data', () => {
    savePendingSignup(baseSignup);

    expect(readPendingSignup()).toEqual(baseSignup);
  });

  it('updates the verification token without losing the rest of the payload', () => {
    savePendingSignup({
      firstName: 'Taylor',
      lastName: 'Stone',
      email: 'taylor@example.com',
      phone: '(212) 555-0110',
      zipCode: '10002',
      password: 'Secret123!',
      confirmPassword: 'Secret123!',
      role: RoleName.STUDENT,
      redirect: '/',
      referralCode: null,
      founding: false,
      inviteCode: null,
      emailVerificationToken: null,
    });

    const updated = updatePendingSignupVerificationToken('verified-token');

    expect(updated?.emailVerificationToken).toBe('verified-token');
    expect(readPendingSignup()?.emailVerificationToken).toBe('verified-token');
    expect(readPendingSignup()?.email).toBe('taylor@example.com');
  });

  it('returns null when no pending signup exists to update', () => {
    expect(updatePendingSignupVerificationToken('verified-token')).toBeNull();
  });

  it('builds the register payload from the stored signup data', () => {
    const payload = buildRegistrationPayload(
      {
        firstName: 'Jamie',
        lastName: 'Lee',
        email: 'Jamie@Example.com',
        phone: '(212) 555-0999',
        zipCode: '10003',
        password: 'Secret123!',
        confirmPassword: 'Secret123!',
        role: RoleName.INSTRUCTOR,
        redirect: '/instructor/onboarding/welcome',
        referralCode: null,
        founding: false,
        inviteCode: 'INVITE555',
        emailVerificationToken: 'token-123',
      },
      'guest-123',
      'America/New_York'
    );

    expect(payload).toMatchObject({
      first_name: 'Jamie',
      last_name: 'Lee',
      email: 'jamie@example.com',
      phone: '+12125550999',
      zip_code: '10003',
      role: RoleName.INSTRUCTOR,
      guest_session_id: 'guest-123',
      email_verification_token: 'token-123',
      timezone: 'America/New_York',
      metadata: {
        invite_code: 'INVITE555',
      },
    });
  });

  it('formats phone numbers for the register payload', () => {
    expect(formatSignupPhoneForApi('(212) 555-0101')).toBe('+12125550101');
    expect(formatSignupPhoneForApi('1 (646) 555-1212')).toBe('+16465551212');
    expect(formatSignupPhoneForApi('  +442071838750  ')).toBe('+442071838750');
  });

  it('returns null and clears malformed JSON payloads', () => {
    sessionStorage.setItem(PENDING_SIGNUP_STORAGE_KEY, '{not-json');

    expect(readPendingSignup()).toBeNull();
    expect(sessionStorage.getItem(PENDING_SIGNUP_STORAGE_KEY)).toBeNull();
  });

  it('returns null and clears invalid payload shapes', () => {
    sessionStorage.setItem(
      PENDING_SIGNUP_STORAGE_KEY,
      JSON.stringify({ version: 1, email: 'missing-fields@example.com' })
    );

    expect(readPendingSignup()).toBeNull();
    expect(sessionStorage.getItem(PENDING_SIGNUP_STORAGE_KEY)).toBeNull();
  });

  it('returns null and clears non-object payloads', () => {
    sessionStorage.setItem(PENDING_SIGNUP_STORAGE_KEY, JSON.stringify('invalid'));

    expect(readPendingSignup()).toBeNull();
    expect(sessionStorage.getItem(PENDING_SIGNUP_STORAGE_KEY)).toBeNull();
  });

  it('gracefully handles sessionStorage access failures', () => {
    const sessionStorageGetter = jest
      .spyOn(window, 'sessionStorage', 'get')
      .mockImplementation(() => {
        throw new Error('blocked');
      });

    try {
      expect(readPendingSignup()).toBeNull();
      expect(() => savePendingSignup(baseSignup)).not.toThrow();
      expect(() => clearPendingSignup()).not.toThrow();
    } finally {
      sessionStorageGetter.mockRestore();
    }
  });

  it('clears the pending signup payload', () => {
    savePendingSignup(baseSignup);

    clearPendingSignup();

    expect(readPendingSignup()).toBeNull();
  });
});
