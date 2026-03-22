import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import VerifyEmailPage from '@/app/(shared)/verify-email/page';
import { savePendingSignup } from '@/features/shared/auth/pendingSignup';
import { RoleName } from '@/types/enums';

const mockPush = jest.fn();
const mockCheckAuth = jest.fn(async () => undefined);
const mockHttpPost = jest.fn();
const mockHttp = jest.fn();
const mockGetGuestSessionId = jest.fn(() => null);
const mockClaimReferralCode = jest.fn(async (_code: string) => undefined);

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('@/lib/api', () => ({
  API_ENDPOINTS: {
    SEND_EMAIL_VERIFICATION: '/api/v1/auth/send-email-verification',
    VERIFY_EMAIL_CODE: '/api/v1/auth/verify-email-code',
    REGISTER: '/api/v1/auth/register',
    LOGIN: '/api/v1/auth/login',
  },
}));

jest.mock('@/lib/http', () => ({
  ApiError: class ApiError extends Error {
    status: number;
    data?: unknown;

    constructor(message: string, status: number, data?: unknown) {
      super(message);
      this.status = status;
      this.data = data;
    }
  },
  httpPost: (...args: unknown[]) => mockHttpPost(...args),
  http: (...args: unknown[]) => mockHttp(...args),
}));

jest.mock('@/lib/searchTracking', () => ({
  getGuestSessionId: () => mockGetGuestSessionId(),
}));

jest.mock('@/features/referrals/referralAuth', () => ({
  buildAuthHref: (path: string, params?: Record<string, string | boolean | null | undefined>) => {
    const entries = Object.entries(params ?? {}).filter(([, value]) => value !== null && value !== undefined && value !== '');
    if (entries.length === 0) {
      return path;
    }
    const search = new URLSearchParams();
    for (const [key, value] of entries) {
      search.set(key, String(value));
    }
    return `${path}?${search.toString()}`;
  },
  claimReferralCode: (code: string) => mockClaimReferralCode(code),
}));

jest.mock('@/app/config/brand', () => ({
  BRAND: {
    name: 'iNSTAiNSTRU',
  },
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => ({
    checkAuth: mockCheckAuth,
  }),
}));

describe('VerifyEmailPage', () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockCheckAuth.mockClear();
    mockHttpPost.mockReset();
    mockHttp.mockReset();
    mockGetGuestSessionId.mockReset();
    mockGetGuestSessionId.mockReturnValue(null);
    mockClaimReferralCode.mockReset();
    sessionStorage.clear();
  });

  function seedPendingSignup() {
    savePendingSignup({
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
    });
  }

  it('renders the masked email, shows the resend cooldown, and returns to signup on wrong email', async () => {
    const user = userEvent.setup();
    seedPendingSignup();

    render(<VerifyEmailPage />);

    expect(await screen.findByText(/al\*\*@example\.com/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Resend in 30s/i })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: /Wrong email\? Go back/i }));

    const pushedHref = mockPush.mock.calls[0]?.[0];
    expect(typeof pushedHref).toBe('string');
    expect(pushedHref).toBeTruthy();

    const parsedUrl = new URL(String(pushedHref), 'https://instainstru.test');
    expect(parsedUrl.pathname).toBe('/signup');
    expect(parsedUrl.searchParams.get('role')).toBe('instructor');
    expect(parsedUrl.searchParams.get('redirect')).toBe('/instructor/onboarding/welcome');
    expect(parsedUrl.searchParams.get('ref')).toBe('REF123');
    expect(parsedUrl.searchParams.get('founding')).toBe('true');
    expect(parsedUrl.searchParams.get('invite_code')).toBe('INVITE123');
    expect(parsedUrl.searchParams.get('email')).toBe('alex@example.com');
  });

  it('verifies the code, registers the account, and continues the signup flow', async () => {
    const user = userEvent.setup();
    seedPendingSignup();
    mockHttpPost
      .mockResolvedValueOnce({
        verification_token: 'verified-token',
        expires_in_seconds: 900,
      })
      .mockResolvedValueOnce({ message: 'ok' });
    mockHttp.mockResolvedValue({});

    render(<VerifyEmailPage />);

    await user.type(await screen.findByLabelText(/Verification code/i), '123456');
    await user.click(screen.getByRole('button', { name: /Verify and continue/i }));

    await waitFor(() => {
      expect(mockHttpPost).toHaveBeenNthCalledWith(1, '/api/v1/auth/verify-email-code', {
        email: 'alex@example.com',
        code: '123456',
      });
    });

    expect(mockHttpPost).toHaveBeenNthCalledWith(
      2,
      '/api/v1/auth/register',
      expect.objectContaining({
        email: 'alex@example.com',
        role: RoleName.INSTRUCTOR,
        email_verification_token: 'verified-token',
        metadata: {
          invite_code: 'INVITE123',
        },
      })
    );
    expect(mockHttp).toHaveBeenCalledWith('POST', '/api/v1/auth/login', {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: 'username=alex%40example.com&password=Secret123%21',
    });
    expect(mockClaimReferralCode).toHaveBeenCalledWith('REF123');
    expect(mockCheckAuth).toHaveBeenCalled();
    expect(mockPush).toHaveBeenCalledWith('/instructor/onboarding/welcome');
  });
});
