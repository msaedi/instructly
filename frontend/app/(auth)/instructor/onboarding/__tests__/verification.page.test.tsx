import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Step4Verification from '@/app/(auth)/instructor/onboarding/verification/page';
import { toast } from 'sonner';

const mockPush = jest.fn();
const mockReplace = jest.fn();
let currentSearchParams = new URLSearchParams();
const searchParamsProxy = {
  get: (key: string) => currentSearchParams.get(key),
  toString: () => currentSearchParams.toString(),
};
const routerProxy = {
  push: mockPush,
  replace: mockReplace,
};

jest.mock('next/navigation', () => ({
  useRouter: () => routerProxy,
  useSearchParams: () => searchParamsProxy,
  usePathname: () => '/instructor/onboarding/verification',
}));

jest.mock('@stripe/stripe-js', () => ({
  loadStripe: jest.fn(async () => ({ verifyIdentity: jest.fn(() => ({})) })),
}));

const mockFetchWithAuth = jest.fn();

jest.mock('@/lib/api', () => ({
  API_ENDPOINTS: {
    INSTRUCTOR_PROFILE: '/api/v1/instructors/me',
    STRIPE_IDENTITY_REFRESH: '/api/v1/payments/identity/refresh',
  },
  fetchWithAuth: (...args: unknown[]) => mockFetchWithAuth(...args),
  createStripeIdentitySession: jest.fn().mockResolvedValue({ verification_session_id: 'vs_123', client_secret: 'cs_123' }),
}));

jest.mock('sonner', () => {
  const fn = Object.assign(jest.fn(), {
    success: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
  });
  return { toast: fn };
});

jest.mock('@/components/instructor/BGCStep', () => ({
  __esModule: true,
  BGCStep: () => <div data-testid="bgc-step">BGC Step</div>,
}));

// Stable mock function for refresh to avoid dependency array issues
const mockRefreshStepStatus = jest.fn();

jest.mock('@/features/instructor-onboarding/useOnboardingStepStatus', () => ({
  useOnboardingStepStatus: () => ({
    loading: false,
    stepStatus: {
      'account-setup': 'done',
      'skill-selection': 'done',
      'verify-identity': 'pending',
      'payment-setup': 'pending',
    },
    rawData: {
      profile: { id: 'profile-1', identity_verified_at: null, identity_verification_session_id: null },
      user: { first_name: 'Test', last_name: 'User' },
      serviceAreas: [],
      connectStatus: null,
      bgcStatus: null,
    },
    refresh: mockRefreshStepStatus,
  }),
}));

jest.mock('@/features/shared/hooks/useAuth', () => {
  return {
    AuthProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
    useAuth: () => ({
      user: { id: 'user-1', roles: ['instructor'], permissions: [] },
      isAuthenticated: true,
      isLoading: false,
      error: null,
      login: jest.fn(),
      logout: jest.fn(),
      checkAuth: jest.fn(),
      redirectToLogin: jest.fn(),
    }),
  };
});

const renderWithClient = (ui: ReactNode) => {
  const queryClient = new QueryClient();
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
};

describe('Verification page', () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockReplace.mockClear();
    currentSearchParams = new URLSearchParams();
    mockFetchWithAuth.mockReset();
    (toast.success as jest.Mock).mockClear();
    (toast.error as jest.Mock).mockClear();
    (toast.info as jest.Mock).mockClear();
    mockFetchWithAuth.mockImplementation(async (url: unknown) => {
      if (url === '/api/v1/instructors/me') {
        return {
          ok: true,
          json: async () => ({ id: 'inst-1', identity_verified_at: null }),
        } as unknown as Response;
      }
      if (url === '/api/v1/payments/identity/refresh') {
        return {
          ok: true,
          json: async () => ({ verified: true }),
        } as unknown as Response;
      }
      return {
        ok: true,
        json: async () => ({}),
      } as unknown as Response;
    });
  });

  it('renders background check step and no upload UI', async () => {
    renderWithClient(<Step4Verification />);

    await waitFor(() => expect(screen.getByTestId('bgc-step')).toBeInTheDocument());
    expect(screen.queryByText(/choose file/i)).not.toBeInTheDocument();
  });

  it('navigates back to status when coming from status', async () => {
    currentSearchParams = new URLSearchParams('from=status');
    renderWithClient(<Step4Verification />);

    // Wait for the Continue button to appear (component fully rendered)
    await waitFor(() => expect(screen.getByRole('button', { name: /continue/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));
    expect(mockPush).toHaveBeenCalledWith('/instructor/onboarding/status');
  });

  it('navigates to payment setup by default', async () => {
    renderWithClient(<Step4Verification />);

    // Wait for the Continue button to appear (component fully rendered)
    await waitFor(() => expect(screen.getByRole('button', { name: /continue/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));
    expect(mockPush).toHaveBeenCalledWith('/instructor/onboarding/payment-setup');
  });

  it('refreshes identity and shows toast when returning from Stripe', async () => {
    currentSearchParams = new URLSearchParams('identity_return=true');
    renderWithClient(<Step4Verification />);

    await waitFor(() => expect(mockFetchWithAuth).toHaveBeenCalledWith('/api/v1/payments/identity/refresh', { method: 'POST' }));
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/instructor/onboarding/verification'));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Identity check complete', {
      description: 'Next, start your background check.',
    }));
  });
});
