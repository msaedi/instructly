import type { AnchorHTMLAttributes } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { LoginClient } from '../LoginClient';
import { http } from '@/lib/http';
import { logger } from '@/lib/logger';

const mockPush = jest.fn();

jest.mock('next/link', () => {
  const MockLink = ({
    children,
    href,
    ...props
  }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  );
  MockLink.displayName = 'MockLink';
  return {
    __esModule: true,
    default: MockLink,
  };
});

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('@marsidev/react-turnstile', () => ({
  Turnstile: () => <div data-testid="turnstile" />,
}));

jest.mock('@/app/config/brand', () => ({
  BRAND: { name: 'InstaInstru' },
}));

jest.mock('@/lib/api', () => ({
  API_ENDPOINTS: {
    LOGIN: '/api/v1/auth/login',
    ME: '/api/v1/auth/me',
    INSTRUCTOR_PROFILE: '/api/v1/instructor/profile',
  },
}));

jest.mock('@/lib/http', () => ({
  ApiError: class ApiError extends Error {},
  http: jest.fn(),
  httpGet: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    debug: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => ({ checkAuth: jest.fn() }),
}));

jest.mock('@/features/referrals/referralAuth', () => ({
  buildAuthHref: () => '/signup',
}));

jest.mock('@/lib/searchTracking', () => ({
  getGuestSessionId: jest.fn(() => null),
  transferGuestSearchesToAccount: jest.fn(),
}));

jest.mock('@/lib/publicEnv', () => ({
  TURNSTILE_SITE_KEY: 'test-turnstile-key',
}));

const mockHttp = http as jest.MockedFunction<typeof http>;
const mockLoggerInfo = logger.info as jest.MockedFunction<typeof logger.info>;

describe('LoginClient', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockHttp.mockResolvedValue({});
  });

  it('logs page load once per mount instead of every render', async () => {
    const { rerender } = render(<LoginClient redirect="/" referralCode={null} />);

    await waitFor(() => {
      expect(mockLoggerInfo).toHaveBeenCalledWith('Login page loaded');
    });

    rerender(<LoginClient redirect="/" referralCode={null} />);

    expect(
      mockLoggerInfo.mock.calls.filter(([message]) => message === 'Login page loaded')
    ).toHaveLength(1);
  });

  it('uses a text input for 2FA and logs only the email domain during login', async () => {
    mockHttp.mockResolvedValue({
      requires_2fa: true,
      temp_token: 'temp-token',
    });

    render(<LoginClient redirect="/" referralCode={null} />);

    fireEvent.change(screen.getByLabelText('Email'), {
      target: { name: 'email', value: 'USER@EXAMPLE.COM' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { name: 'password', value: 'StrongPass123!' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    const twoFactorInput = await screen.findByLabelText('6-digit code');
    expect(twoFactorInput).toHaveAttribute('type', 'text');

    const loginAttemptCall = mockLoggerInfo.mock.calls.find(
      ([message]) => message === 'Login attempt started'
    );
    expect(loginAttemptCall?.[1]).toMatchObject({
      emailDomain: 'example.com',
      hasEmail: true,
    });
    expect(loginAttemptCall?.[1]).not.toHaveProperty('email');

    const requestLogCall = mockLoggerInfo.mock.calls.find(
      ([message]) => message === 'Sending login request:'
    );
    expect(requestLogCall?.[1]).toMatchObject({
      emailDomain: 'example.com',
      includesGuestSessionId: false,
      payloadType: 'form-data',
    });
    expect(requestLogCall?.[1]).not.toHaveProperty('bodyPreview');
  });
});
