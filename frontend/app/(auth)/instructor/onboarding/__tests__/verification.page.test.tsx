import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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

type MockProfile = {
  id: string;
  identity_verified_at: string | null;
  identity_verification_session_id: string | null;
  identity_name_mismatch?: boolean;
  bgc_name_mismatch?: boolean;
};

type MockRefreshResponse = {
  body?: {
    status?: string;
    verified?: boolean;
    identity_name_mismatch?: boolean;
    last_error_code?: string | null;
    last_error_reason?: string | null;
  };
  ok?: boolean;
  reject?: boolean;
};

const makeProfile = (overrides: Partial<MockProfile> = {}): MockProfile => ({
  id: 'profile-1',
  identity_verified_at: null,
  identity_verification_session_id: null,
  identity_name_mismatch: false,
  ...overrides,
});

const makeRawData = (profileOverrides: Partial<MockProfile> = {}) => ({
  profile: makeProfile(profileOverrides),
  user: { first_name: 'Test', last_name: 'User' },
  serviceAreas: [],
  connectStatus: null,
  bgcStatus: null,
});

let mockRawData = makeRawData();
let refreshResponses: MockRefreshResponse[] = [];
const mockFetchWithAuth = jest.fn();
const mockCreateStripeIdentitySession = jest.fn();
const mockVerifyIdentity = jest.fn();
const mockLoadStripe = jest.fn(async (_publishableKey: string) => ({
  verifyIdentity: mockVerifyIdentity,
}));
let capturedBgcIdentityVerified: boolean | undefined;

jest.mock('next/navigation', () => ({
  useRouter: () => routerProxy,
  useSearchParams: () => searchParamsProxy,
  usePathname: () => '/instructor/onboarding/verification',
}));

jest.mock('@stripe/stripe-js', () => ({
  loadStripe: (...args: [string]) => mockLoadStripe(...args),
}));

jest.mock('@/features/shared/payment/utils/stripe', () => ({
  getStripe: () => mockLoadStripe('pk_test_mock'),
}));

jest.mock('@/lib/api', () => ({
  API_ENDPOINTS: {
    INSTRUCTOR_PROFILE: '/api/v1/instructors/me',
    STRIPE_IDENTITY_REFRESH: '/api/v1/payments/identity/refresh',
  },
  fetchWithAuth: (...args: [string, RequestInit?]) => mockFetchWithAuth(...args),
  createStripeIdentitySession: (...args: []) => mockCreateStripeIdentitySession(...args),
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
  BGCStep: (props: { identityVerified?: boolean }) => {
    capturedBgcIdentityVerified = props.identityVerified;
    return <div data-testid="bgc-step">BGC Step</div>;
  },
}));

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
    rawData: mockRawData,
    refresh: mockRefreshStepStatus,
  }),
}));

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

const renderWithClient = (ui: ReactNode) => {
  const queryClient = new QueryClient();
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
};

const queueRefreshResponses = (...responses: MockRefreshResponse[]) => {
  refreshResponses = responses;
};

const makeResponse = (body: unknown, ok: boolean = true) =>
  ({
    ok,
    json: async () => body,
  }) as unknown as Response;

describe('Verification page', () => {
  const originalPublishableKey = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;

  beforeEach(() => {
    mockPush.mockClear();
    mockReplace.mockClear();
    currentSearchParams = new URLSearchParams();
    mockRawData = makeRawData();
    refreshResponses = [];
    mockFetchWithAuth.mockReset();
    mockCreateStripeIdentitySession.mockReset();
    mockCreateStripeIdentitySession.mockResolvedValue({
      verification_session_id: 'vs_123',
      client_secret: 'cs_123',
    });
    mockVerifyIdentity.mockReset();
    mockVerifyIdentity.mockResolvedValue({});
    mockLoadStripe.mockClear();
    mockRefreshStepStatus.mockClear();
    capturedBgcIdentityVerified = undefined;
    (toast.success as jest.Mock).mockClear();
    (toast.error as jest.Mock).mockClear();
    (toast.info as jest.Mock).mockClear();
    process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY = 'pk_test_123';

    mockFetchWithAuth.mockImplementation(async (url: unknown) => {
      if (url === '/api/v1/payments/identity/refresh') {
        const next = refreshResponses.shift() ?? {
          body: {
            status: 'verified',
            verified: true,
            last_error_code: null,
            last_error_reason: null,
          },
        };
        if (next.reject) {
          throw new Error('network down');
        }
        return makeResponse(
          {
            status: 'verified',
            verified: true,
            last_error_code: null,
            last_error_reason: null,
            ...next.body,
          },
          next.ok ?? true
        );
      }

      return makeResponse({});
    });
  });

  afterAll(() => {
    if (originalPublishableKey === undefined) {
      delete process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;
      return;
    }
    process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY = originalPublishableKey;
  });

  it('renders background check step and no upload UI', async () => {
    renderWithClient(<Step4Verification />);

    await waitFor(() => expect(screen.getByTestId('bgc-step')).toBeInTheDocument());
    expect(screen.queryByText(/choose file/i)).not.toBeInTheDocument();
    expect(capturedBgcIdentityVerified).toBe(false);
  });

  it('keeps peer section headings at h2 level', async () => {
    renderWithClient(<Step4Verification />);

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { level: 2, name: /identity verification/i })
      ).toBeInTheDocument()
    );
    expect(
      screen.getByRole('heading', { level: 2, name: /background check/i })
    ).toBeInTheDocument();
  });

  it('navigates back to status when coming from status', async () => {
    currentSearchParams = new URLSearchParams('from=status');
    renderWithClient(<Step4Verification />);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /save & continue/i })).toBeInTheDocument()
    );
    fireEvent.click(screen.getByRole('button', { name: /save & continue/i }));
    expect(mockPush).toHaveBeenCalledWith('/instructor/onboarding/status');
  });

  it('navigates to payment setup by default', async () => {
    renderWithClient(<Step4Verification />);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /save & continue/i })).toBeInTheDocument()
    );
    fireEvent.click(screen.getByRole('button', { name: /save & continue/i }));
    expect(mockPush).toHaveBeenCalledWith('/instructor/onboarding/payment-setup');
  });

  it('renders the not_started state with no banner and enabled start button', async () => {
    renderWithClient(<Step4Verification />);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /start verification/i })).toBeEnabled()
    );
    expect(screen.queryByText(/we're reviewing your documents/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/identity verification complete/i)).not.toBeInTheDocument();
  });

  it('renders the processing state with a blue banner and disabled button', async () => {
    mockRawData = makeRawData({ identity_verification_session_id: 'vs_processing' });
    queueRefreshResponses({
      body: {
        status: 'processing',
        verified: false,
        last_error_code: null,
        last_error_reason: null,
      },
    });

    renderWithClient(<Step4Verification />);

    await waitFor(() =>
      expect(
        screen.getByText("We're reviewing your documents. This usually takes less than a minute.")
      ).toBeInTheDocument()
    );
    expect(
      screen.getByRole('button', { name: /verification in progress/i })
    ).toBeDisabled();
  });

  it('renders the verified state with a green banner and disabled button', async () => {
    mockRawData = makeRawData({
      identity_verified_at: '2026-03-05T12:00:00Z',
      identity_verification_session_id: 'vs_verified',
    });

    renderWithClient(<Step4Verification />);

    await waitFor(() =>
      expect(screen.getByText(/identity verification complete\./i)).toBeInTheDocument()
    );
    expect(screen.getByRole('button', { name: /^verified$/i })).toBeDisabled();
    expect(
      screen.queryByText(/the last name on your id doesn't match your account name/i)
    ).not.toBeInTheDocument();
  });

  it('shows an amber mismatch banner when verification is complete with a name mismatch', async () => {
    mockRawData = makeRawData({
      identity_verified_at: '2026-03-05T12:00:00Z',
      identity_verification_session_id: 'vs_verified',
      identity_name_mismatch: true,
    });

    renderWithClient(<Step4Verification />);

    await waitFor(() =>
      expect(screen.getByText(/identity verification complete\./i)).toBeInTheDocument()
    );
    expect(
      screen.getByText(/the last name on your id doesn't match your account name/i)
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /update my name/i })
    ).toBeInTheDocument();
  });

  it('navigates to profile settings from the mismatch banner', async () => {
    mockRawData = makeRawData({
      identity_verified_at: '2026-03-05T12:00:00Z',
      identity_verification_session_id: 'vs_verified',
      identity_name_mismatch: true,
    });

    renderWithClient(<Step4Verification />);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /update my name/i })).toBeInTheDocument()
    );
    fireEvent.click(screen.getByRole('button', { name: /update my name/i }));
    expect(mockPush).toHaveBeenCalledWith('/instructor/settings');
  });

  it('shows BGC mismatch banner when bgc_name_mismatch is true', async () => {
    mockRawData = makeRawData({ bgc_name_mismatch: true });

    renderWithClient(<Step4Verification />);

    await waitFor(() =>
      expect(
        screen.getByText(
          /the information submitted during your background check doesn't match your verified identity/i
        )
      ).toBeInTheDocument()
    );
  });

  it('does not show BGC mismatch banner when bgc_name_mismatch is false', async () => {
    mockRawData = makeRawData({ bgc_name_mismatch: false });

    renderWithClient(<Step4Verification />);

    await waitFor(() => expect(screen.getByTestId('bgc-step')).toBeInTheDocument());
    expect(
      screen.queryByText(
        /the information submitted during your background check doesn't match your verified identity/i
      )
    ).not.toBeInTheDocument();
  });

  it('renders the requires_input state with a mapped amber banner and retry button', async () => {
    mockRawData = makeRawData({ identity_verification_session_id: 'vs_retry' });
    queueRefreshResponses({
      body: {
        status: 'requires_input',
        verified: false,
        last_error_code: 'document_expired',
        last_error_reason: 'expired',
      },
    });

    renderWithClient(<Step4Verification />);

    await waitFor(() =>
      expect(
        screen.getByText(
          'Your document appears to be expired. Please try again with a valid, non-expired ID.'
        )
      ).toBeInTheDocument()
    );
    expect(screen.getByRole('button', { name: /retry verification/i })).toBeEnabled();
  });

  it('falls back to the generic message for unknown requires_input error codes', async () => {
    mockRawData = makeRawData({ identity_verification_session_id: 'vs_retry' });
    queueRefreshResponses({
      body: {
        status: 'requires_input',
        verified: false,
        last_error_code: 'unknown_code',
        last_error_reason: 'unknown',
      },
    });

    renderWithClient(<Step4Verification />);

    await waitFor(() =>
      expect(screen.getByText("Verification couldn't be completed. Please try again.")).toBeInTheDocument()
    );
  });

  it('treats requires_input without an error code as a neutral start state', async () => {
    mockRawData = makeRawData({ identity_verification_session_id: 'vs_retry' });
    queueRefreshResponses({
      body: {
        status: 'requires_input',
        verified: false,
        last_error_code: null,
        last_error_reason: null,
      },
    });

    renderWithClient(<Step4Verification />);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /start verification/i })).toBeEnabled()
    );
    expect(
      screen.queryByText("Verification couldn't be completed. Please try again.")
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /retry verification/i })).not.toBeInTheDocument();
  });

  it('renders the canceled state with a gray banner and enabled start button', async () => {
    mockRawData = makeRawData({ identity_verification_session_id: 'vs_canceled' });
    queueRefreshResponses({
      body: {
        status: 'canceled',
        verified: false,
        last_error_code: null,
        last_error_reason: null,
      },
    });

    renderWithClient(<Step4Verification />);

    await waitFor(() =>
      expect(screen.getByText(/your verification session was canceled\./i)).toBeInTheDocument()
    );
    expect(screen.getByRole('button', { name: /start verification/i })).toBeEnabled();
  });

  it('clears a stale requires_input banner when retry starts processing', async () => {
    mockRawData = makeRawData({ identity_verification_session_id: 'vs_retry' });
    mockCreateStripeIdentitySession.mockResolvedValue({
      verification_session_id: 'vs_retry',
      client_secret: 'cs_retry',
    });
    queueRefreshResponses({
      body: {
        status: 'requires_input',
        verified: false,
        last_error_code: 'document_expired',
        last_error_reason: 'expired',
      },
    });

    renderWithClient(<Step4Verification />);

    await waitFor(() =>
      expect(
        screen.getByText(
          'Your document appears to be expired. Please try again with a valid, non-expired ID.'
        )
      ).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole('button', { name: /retry verification/i }));

    await waitFor(() => expect(mockCreateStripeIdentitySession).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(
        screen.getByText("We're reviewing your documents. This usually takes less than a minute.")
      ).toBeInTheDocument()
    );
    expect(
      screen.queryByText(
        'Your document appears to be expired. Please try again with a valid, non-expired ID.'
      )
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /verification in progress/i })
    ).toBeDisabled();
    expect(mockReplace).toHaveBeenCalledWith(
      '/instructor/onboarding/verification?identity_return=true'
    );
  });

  describe('identity return polling', () => {
    beforeEach(() => {
      jest.useFakeTimers();
    });

    afterEach(() => {
      jest.runOnlyPendingTimers();
      jest.useRealTimers();
    });

    it('refreshes identity and shows toast when returning from Stripe', async () => {
      currentSearchParams = new URLSearchParams('identity_return=true');
      queueRefreshResponses({
        body: {
          status: 'verified',
          verified: true,
          last_error_code: null,
          last_error_reason: null,
        },
      });

      renderWithClient(<Step4Verification />);

      await waitFor(() =>
        expect(mockFetchWithAuth).toHaveBeenCalledWith('/api/v1/payments/identity/refresh', {
          method: 'POST',
        })
      );
      await waitFor(() =>
        expect(mockReplace).toHaveBeenCalledWith('/instructor/onboarding/verification')
      );
      await waitFor(() =>
        expect(toast.success).toHaveBeenCalledWith('Identity check complete', {
          description: 'Next, start your background check.',
        })
      );
    });

    it('polls until verified when initial refresh returns processing', async () => {
      currentSearchParams = new URLSearchParams('identity_return=true');
      let refreshCalls = 0;
      mockFetchWithAuth.mockImplementation(async (url: unknown) => {
        if (url !== '/api/v1/payments/identity/refresh') {
          return makeResponse({});
        }

        refreshCalls += 1;
        return makeResponse({
          status: refreshCalls >= 3 ? 'verified' : 'processing',
          verified: refreshCalls >= 3,
          last_error_code: null,
          last_error_reason: null,
        });
      });

      renderWithClient(<Step4Verification />);

      await waitFor(() => expect(refreshCalls).toBe(1));
      await act(async () => {
        await jest.advanceTimersByTimeAsync(5000);
      });
      await waitFor(() => expect(refreshCalls).toBe(2));
      await act(async () => {
        await jest.advanceTimersByTimeAsync(5000);
      });
      await waitFor(() => expect(refreshCalls).toBe(3));
      await waitFor(() =>
        expect(toast.success).toHaveBeenCalledWith('Identity check complete', {
          description: 'Next, start your background check.',
        })
      );
      expect(mockRefreshStepStatus).toHaveBeenCalledTimes(3);
      expect(mockReplace).toHaveBeenCalledWith('/instructor/onboarding/verification');
    });

    it('stops polling after 12 attempts and shows info toast while still processing', async () => {
      currentSearchParams = new URLSearchParams('identity_return=true');
      let refreshCalls = 0;
      mockFetchWithAuth.mockImplementation(async (url: unknown) => {
        if (url !== '/api/v1/payments/identity/refresh') {
          return makeResponse({});
        }

        refreshCalls += 1;
        return makeResponse({
          status: 'processing',
          verified: false,
          last_error_code: null,
          last_error_reason: null,
        });
      });

      renderWithClient(<Step4Verification />);

      await waitFor(() => expect(refreshCalls).toBe(1));
      for (let i = 0; i < 11; i += 1) {
        await act(async () => {
          await jest.advanceTimersByTimeAsync(5000);
        });
      }
      await waitFor(() => expect(refreshCalls).toBe(12));
      await waitFor(() =>
        expect(toast.info).toHaveBeenCalledWith('Verification still processing', {
          description:
            'Stripe is finishing your verification. This page will update automatically when complete.',
        })
      );
      expect(mockRefreshStepStatus).toHaveBeenCalledTimes(12);
      expect(mockReplace).toHaveBeenCalledWith('/instructor/onboarding/verification');
      await act(async () => {
        await jest.advanceTimersByTimeAsync(15000);
      });
      expect(refreshCalls).toBe(12);
    });

    it('stops polling immediately when refresh returns requires_input', async () => {
      currentSearchParams = new URLSearchParams('identity_return=true');
      queueRefreshResponses({
        body: {
          status: 'requires_input',
          verified: false,
          last_error_code: 'document_expired',
          last_error_reason: 'expired',
        },
      });

      renderWithClient(<Step4Verification />);

      await waitFor(() =>
        expect(
          screen.getByText(
            'Your document appears to be expired. Please try again with a valid, non-expired ID.'
          )
        ).toBeInTheDocument()
      );
      expect(
        screen.getByRole('button', { name: /retry verification/i })
      ).toBeEnabled();
      expect(mockReplace).toHaveBeenCalledWith('/instructor/onboarding/verification');
      expect(toast.success).not.toHaveBeenCalled();
      expect(toast.info).not.toHaveBeenCalled();
    });

    it('cleans up poll timer on unmount', async () => {
      currentSearchParams = new URLSearchParams('identity_return=true');
      let refreshCalls = 0;
      mockFetchWithAuth.mockImplementation(async (url: unknown) => {
        if (url !== '/api/v1/payments/identity/refresh') {
          return makeResponse({});
        }

        refreshCalls += 1;
        return makeResponse({
          status: 'processing',
          verified: false,
          last_error_code: null,
          last_error_reason: null,
        });
      });

      const view = renderWithClient(<Step4Verification />);
      await waitFor(() => expect(refreshCalls).toBe(1));
      view.unmount();

      await act(async () => {
        await jest.advanceTimersByTimeAsync(15000);
      });
      expect(refreshCalls).toBe(1);
    });

    it('does not poll when identity_return is absent', async () => {
      renderWithClient(<Step4Verification />);

      await act(async () => {
        await jest.advanceTimersByTimeAsync(10000);
      });
      const refreshEndpointCalls = mockFetchWithAuth.mock.calls.filter(
        ([url]) => url === '/api/v1/payments/identity/refresh'
      );
      expect(refreshEndpointCalls).toHaveLength(0);
    });

    it('ignores transient refresh failures and keeps the previous processing UI', async () => {
      currentSearchParams = new URLSearchParams('identity_return=true');
      mockRawData = makeRawData({ identity_verification_session_id: 'vs_processing' });
      queueRefreshResponses({ reject: true }, { reject: true });

      renderWithClient(<Step4Verification />);

      await waitFor(() =>
        expect(
          screen.getByText("We're reviewing your documents. This usually takes less than a minute.")
        ).toBeInTheDocument()
      );

      await act(async () => {
        await jest.advanceTimersByTimeAsync(5000);
      });

      expect(
        screen.getByRole('button', { name: /verification in progress/i })
      ).toBeDisabled();
      expect(toast.error).not.toHaveBeenCalled();
    });

    it('removes identity_return from the URL after polling completes', async () => {
      currentSearchParams = new URLSearchParams('identity_return=true');
      queueRefreshResponses({
        body: {
          status: 'verified',
          verified: true,
          last_error_code: null,
          last_error_reason: null,
        },
      });

      renderWithClient(<Step4Verification />);
      await waitFor(() =>
        expect(mockReplace).toHaveBeenCalledWith('/instructor/onboarding/verification')
      );
    });
  });
});
