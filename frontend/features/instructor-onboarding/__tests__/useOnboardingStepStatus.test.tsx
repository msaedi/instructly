import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { fetchWithAuth } from '@/lib/api';
import { useInstructorProfileMe } from '@/hooks/queries/useInstructorProfileMe';
import { useInstructorServiceAreas } from '@/hooks/queries/useInstructorServiceAreas';
import { useStripeConnectStatus } from '@/hooks/queries/useStripeConnectStatus';
import { useUserAddresses } from '@/hooks/queries/useUserAddresses';
import { useSession } from '@/src/api/hooks/useSession';

import { canInstructorGoLive, useOnboardingStepStatus } from '../useOnboardingStepStatus';

jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(),
}));

jest.mock('@/hooks/queries/useInstructorProfileMe', () => ({
  useInstructorProfileMe: jest.fn(),
}));

jest.mock('@/hooks/queries/useInstructorServiceAreas', () => ({
  useInstructorServiceAreas: jest.fn(),
}));

jest.mock('@/hooks/queries/useStripeConnectStatus', () => ({
  useStripeConnectStatus: jest.fn(),
}));

jest.mock('@/hooks/queries/useUserAddresses', () => ({
  useUserAddresses: jest.fn(),
}));

jest.mock('@/src/api/hooks/useSession', () => ({
  useSession: jest.fn(),
}));

type MockQueryResult<T> = {
  data: T | undefined;
  isLoading: boolean;
  isError: boolean;
  isFetched: boolean;
  refetch: jest.Mock<Promise<unknown>, []>;
};

type HookOverrides = {
  user?: MockQueryResult<Record<string, unknown> | null>;
  profile?: MockQueryResult<Record<string, unknown> | null>;
  addresses?: MockQueryResult<{ items: Array<Record<string, unknown>> } | null>;
  serviceAreas?: MockQueryResult<{ items: Array<Record<string, unknown>> } | null>;
  connectStatus?: MockQueryResult<Record<string, unknown> | null>;
};

const fetchWithAuthMock = fetchWithAuth as jest.MockedFunction<typeof fetchWithAuth>;
const useInstructorProfileMeMock = useInstructorProfileMe as jest.Mock;
const useInstructorServiceAreasMock = useInstructorServiceAreas as jest.Mock;
const useStripeConnectStatusMock = useStripeConnectStatus as jest.Mock;
const useUserAddressesMock = useUserAddresses as jest.Mock;
const useSessionMock = useSession as jest.Mock;

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }

  return Wrapper;
}

function makeQueryResult<T>(
  data?: T,
  overrides?: Partial<Omit<MockQueryResult<T>, 'data'>>
): MockQueryResult<T> {
  return {
    data,
    isLoading: false,
    isError: false,
    isFetched: data !== undefined,
    refetch: jest.fn(async () => ({ data })),
    ...overrides,
  };
}

function setupHookMocks(overrides?: HookOverrides) {
  useSessionMock.mockReturnValue(
    overrides?.user ??
      makeQueryResult({
        first_name: 'Jane',
        last_name: 'Doe',
        zip_code: '10001',
        has_profile_picture: true,
        phone_verified: true,
      })
  );

  useInstructorProfileMeMock.mockReturnValue(
    overrides?.profile ??
      makeQueryResult({
        id: 'instructor-1',
        bio: 'x'.repeat(400),
        services: [{ id: 'svc-1' }],
        identity_verified_at: '2024-01-01T00:00:00Z',
      })
  );

  useUserAddressesMock.mockReturnValue(
    overrides?.addresses ??
      makeQueryResult({
        items: [{ postal_code: '10001', is_default: true }],
      })
  );

  useInstructorServiceAreasMock.mockReturnValue(
    overrides?.serviceAreas ?? makeQueryResult({ items: [{ id: 'area-1' }] })
  );

  useStripeConnectStatusMock.mockReturnValue(
    overrides?.connectStatus ??
      makeQueryResult({
        onboarding_completed: true,
      })
  );
}

function okResponse(body: unknown): Response {
  return {
    ok: true,
    json: async () => body,
  } as Response;
}

function errorResponse(): Response {
  return {
    ok: false,
    json: async () => ({}),
  } as Response;
}

describe('useOnboardingStepStatus', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    fetchWithAuthMock.mockResolvedValue(okResponse({ status: 'passed' }));
    setupHookMocks();
  });

  it('skips evaluation when skip is true', () => {
    const { result } = renderHook(() => useOnboardingStepStatus({ skip: true }), {
      wrapper: createWrapper(),
    });

    expect(result.current.loading).toBe(false);
    expect(fetchWithAuthMock).not.toHaveBeenCalled();
  });

  it('marks all steps done when shared query data is complete', async () => {
    const { result } = renderHook(() => useOnboardingStepStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus).toEqual({
      'account-setup': 'done',
      'skill-selection': 'done',
      'verify-identity': 'done',
      'payment-setup': 'done',
    });
  });

  it('marks steps failed when shared query data is incomplete', async () => {
    setupHookMocks({
      user: makeQueryResult({
        first_name: '',
        last_name: '',
        zip_code: '',
        has_profile_picture: false,
      }),
      profile: makeQueryResult({
        id: 'instructor-1',
        bio: 'short',
        services: [],
      }),
      addresses: makeQueryResult({ items: [] }),
      serviceAreas: makeQueryResult({ items: [] }),
      connectStatus: makeQueryResult({ onboarding_completed: false }),
    });
    fetchWithAuthMock.mockResolvedValue(okResponse({ status: 'pending' }));

    const { result } = renderHook(() => useOnboardingStepStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus).toEqual({
      'account-setup': 'failed',
      'skill-selection': 'failed',
      'verify-identity': 'failed',
      'payment-setup': 'failed',
    });
  });

  it('falls back to profile background check status when the status endpoint fails', async () => {
    setupHookMocks({
      profile: makeQueryResult({
        id: 'instructor-1',
        bio: 'x'.repeat(400),
        services: [{ id: 'svc-1' }],
        identity_verified_at: '2024-01-01T00:00:00Z',
        bgc_status: 'clear',
      }),
    });
    fetchWithAuthMock.mockResolvedValue(errorResponse());

    const { result } = renderHook(() => useOnboardingStepStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus['verify-identity']).toBe('done');
  });

  it('returns pending defaults when no core shared query data has loaded', async () => {
    setupHookMocks({
      user: makeQueryResult<Record<string, unknown> | null>(undefined, { isFetched: false }),
      profile: makeQueryResult<Record<string, unknown> | null>(undefined, { isFetched: false }),
      addresses: makeQueryResult<{ items: Array<Record<string, unknown>> } | null>(undefined, {
        isFetched: false,
      }),
      serviceAreas: makeQueryResult<{ items: Array<Record<string, unknown>> } | null>(
        undefined,
        { isFetched: false }
      ),
      connectStatus: makeQueryResult<Record<string, unknown> | null>(undefined, {
        isFetched: false,
      }),
    });

    const { result } = renderHook(() => useOnboardingStepStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus['account-setup']).toBe('pending');
    expect(result.current.stepStatus['skill-selection']).toBe('pending');
    expect(result.current.stepStatus['verify-identity']).toBe('pending');
    expect(result.current.stepStatus['payment-setup']).toBe('pending');
  });

  it('treats service-area query errors as missing service areas', async () => {
    setupHookMocks({
      serviceAreas: makeQueryResult<{ items: Array<Record<string, unknown>> } | null>(
        undefined,
        { isError: true, isFetched: true }
      ),
    });

    const { result } = renderHook(() => useOnboardingStepStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.rawData.serviceAreas).toBeNull();
    expect(result.current.stepStatus['account-setup']).toBe('failed');
  });

  it('treats an empty fetched service-area payload as no selected neighborhoods', async () => {
    setupHookMocks({
      serviceAreas: makeQueryResult<{ items: Array<Record<string, unknown>> } | null>(
        undefined,
        { isFetched: true }
      ),
    });

    const { result } = renderHook(() => useOnboardingStepStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.rawData.serviceAreas).toEqual([]);
    expect(result.current.stepStatus['account-setup']).toBe('failed');
  });

  it('uses profile_picture_version as a valid profile photo', async () => {
    setupHookMocks({
      user: makeQueryResult({
        first_name: 'Jane',
        last_name: 'Doe',
        zip_code: '10001',
        has_profile_picture: false,
        profile_picture_version: 2,
        phone_verified: true,
      }),
    });

    const { result } = renderHook(() => useOnboardingStepStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus['account-setup']).toBe('done');
  });

  it('requires phone verification before account setup is complete', async () => {
    setupHookMocks({
      user: makeQueryResult({
        first_name: 'Jane',
        last_name: 'Doe',
        zip_code: '10001',
        has_profile_picture: true,
        phone_verified: false,
      }),
    });

    const { result } = renderHook(() => useOnboardingStepStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus['account-setup']).toBe('failed');
  });

  it('treats bgc status "eligible" as passed', async () => {
    fetchWithAuthMock.mockResolvedValue(okResponse({ status: 'eligible' }));

    const { result } = renderHook(() => useOnboardingStepStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus['verify-identity']).toBe('done');
  });

  it('requires class locations when instructor-location services are enabled', async () => {
    setupHookMocks({
      profile: makeQueryResult({
        id: 'instructor-1',
        bio: 'x'.repeat(400),
        services: [
          {
            id: 'svc-1',
            format_prices: [{ format: 'instructor_location', hourly_rate: 100 }],
          },
        ],
        preferred_teaching_locations: [],
        identity_verified_at: '2024-01-01T00:00:00Z',
      }),
    });

    const { result } = renderHook(() => useOnboardingStepStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus['account-setup']).toBe('failed');
  });

  it('marks account setup done once instructor-location services have a class location', async () => {
    setupHookMocks({
      profile: makeQueryResult({
        id: 'instructor-1',
        bio: 'x'.repeat(400),
        services: [
          {
            id: 'svc-1',
            format_prices: [{ format: 'instructor_location', hourly_rate: 100 }],
          },
        ],
        preferred_teaching_locations: [{ address: '123 Studio Lane' }],
        identity_verified_at: '2024-01-01T00:00:00Z',
      }),
    });

    const { result } = renderHook(() => useOnboardingStepStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus['account-setup']).toBe('done');
  });

  it('ignores invalid preferred teaching location entries', async () => {
    setupHookMocks({
      profile: makeQueryResult({
        id: 'instructor-1',
        bio: 'x'.repeat(400),
        services: [
          {
            id: 'svc-1',
            format_prices: [{ format: 'instructor_location', hourly_rate: 100 }],
          },
        ],
        preferred_teaching_locations: [null, { label: 'Studio' }],
        identity_verified_at: '2024-01-01T00:00:00Z',
      }),
    });

    const { result } = renderHook(() => useOnboardingStepStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus['account-setup']).toBe('failed');
  });

  it('falls back to user zip_code when addresses are missing', async () => {
    setupHookMocks({
      addresses: makeQueryResult({ items: [] }),
    });

    const { result } = renderHook(() => useOnboardingStepStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus['account-setup']).toBe('done');
  });

  it('uses background_check_status when bgc_status is absent', async () => {
    setupHookMocks({
      profile: makeQueryResult({
        id: 'instructor-1',
        bio: 'x'.repeat(400),
        services: [{ id: 'svc-1' }],
        identity_verified_at: '2024-01-01T00:00:00Z',
        background_check_status: 'PASSED',
      }),
    });
    fetchWithAuthMock.mockResolvedValue(errorResponse());

    const { result } = renderHook(() => useOnboardingStepStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus['verify-identity']).toBe('done');
  });

  it('uses shared query hooks instead of raw address and service-area fetches', async () => {
    const { result } = renderHook(() => useOnboardingStepStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/instructors/instructor-1/bgc/status');
    expect(fetchWithAuthMock).not.toHaveBeenCalledWith('/api/v1/addresses/me');
    expect(fetchWithAuthMock).not.toHaveBeenCalledWith('/api/v1/addresses/service-areas/me');
  });

  it('exposes refresh to refetch shared queries and background check status', async () => {
    const userRefetch = jest.fn(async () => ({ data: { first_name: 'Jane' } }));
    const profileRefetch = jest.fn(async () => ({ data: { id: 'instructor-1' } }));
    const addressesRefetch = jest.fn(async () => ({ data: { items: [] } }));
    const serviceAreasRefetch = jest.fn(async () => ({ data: { items: [] } }));
    const connectRefetch = jest.fn(async () => ({ data: { onboarding_completed: false } }));

    setupHookMocks({
      user: makeQueryResult(
        {
          first_name: 'Jane',
          last_name: 'Doe',
          zip_code: '10001',
          has_profile_picture: true,
          phone_verified: true,
        },
        { refetch: userRefetch }
      ),
      profile: makeQueryResult(
        {
          id: 'instructor-1',
          bio: 'x'.repeat(400),
          services: [{ id: 'svc-1' }],
          identity_verified_at: '2024-01-01T00:00:00Z',
        },
        { refetch: profileRefetch }
      ),
      addresses: makeQueryResult(
        { items: [{ postal_code: '10001', is_default: true }] },
        { refetch: addressesRefetch }
      ),
      serviceAreas: makeQueryResult(
        { items: [{ id: 'area-1' }] },
        { refetch: serviceAreasRefetch }
      ),
      connectStatus: makeQueryResult(
        { onboarding_completed: true },
        { refetch: connectRefetch }
      ),
    });

    const { result } = renderHook(() => useOnboardingStepStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    await result.current.refresh();

    expect(userRefetch).toHaveBeenCalledTimes(1);
    expect(profileRefetch).toHaveBeenCalledTimes(1);
    expect(addressesRefetch).toHaveBeenCalledTimes(1);
    expect(serviceAreasRefetch).toHaveBeenCalledTimes(1);
    expect(connectRefetch).toHaveBeenCalledTimes(1);
    expect(fetchWithAuthMock).toHaveBeenCalledTimes(2);
  });

  it('returns early from refresh when the hook is skipped', async () => {
    const userRefetch = jest.fn(async () => ({ data: null }));
    const profileRefetch = jest.fn(async () => ({ data: null }));
    const addressesRefetch = jest.fn(async () => ({ data: null }));
    const serviceAreasRefetch = jest.fn(async () => ({ data: null }));
    const connectRefetch = jest.fn(async () => ({ data: null }));

    setupHookMocks({
      user: makeQueryResult(null, { refetch: userRefetch }),
      profile: makeQueryResult(null, { refetch: profileRefetch }),
      addresses: makeQueryResult(null, { refetch: addressesRefetch }),
      serviceAreas: makeQueryResult(null, { refetch: serviceAreasRefetch }),
      connectStatus: makeQueryResult(null, { refetch: connectRefetch }),
    });

    const { result } = renderHook(() => useOnboardingStepStatus({ skip: true }), {
      wrapper: createWrapper(),
    });

    await result.current.refresh();

    expect(userRefetch).not.toHaveBeenCalled();
    expect(profileRefetch).not.toHaveBeenCalled();
    expect(addressesRefetch).not.toHaveBeenCalled();
    expect(serviceAreasRefetch).not.toHaveBeenCalled();
    expect(connectRefetch).not.toHaveBeenCalled();
    expect(fetchWithAuthMock).not.toHaveBeenCalled();
  });
});

describe('canInstructorGoLive', () => {
  it('returns missing requirements when incomplete', () => {
    const result = canInstructorGoLive({
      profile: { bio: 'short', services: [] } as never,
      user: {
        first_name: '',
        last_name: '',
        has_profile_picture: false,
        phone_verified: false,
      } as never,
      serviceAreas: [],
      connectStatus: { onboarding_completed: false } as never,
      bgcStatus: 'pending',
    });

    expect(result.canGoLive).toBe(false);
    expect(result.missing).toEqual(
      expect.arrayContaining([
        'Profile picture',
        'First name',
        'Last name',
        'Phone verification',
        'Bio (400+ characters)',
        'Service areas',
        'Skills & pricing',
        'ID verification',
        'Background check',
        'Stripe Connect',
      ])
    );
  });

  it('returns true when all requirements are met', () => {
    const result = canInstructorGoLive({
      profile: {
        bio: 'x'.repeat(400),
        services: [{ id: 'svc-1' }],
        identity_verified_at: '2024-01-01T00:00:00Z',
      } as never,
      user: {
        first_name: 'Jane',
        last_name: 'Doe',
        has_profile_picture: true,
        phone_verified: true,
      } as never,
      serviceAreas: [{ id: 'area-1' } as never],
      connectStatus: { onboarding_completed: true } as never,
      bgcStatus: 'passed',
    });

    expect(result.canGoLive).toBe(true);
    expect(result.missing).toEqual([]);
  });

  it('requires class locations to go live when instructor-location services are enabled', () => {
    const result = canInstructorGoLive({
      profile: {
        bio: 'x'.repeat(400),
        services: [
          {
            id: 'svc-1',
            format_prices: [{ format: 'instructor_location', hourly_rate: 100 }],
          },
        ],
        preferred_teaching_locations: [],
        identity_verified_at: '2024-01-01T00:00:00Z',
      } as never,
      user: {
        first_name: 'Jane',
        last_name: 'Doe',
        phone_verified: true,
        has_profile_picture: true,
      } as never,
      serviceAreas: [{ id: 'area-1' } as never],
      connectStatus: { onboarding_completed: true } as never,
      bgcStatus: 'passed',
    });

    expect(result.canGoLive).toBe(false);
    expect(result.missing).toContain('Class locations');
  });

  it('blocks go-live when the account name does not match government ID', () => {
    const result = canInstructorGoLive({
      profile: {
        bio: 'x'.repeat(400),
        services: [{ id: 'svc-1' }],
        identity_verified_at: '2024-01-01T00:00:00Z',
        identity_name_mismatch: true,
      } as never,
      user: {
        first_name: 'Jane',
        last_name: 'Doe',
        has_profile_picture: true,
        phone_verified: true,
      } as never,
      serviceAreas: [{ id: 'area-1' } as never],
      connectStatus: { onboarding_completed: true } as never,
      bgcStatus: 'passed',
    });

    expect(result.canGoLive).toBe(false);
    expect(result.missing).toContain('Account name must match government ID');
  });

  it('blocks go-live when the background check name does not match verified identity', () => {
    const result = canInstructorGoLive({
      profile: {
        bio: 'x'.repeat(400),
        services: [{ id: 'svc-1' }],
        identity_verified_at: '2024-01-01T00:00:00Z',
        bgc_name_mismatch: true,
      } as never,
      user: {
        first_name: 'Jane',
        last_name: 'Doe',
        has_profile_picture: true,
        phone_verified: true,
      } as never,
      serviceAreas: [{ id: 'area-1' } as never],
      connectStatus: { onboarding_completed: true } as never,
      bgcStatus: 'passed',
    });

    expect(result.canGoLive).toBe(false);
    expect(result.missing).toContain('Background check name must match verified identity');
  });

  it('handles null profile gracefully', () => {
    const result = canInstructorGoLive({
      profile: null,
      user: null,
      serviceAreas: null,
      connectStatus: null,
      bgcStatus: null,
    });

    expect(result.canGoLive).toBe(false);
    expect(result.missing).toContain('Profile picture');
    expect(result.missing).toContain('Phone verification');
    expect(result.missing).toContain('Bio (400+ characters)');
    expect(result.missing).toContain('Service areas');
  });
});
