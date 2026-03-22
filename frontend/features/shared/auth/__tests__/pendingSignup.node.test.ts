/** @jest-environment node */

import {
  clearPendingSignup,
  readPendingSignup,
  savePendingSignup,
} from '@/features/shared/auth/pendingSignup';
import { RoleName } from '@/types/enums';

describe('pendingSignup without window', () => {
  it('returns null and no-ops when sessionStorage is unavailable', () => {
    expect(readPendingSignup()).toBeNull();

    expect(() =>
      savePendingSignup({
        firstName: 'Alex',
        lastName: 'Morgan',
        email: 'alex@example.com',
        phone: '(212) 555-0101',
        zipCode: '10001',
        password: 'Secret123!',
        confirmPassword: 'Secret123!',
        role: RoleName.STUDENT,
        redirect: '/',
        referralCode: null,
        founding: false,
        inviteCode: null,
        emailVerificationToken: null,
      })
    ).not.toThrow();

    expect(() => clearPendingSignup()).not.toThrow();
  });
});
