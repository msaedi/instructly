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

  it('handles API failures gracefully', async () => {
    fetchWithAuthMock.mockRejectedValue(new Error('Network error'));
    getConnectStatusMock.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useOnboardingStepStatus());

    await waitFor(() => expect(result.current.loading).toBe(false));

    // All steps remain pending on error
    expect(result.current.stepStatus['account-setup']).toBe('pending');
  });

  it('uses profile_picture_version for hasPic check', async () => {
    const user = {
      first_name: 'Jane',
      last_name: 'Doe',
      zip_code: '10001',
      has_profile_picture: false, // false but has version
      profile_picture_version: 2,
    };
    const profile = {
      id: 'instructor-1',
      bio: 'x'.repeat(400),
      services: [{ id: 'svc-1' }],
      identity_verified_at: '2024-01-01T00:00:00Z',
    };

    fetchWithAuthMock.mockImplementation((url: string) => {
      if (url === API_ENDPOINTS.ME) return Promise.resolve(makeResponse(user));
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) return Promise.resolve(makeResponse(profile));
      if (url === '/api/v1/addresses/service-areas/me') return Promise.resolve(makeResponse({ items: [{ id: 'area-1' }] }));
      if (url === '/api/v1/addresses/me') return Promise.resolve(makeResponse({ items: [{ postal_code: '10001', is_default: true }] }));
      if (url.includes('/bgc/status')) return Promise.resolve(makeResponse({ status: 'passed' }));
      return Promise.resolve(makeResponse(null, false));
    });
    getConnectStatusMock.mockResolvedValueOnce({ onboarding_completed: true });

    const { result } = renderHook(() => useOnboardingStepStatus());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus['account-setup']).toBe('done');
  });

  it('handles bgc status "eligible" as passed', async () => {
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

    fetchWithAuthMock.mockImplementation((url: string) => {
      if (url === API_ENDPOINTS.ME) return Promise.resolve(makeResponse(user));
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) return Promise.resolve(makeResponse(profile));
      if (url === '/api/v1/addresses/service-areas/me') return Promise.resolve(makeResponse({ items: [{ id: 'area-1' }] }));
      if (url === '/api/v1/addresses/me') return Promise.resolve(makeResponse({ items: [{ postal_code: '10001', is_default: true }] }));
      if (url.includes('/bgc/status')) return Promise.resolve(makeResponse({ status: 'eligible' }));
      return Promise.resolve(makeResponse(null, false));
    });
    getConnectStatusMock.mockResolvedValueOnce({ onboarding_completed: true });

    const { result } = renderHook(() => useOnboardingStepStatus());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus['verify-identity']).toBe('done');
  });

  it('falls back to user zip_code when address parsing fails', async () => {
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

    fetchWithAuthMock.mockImplementation((url: string) => {
      if (url === API_ENDPOINTS.ME) return Promise.resolve(makeResponse(user));
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) return Promise.resolve(makeResponse(profile));
      if (url === '/api/v1/addresses/service-areas/me') return Promise.resolve(makeResponse({ items: [{ id: 'area-1' }] }));
      if (url === '/api/v1/addresses/me') {
        // Simulate ok but json parsing error
        return Promise.resolve({
          ok: true,
          json: jest.fn().mockRejectedValue(new Error('JSON parse error')),
        });
      }
      if (url.includes('/bgc/status')) return Promise.resolve(makeResponse({ status: 'passed' }));
      return Promise.resolve(makeResponse(null, false));
    });
    getConnectStatusMock.mockResolvedValueOnce({ onboarding_completed: true });

    const { result } = renderHook(() => useOnboardingStepStatus());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus['account-setup']).toBe('done');
  });

  it('uses background_check_status field when bgc_status not present', async () => {
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
      background_check_status: 'PASSED',
    };

    fetchWithAuthMock.mockImplementation((url: string) => {
      if (url === API_ENDPOINTS.ME) return Promise.resolve(makeResponse(user));
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) return Promise.resolve(makeResponse(profile));
      if (url === '/api/v1/addresses/service-areas/me') return Promise.resolve(makeResponse({ items: [{ id: 'area-1' }] }));
      if (url === '/api/v1/addresses/me') return Promise.resolve(makeResponse({ items: [{ postal_code: '10001', is_default: true }] }));
      if (url.includes('/bgc/status')) return Promise.resolve(makeResponse(null, false));
      return Promise.resolve(makeResponse(null, false));
    });
    getConnectStatusMock.mockResolvedValueOnce({ onboarding_completed: true });

    const { result } = renderHook(() => useOnboardingStepStatus());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus['verify-identity']).toBe('done');
  });

  it('handles bgc status endpoint throwing error', async () => {
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
      bgc_status: 'passed',
    };

    fetchWithAuthMock.mockImplementation((url: string) => {
      if (url === API_ENDPOINTS.ME) return Promise.resolve(makeResponse(user));
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) return Promise.resolve(makeResponse(profile));
      if (url === '/api/v1/addresses/service-areas/me') return Promise.resolve(makeResponse({ items: [{ id: 'area-1' }] }));
      if (url === '/api/v1/addresses/me') return Promise.resolve(makeResponse({ items: [{ postal_code: '10001', is_default: true }] }));
      if (url.includes('/bgc/status')) return Promise.reject(new Error('BGC service down'));
      return Promise.resolve(makeResponse(null, false));
    });
    getConnectStatusMock.mockResolvedValueOnce({ onboarding_completed: true });

    const { result } = renderHook(() => useOnboardingStepStatus());

    await waitFor(() => expect(result.current.loading).toBe(false));

    // Falls back to profile.bgc_status
    expect(result.current.stepStatus['verify-identity']).toBe('done');
  });

  it('uses first address when no default address exists', async () => {
    const user = {
      first_name: 'Jane',
      last_name: 'Doe',
      has_profile_picture: true,
    };
    const profile = {
      id: 'instructor-1',
      bio: 'x'.repeat(400),
      services: [{ id: 'svc-1' }],
      identity_verified_at: '2024-01-01T00:00:00Z',
    };

    fetchWithAuthMock.mockImplementation((url: string) => {
      if (url === API_ENDPOINTS.ME) return Promise.resolve(makeResponse(user));
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) return Promise.resolve(makeResponse(profile));
      if (url === '/api/v1/addresses/service-areas/me') return Promise.resolve(makeResponse({ items: [{ id: 'area-1' }] }));
      if (url === '/api/v1/addresses/me') {
        return Promise.resolve(makeResponse({ items: [{ postal_code: '10002', is_default: false }] }));
      }
      if (url.includes('/bgc/status')) return Promise.resolve(makeResponse({ status: 'passed' }));
      return Promise.resolve(makeResponse(null, false));
    });
    getConnectStatusMock.mockResolvedValueOnce({ onboarding_completed: true });

    const { result } = renderHook(() => useOnboardingStepStatus());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.stepStatus['account-setup']).toBe('done');
  });

  it('handles non-string bgc status response', async () => {
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
      bgc_status: 12345, // Non-string status
    };

    fetchWithAuthMock.mockImplementation((url: string) => {
      if (url === API_ENDPOINTS.ME) return Promise.resolve(makeResponse(user));
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) return Promise.resolve(makeResponse(profile));
      if (url === '/api/v1/addresses/service-areas/me') return Promise.resolve(makeResponse({ items: [{ id: 'area-1' }] }));
      if (url === '/api/v1/addresses/me') return Promise.resolve(makeResponse({ items: [{ postal_code: '10001', is_default: true }] }));
      if (url.includes('/bgc/status')) return Promise.resolve(makeResponse({ status: null }));
      return Promise.resolve(makeResponse(null, false));
    });
    getConnectStatusMock.mockResolvedValueOnce({ onboarding_completed: true });

    const { result } = renderHook(() => useOnboardingStepStatus());

    await waitFor(() => expect(result.current.loading).toBe(false));

    // Verify identity fails because bgc status is not valid
    expect(result.current.stepStatus['verify-identity']).toBe('failed');
  });

  it('exposes refresh function for manual re-evaluation', async () => {
    fetchWithAuthMock.mockImplementation((url: string) => {
      if (url === API_ENDPOINTS.ME) return Promise.resolve(makeResponse({ first_name: 'A', last_name: 'B' }));
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) return Promise.resolve(makeResponse({ id: 'i-1' }));
      if (url === '/api/v1/addresses/service-areas/me') return Promise.resolve(makeResponse({ items: [] }));
      if (url === '/api/v1/addresses/me') return Promise.resolve(makeResponse({ items: [] }));
      return Promise.resolve(makeResponse(null, false));
    });
    getConnectStatusMock.mockResolvedValue({ onboarding_completed: false });

    const { result } = renderHook(() => useOnboardingStepStatus());

    await waitFor(() => expect(result.current.loading).toBe(false));

    // Call refresh
    await result.current.refresh();

    expect(fetchWithAuthMock).toHaveBeenCalledTimes(10); // Initial 5 + refresh 5
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

  it('accepts profile_picture_version as valid profile picture', () => {
    const result = canInstructorGoLive({
      profile: {
        bio: 'x'.repeat(400),
        services: [{ id: 'svc-1' }],
        identity_verified_at: '2024-01-01T00:00:00Z',
      } as never,
      user: {
        first_name: 'Jane',
        last_name: 'Doe',
        has_profile_picture: false,
        profile_picture_version: 3, // Version present but has_profile_picture is false
      } as never,
      serviceAreas: [{ id: 'area-1' } as never],
      connectStatus: { onboarding_completed: true } as never,
      bgcStatus: 'passed',
    });

    expect(result.canGoLive).toBe(true);
    expect(result.missing).not.toContain('Profile picture');
  });

  it('accepts identity_verification_session_id when identity_verified_at is missing', () => {
    const result = canInstructorGoLive({
      profile: {
        bio: 'x'.repeat(400),
        services: [{ id: 'svc-1' }],
        identity_verification_session_id: 'session-123', // Session exists but not verified yet
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

    expect(result.missing).not.toContain('ID verification');
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
    expect(result.missing).toContain('Bio (400+ characters)');
    expect(result.missing).toContain('Service areas');
  });

  it('handles profile with services as non-array', () => {
    const result = canInstructorGoLive({
      profile: {
        bio: 'x'.repeat(400),
        services: null,
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

    expect(result.missing).toContain('Skills & pricing');
  });
});
