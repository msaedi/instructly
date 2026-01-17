import { renderHook, waitFor } from '@testing-library/react';
import { useOnboardingStepStatus, canInstructorGoLive } from '../useOnboardingStepStatus';
import { fetchWithAuth, API_ENDPOINTS, getConnectStatus } from '@/lib/api';

jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(),
  getConnectStatus: jest.fn(),
  API_ENDPOINTS: {
    ME: '/api/v1/auth/me',
    INSTRUCTOR_PROFILE: '/api/v1/instructors/me',
    CONNECT_STATUS: '/api/v1/payments/connect/status',
  },
}));

const fetchWithAuthMock = fetchWithAuth as jest.Mock;
const getConnectStatusMock = getConnectStatus as jest.Mock;

const makeResponse = (data: unknown, ok = true) => ({
  ok,
  json: jest.fn().mockResolvedValue(data),
});

describe('useOnboardingStepStatus', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    getConnectStatusMock.mockReset();
  });

  it('skips evaluation when skip is true', async () => {
    const { result } = renderHook(() => useOnboardingStepStatus({ skip: true }));

    expect(result.current.loading).toBe(false);
    expect(fetchWithAuthMock).not.toHaveBeenCalled();
  });

  it('marks all steps done when data is complete', async () => {
    const user = {
      first_name: 'Jane',
      last_name: 'Doe',
      zip_code: '10001',
      has_profile_picture: true,
    };
    const profile = {
      id: 'instructor-1',
      bio: 'x'.repeat(400),
      services: [{ id: 'svc-1' }],
      identity_verified_at: '2024-01-01T00:00:00Z',
    };
    const serviceAreas = { items: [{ id: 'area-1' }] };
    const addresses = { items: [{ postal_code: '10001', is_default: true }] };

    fetchWithAuthMock.mockImplementation((url: string) => {
      if (url === API_ENDPOINTS.ME) return Promise.resolve(makeResponse(user));
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) return Promise.resolve(makeResponse(profile));
      if (url === '/api/v1/addresses/service-areas/me') return Promise.resolve(makeResponse(serviceAreas));
      if (url === '/api/v1/addresses/me') return Promise.resolve(makeResponse(addresses));
      if (url === `/api/v1/instructors/${profile.id}/bgc/status`) return Promise.resolve(makeResponse({ status: 'PASSED' }));
      return Promise.resolve(makeResponse(null, false));
    });
    getConnectStatusMock.mockResolvedValueOnce({ onboarding_completed: true });

    const { result } = renderHook(() => useOnboardingStepStatus());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus).toEqual({
      'account-setup': 'done',
      'skill-selection': 'done',
      'verify-identity': 'done',
      'payment-setup': 'done',
    });
  });

  it('marks steps failed when data is incomplete', async () => {
    const user = {
      first_name: '',
      last_name: '',
      zip_code: '',
      has_profile_picture: false,
    };
    const profile = {
      id: 'instructor-1',
      bio: 'short',
      services: [],
    };

    fetchWithAuthMock.mockImplementation((url: string) => {
      if (url === API_ENDPOINTS.ME) return Promise.resolve(makeResponse(user));
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) return Promise.resolve(makeResponse(profile));
      if (url === '/api/v1/addresses/service-areas/me') return Promise.resolve(makeResponse({ items: [] }));
      if (url === '/api/v1/addresses/me') return Promise.resolve(makeResponse({ items: [] }));
      return Promise.resolve(makeResponse(null, false));
    });
    getConnectStatusMock.mockResolvedValueOnce({ onboarding_completed: false });

    const { result } = renderHook(() => useOnboardingStepStatus());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus['account-setup']).toBe('failed');
    expect(result.current.stepStatus['skill-selection']).toBe('failed');
    expect(result.current.stepStatus['verify-identity']).toBe('failed');
    expect(result.current.stepStatus['payment-setup']).toBe('failed');
  });

  it('falls back to profile background check status when endpoint fails', async () => {
    const user = {
      first_name: 'Jane',
      last_name: 'Doe',
      zip_code: '10001',
      has_profile_picture: true,
    };
    const profile = {
      id: 'instructor-1',
      bio: 'x'.repeat(400),
      services: [{ id: 'svc-1' }],
      identity_verified_at: '2024-01-01T00:00:00Z',
      bgc_status: 'clear',
    };

    fetchWithAuthMock.mockImplementation((url: string) => {
      if (url === API_ENDPOINTS.ME) return Promise.resolve(makeResponse(user));
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) return Promise.resolve(makeResponse(profile));
      if (url === '/api/v1/addresses/service-areas/me') return Promise.resolve(makeResponse({ items: [{ id: 'area-1' }] }));
      if (url === '/api/v1/addresses/me') return Promise.resolve(makeResponse({ items: [{ postal_code: '10001', is_default: true }] }));
      if (url === `/api/v1/instructors/${profile.id}/bgc/status`) return Promise.resolve(makeResponse(null, false));
      return Promise.resolve(makeResponse(null, false));
    });
    getConnectStatusMock.mockResolvedValueOnce({ onboarding_completed: true });

    const { result } = renderHook(() => useOnboardingStepStatus());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus['verify-identity']).toBe('done');
  });
});

describe('canInstructorGoLive', () => {
  it('returns missing requirements when incomplete', () => {
    const result = canInstructorGoLive({
      profile: { bio: 'short', services: [] } as never,
      user: { first_name: '', last_name: '', has_profile_picture: false } as never,
      serviceAreas: [],
      connectStatus: { onboarding_completed: false } as never,
      bgcStatus: 'pending',
    });

    expect(result.canGoLive).toBe(false);
    expect(result.missing).toEqual(
      expect.arrayContaining(['Profile picture', 'First name', 'Last name', 'Bio (400+ characters)', 'Service areas', 'Skills & pricing', 'ID verification', 'Background check', 'Stripe Connect'])
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
      } as never,
      serviceAreas: [{ id: 'area-1' } as never],
      connectStatus: { onboarding_completed: true } as never,
      bgcStatus: 'passed',
    });

    expect(result.canGoLive).toBe(true);
    expect(result.missing).toEqual([]);
  });
});
