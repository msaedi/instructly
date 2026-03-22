import type { components } from '@/features/shared/api/types';
import { RoleName } from '@/types/enums';

export const PENDING_SIGNUP_STORAGE_KEY = 'pending_signup';

export type PendingSignupRole = RoleName.INSTRUCTOR | RoleName.STUDENT;

export type PendingSignupData = {
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  zipCode: string;
  password: string;
  confirmPassword: string;
  role: PendingSignupRole;
  redirect: string;
  referralCode: string | null;
  founding: boolean;
  inviteCode: string | null;
  emailVerificationToken: string | null;
};

type PersistedPendingSignup = PendingSignupData & {
  version: 1;
};

function getSessionStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function isPendingSignupRole(value: unknown): value is PendingSignupRole {
  return value === RoleName.INSTRUCTOR || value === RoleName.STUDENT;
}

function isStringOrNull(value: unknown): value is string | null {
  return typeof value === 'string' || value === null;
}

function isPersistedPendingSignup(value: unknown): value is PersistedPendingSignup {
  if (!value || typeof value !== 'object') {
    return false;
  }

  const record = value as Record<string, unknown>;
  return (
    record['version'] === 1 &&
    typeof record['firstName'] === 'string' &&
    typeof record['lastName'] === 'string' &&
    typeof record['email'] === 'string' &&
    typeof record['phone'] === 'string' &&
    typeof record['zipCode'] === 'string' &&
    typeof record['password'] === 'string' &&
    typeof record['confirmPassword'] === 'string' &&
    isPendingSignupRole(record['role']) &&
    typeof record['redirect'] === 'string' &&
    isStringOrNull(record['referralCode']) &&
    typeof record['founding'] === 'boolean' &&
    isStringOrNull(record['inviteCode']) &&
    isStringOrNull(record['emailVerificationToken'])
  );
}

export function formatSignupPhoneForApi(phone: string): string {
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length === 10) {
    return `+1${cleaned}`;
  }
  if (cleaned.length === 11 && cleaned[0] === '1') {
    return `+${cleaned}`;
  }
  return phone.trim();
}

export function readPendingSignup(): PendingSignupData | null {
  const storage = getSessionStorage();
  if (!storage) {
    return null;
  }

  try {
    const raw = storage.getItem(PENDING_SIGNUP_STORAGE_KEY);
    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw) as unknown;
    if (!isPersistedPendingSignup(parsed)) {
      storage.removeItem(PENDING_SIGNUP_STORAGE_KEY);
      return null;
    }

    const { version: _version, ...pendingSignup } = parsed;
    return pendingSignup;
  } catch {
    storage.removeItem(PENDING_SIGNUP_STORAGE_KEY);
    return null;
  }
}

export function savePendingSignup(data: PendingSignupData): void {
  const storage = getSessionStorage();
  if (!storage) {
    return;
  }

  const payload: PersistedPendingSignup = {
    version: 1,
    ...data,
  };

  try {
    storage.setItem(PENDING_SIGNUP_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // Ignore sessionStorage failures and let the flow continue.
  }
}

export function updatePendingSignupVerificationToken(
  token: string | null
): PendingSignupData | null {
  const current = readPendingSignup();
  if (!current) {
    return null;
  }

  const nextValue: PendingSignupData = {
    ...current,
    emailVerificationToken: token,
  };
  savePendingSignup(nextValue);
  return nextValue;
}

export function clearPendingSignup(): void {
  const storage = getSessionStorage();
  if (!storage) {
    return;
  }

  try {
    storage.removeItem(PENDING_SIGNUP_STORAGE_KEY);
  } catch {
    // Ignore sessionStorage failures and let the flow continue.
  }
}

export function buildRegistrationPayload(
  pendingSignup: PendingSignupData,
  guestSessionId: string | null,
  timezone: string | null
): components['schemas']['UserCreate'] {
  return {
    first_name: pendingSignup.firstName.trim(),
    last_name: pendingSignup.lastName.trim(),
    email: pendingSignup.email.trim().toLowerCase(),
    phone: formatSignupPhoneForApi(pendingSignup.phone),
    zip_code: pendingSignup.zipCode.trim(),
    password: pendingSignup.password,
    role: pendingSignup.role,
    is_active: true,
    timezone,
    email_verification_token: pendingSignup.emailVerificationToken,
    ...(guestSessionId ? { guest_session_id: guestSessionId } : {}),
    metadata: {
      invite_code: pendingSignup.inviteCode,
    },
  };
}
