import { render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import OnboardingStatusPage from '@/app/(auth)/instructor/onboarding/status/page';

/* ---------- router mock ---------- */
const mockPush = jest.fn();
const mockReplace = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  useSearchParams: () => ({ get: () => null, toString: () => '' }),
  usePathname: () => '/instructor/onboarding/status',
}));

/* ---------- Stripe mock ---------- */
jest.mock('@stripe/stripe-js', () => ({
  loadStripe: jest.fn(async () => ({ verifyIdentity: jest.fn(() => ({})) })),
}));

/* ---------- API mock ---------- */
jest.mock('@/lib/api', () => ({
  API_ENDPOINTS: {
    INSTRUCTOR_PROFILE: '/api/v1/instructors/me',
    STRIPE_IDENTITY_REFRESH: '/api/v1/payments/identity/refresh',
  },
  fetchWithAuth: jest.fn().mockResolvedValue({ ok: true, json: async () => ({}) }),
  getConnectStatus: jest.fn().mockResolvedValue({ onboarding_completed: false }),
  createStripeIdentitySession: jest.fn().mockResolvedValue({
    verification_session_id: 'vs_123',
    client_secret: 'cs_123',
  }),
}));

/* ---------- Payment service mock ---------- */
jest.mock('@/services/api/payments', () => ({
  paymentService: {
    startOnboardingWithReturn: jest.fn().mockResolvedValue({ onboarding_url: null, already_onboarded: false }),
  },
}));

/* ---------- Go live mock ---------- */
jest.mock('@/src/api/services/instructors', () => ({
  useGoLiveInstructor: () => ({
    mutateAsync: jest.fn(),
    isPending: false,
  }),
}));

/* ---------- toast mock ---------- */
jest.mock('sonner', () => {
  const fn = Object.assign(jest.fn(), {
    success: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
  });
  return { toast: fn };
});

/* ---------- BGCStep mock — captures ensureConsent prop ---------- */
let capturedEnsureConsent: (() => Promise<boolean>) | undefined;
jest.mock('@/components/instructor/BGCStep', () => ({
  __esModule: true,
  BGCStep: (props: { instructorId: string; ensureConsent?: () => Promise<boolean> }) => {
    capturedEnsureConsent = props.ensureConsent;
    return <div data-testid="bgc-step">BGC Step</div>;
  },
}));

/* ---------- Consent modal mock ---------- */
jest.mock('@/components/consent/BackgroundCheckDisclosureModal', () => ({
  __esModule: true,
  BackgroundCheckDisclosureModal: (props: {
    isOpen: boolean;
    onAccept: () => void;
    onDecline: () => void;
    submitting?: boolean;
  }) => {
    return props.isOpen ? (
      <div data-testid="consent-modal">
        <button onClick={props.onAccept} data-testid="accept-consent">
          I acknowledge and authorize
        </button>
        <button onClick={props.onDecline} data-testid="decline-consent">
          Decline
        </button>
      </div>
    ) : null;
  },
}));

/* ---------- BGC consent API mock ---------- */
jest.mock('@/lib/api/bgc', () => ({
  bgcConsent: jest.fn().mockResolvedValue({ ok: true }),
}));

/* ---------- Constants mock ---------- */
jest.mock('@/config/constants', () => ({
  DISCLOSURE_VERSION: 'v1.0.0',
}));

/* ---------- Auth mock ---------- */
jest.mock('@/features/shared/hooks/useAuth', () => ({
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
}));

/* ---------- Step status mock — use stable refs to avoid infinite re-render ---------- */
const stableProfile = {
  id: 'profile-1',
  identity_verified_at: null,
  identity_verification_session_id: null,
  skills_configured: false,
  services: [],
  is_live: false,
};
const stableConnectStatus = { onboarding_completed: false };
const stableRawData = {
  profile: stableProfile,
  user: { first_name: 'Test', last_name: 'User' },
  serviceAreas: ['area-1'],
  connectStatus: stableConnectStatus,
  bgcStatus: null,
};

jest.mock('@/features/instructor-onboarding/useOnboardingStepStatus', () => ({
  useOnboardingStepStatus: () => ({
    loading: false,
    stepStatus: {
      'account-setup': 'done',
      'skill-selection': 'done',
      'verify-identity': 'pending',
      'payment-setup': 'pending',
    },
    rawData: stableRawData,
    refresh: jest.fn(),
  }),
  canInstructorGoLive: () => ({
    canGoLive: false,
    missing: ['bgc', 'stripe'],
  }),
}));

const renderWithClient = (ui: ReactNode) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
};

describe('Onboarding status page – BGC consent regression', () => {
  beforeEach(() => {
    capturedEnsureConsent = undefined;
  });

  it('renders the BGC step component', async () => {
    renderWithClient(<OnboardingStatusPage />);

    await waitFor(() => {
      expect(screen.getByTestId('bgc-step')).toBeInTheDocument();
    });
  });

  it('passes ensureConsent callback to BGCStep', async () => {
    renderWithClient(<OnboardingStatusPage />);

    await waitFor(() => {
      expect(screen.getByTestId('bgc-step')).toBeInTheDocument();
    });

    // This is the key regression test:
    // Without the fix, ensureConsent would be undefined,
    // causing BGCStep to fail silently when FCRA consent is required.
    expect(capturedEnsureConsent).toBeDefined();
    expect(typeof capturedEnsureConsent).toBe('function');
  });

  it('renders the BackgroundCheckDisclosureModal (hidden by default)', async () => {
    renderWithClient(<OnboardingStatusPage />);

    await waitFor(() => {
      expect(screen.getByTestId('bgc-step')).toBeInTheDocument();
    });

    // Modal should NOT be visible until ensureConsent triggers it
    expect(screen.queryByTestId('consent-modal')).not.toBeInTheDocument();
  });
});
