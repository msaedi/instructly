import type { AnchorHTMLAttributes } from 'react';
import { render, waitFor } from '@testing-library/react';

import SignUpPage from '../page';
import { logger } from '@/lib/logger';

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
  useRouter: () => ({ push: jest.fn() }),
  useSearchParams: () => ({
    get: jest.fn(() => null),
  }),
}));

jest.mock('@/lib/api', () => ({
  API_ENDPOINTS: {
    REGISTER: '/api/v1/auth/register',
  },
  checkIsNYCZip: jest.fn(),
}));

jest.mock('@/app/config/brand', () => ({
  BRAND: { name: 'InstaInstru' },
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('@/lib/http', () => ({
  ApiError: class ApiError extends Error {},
  httpPost: jest.fn(),
}));

jest.mock('@/lib/beta-config', () => ({
  useBetaConfig: () => ({ site: 'prod', phase: 'public' }),
}));

jest.mock('@/features/referrals/referralAuth', () => ({
  buildAuthHref: () => '/login',
}));

jest.mock('@/features/shared/auth/pendingSignup', () => ({
  readPendingSignup: jest.fn(() => null),
  savePendingSignup: jest.fn(),
}));

const mockLoggerDebug = logger.debug as jest.MockedFunction<typeof logger.debug>;

describe('SignUpPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('logs initialization from an effect instead of on every render', async () => {
    const { rerender } = render(<SignUpPage />);

    await waitFor(() => {
      expect(mockLoggerDebug).toHaveBeenCalledWith('SignUpForm initialized', {
        redirectTo: '/',
        hasRedirect: false,
      });
    });

    rerender(<SignUpPage />);

    expect(
      mockLoggerDebug.mock.calls.filter(([message]) => message === 'SignUpForm initialized')
    ).toHaveLength(1);
  });
});
