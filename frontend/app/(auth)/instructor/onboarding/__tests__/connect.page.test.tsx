import { render, waitFor } from '@testing-library/react';
import StripeConnectCallbackPage from '@/app/(auth)/instructor/onboarding/connect/page';
import { toast } from 'sonner';

const mockReplace = jest.fn();
const mockPush = jest.fn();
let currentSearchParams = new URLSearchParams();

const searchParamsProxy = {
  get: (key: string) => currentSearchParams.get(key),
};

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: mockReplace,
    push: mockPush,
  }),
  useSearchParams: () => searchParamsProxy,
}));

const mockFetchWithAuth = jest.fn();

jest.mock('@/lib/api', () => ({
  API_ENDPOINTS: {
    ME: '/auth/me',
    CONNECT_STATUS: '/api/payments/connect/status',
  },
  fetchWithAuth: (...args: unknown[]) => mockFetchWithAuth(...args),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
    time: jest.fn(),
    timeEnd: jest.fn(),
  },
}));

jest.mock('sonner', () => {
  const fn = Object.assign(jest.fn(), {
    success: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
  });
  return { toast: fn };
});

const toastMock = toast as unknown as jest.Mock;

describe('Stripe Connect callback page', () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    currentSearchParams = new URLSearchParams('connect_return=1&from=status');
    mockFetchWithAuth.mockReset();
    toastMock.mockClear();

    mockFetchWithAuth.mockImplementation(async (url: unknown) => {
      if (url === '/auth/me') {
        return {
          ok: true,
        } as unknown as Response;
      }

      if (url === '/api/payments/connect/status') {
        return {
          ok: true,
          json: async () => ({
            has_account: true,
            onboarding_completed: true,
            charges_enabled: true,
            payouts_enabled: true,
            details_submitted: true,
            requirements: [],
          }),
        } as unknown as Response;
      }

      throw new Error(`Unhandled fetch: ${String(url)}`);
    });
  });

  it('warms up auth, fetches status, and redirects back to onboarding', async () => {
    render(<StripeConnectCallbackPage />);

    await waitFor(() => expect(mockFetchWithAuth).toHaveBeenCalledWith('/auth/me'));
    await waitFor(() => expect(mockFetchWithAuth).toHaveBeenCalledWith('/api/payments/connect/status'));
    await waitFor(() =>
      expect(toastMock).toHaveBeenCalledWith('Stripe Connect linked', {
        description: "You're all set.",
      }),
    );
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/instructor/onboarding/status'));
  });
});
