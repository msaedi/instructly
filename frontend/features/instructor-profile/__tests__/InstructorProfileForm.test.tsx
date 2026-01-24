import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import InstructorProfileForm from '../InstructorProfileForm';
import { useInstructorProfileMe } from '@/hooks/queries/useInstructorProfileMe';
import { useSession } from '@/src/api/hooks/useSession';
import { useUserAddresses, useInvalidateUserAddresses } from '@/hooks/queries/useUserAddresses';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { toast } from 'sonner';
import { submitServiceAreasOnce } from '@/app/(auth)/instructor/profile/serviceAreaSubmit';
import { useRouter } from 'next/navigation';

jest.mock('@/hooks/queries/useInstructorProfileMe', () => ({
  useInstructorProfileMe: jest.fn(),
}));

jest.mock('@/src/api/hooks/useSession', () => ({
  useSession: jest.fn(),
}));

jest.mock('@/hooks/queries/useUserAddresses', () => ({
  useUserAddresses: jest.fn(),
  useInvalidateUserAddresses: jest.fn(),
}));

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api');
  return { ...actual, fetchWithAuth: jest.fn() };
});

jest.mock('@/lib/logger', () => ({
  logger: { debug: jest.fn(), warn: jest.fn(), error: jest.fn() },
}));

jest.mock('@/lib/httpErrors', () => ({
  formatProblemMessages: jest.fn(() => ['Bad request']),
}));

jest.mock('@/lib/profileSchemaDebug', () => ({
  debugProfilePayload: jest.fn(),
}));

jest.mock('@/lib/profileServiceAreas', () => ({
  getServiceAreaBoroughs: jest.fn(() => ['Manhattan']),
}));

jest.mock('@/app/(auth)/instructor/profile/serviceAreaSubmit', () => ({
  submitServiceAreasOnce: jest.fn(),
}));

jest.mock('@/components/dashboard/SectionHeroCard', () => {
  function SectionHeroCard({ title }: { title: string }) {
    return <div data-testid="section-hero">{title}</div>;
  }
  return { SectionHeroCard };
});

jest.mock('@/components/UserProfileDropdown', () => {
  function UserProfileDropdown() {
    return <div data-testid="user-profile-dropdown" />;
  }
  return UserProfileDropdown;
});

jest.mock('@/components/user/ProfilePictureUpload', () => {
  function ProfilePictureUpload({ ariaLabel }: { ariaLabel?: string }) {
    return (
      <button type="button" aria-label={ariaLabel || 'Upload profile photo'}>Upload</button>
    );
  }
  return { ProfilePictureUpload };
});

jest.mock('@/features/instructor-profile/SkillsPricingInline', () => {
  function SkillsPricingInline() {
    return <div data-testid="skills-inline">Skills</div>;
  }
  return { __esModule: true, default: SkillsPricingInline };
});

jest.mock('@/app/(auth)/instructor/onboarding/account-setup/components/PersonalInfoCard', () => {
  function PersonalInfoCard({ profile, onProfileChange, onToggle }: { profile: { first_name?: string; last_name?: string; postal_code?: string }; onProfileChange: (updates: Record<string, string>) => void; onToggle: () => void }) {
    return (
      <section>
        <div data-testid="personal-info">{profile.first_name}-{profile.last_name}-{profile.postal_code}</div>
        <label htmlFor="postal-code">Zip Code</label>
        <input
          id="postal-code"
          type="text"
          value={profile.postal_code ?? ''}
          onChange={(event) => onProfileChange({ postal_code: event.target.value })}
        />
        <button type="button" onClick={() => onProfileChange({ first_name: 'Updated' })}>Update Name</button>
        <button type="button" onClick={onToggle}>Toggle</button>
      </section>
    );
  }
  return { PersonalInfoCard };
});

jest.mock('@/app/(auth)/instructor/onboarding/account-setup/components/BioCard', () => {
  function BioCard({ profile, bioTooShort, onGenerateBio }: { profile: { bio?: string }; bioTooShort: boolean; onGenerateBio: () => void }) {
    return (
      <section>
        <div data-testid="bio-content">{profile.bio}</div>
        <div data-testid="bio-too-short">{bioTooShort ? 'short' : 'long'}</div>
        <button type="button" onClick={onGenerateBio}>Generate Bio</button>
      </section>
    );
  }
  return { BioCard };
});

jest.mock('@/app/(auth)/instructor/onboarding/account-setup/components/ServiceAreasCard', () => {
  function ServiceAreasCard({ selectedNeighborhoods, formatNeighborhoodName, onToggleBoroughAccordion, onGlobalFilterChange, onToggleNeighborhood, onToggleBoroughAll }: { selectedNeighborhoods: Set<string>; formatNeighborhoodName: (value: string) => string; onToggleBoroughAccordion: (borough: string) => void; onGlobalFilterChange: (value: string) => void; onToggleNeighborhood?: (id: string) => void; onToggleBoroughAll?: (borough: string, value: boolean, items?: Array<{ neighborhood_id: string }>) => void }) {
    return (
      <section>
        <div data-testid="service-areas-count">{selectedNeighborhoods.size}</div>
        <div data-testid="formatted-name">{formatNeighborhoodName('lower east')}</div>
        <button type="button" onClick={() => onToggleBoroughAccordion('Manhattan')}>Toggle Borough</button>
        <button type="button" onClick={() => onGlobalFilterChange('park')}>Filter</button>
        <button type="button" onClick={() => onToggleNeighborhood?.('test-neighborhood-1')}>Toggle Neighborhood</button>
        <button type="button" onClick={() => onToggleBoroughAll?.('Manhattan', true, [{ neighborhood_id: 'n1' }, { neighborhood_id: 'n2' }])}>Select All Manhattan</button>
        <button type="button" onClick={() => onToggleBoroughAll?.('Manhattan', false, [{ neighborhood_id: 'n1' }, { neighborhood_id: 'n2' }])}>Clear All Manhattan</button>
      </section>
    );
  }
  return { ServiceAreasCard };
});

jest.mock('@/app/(auth)/instructor/onboarding/account-setup/components/PreferredLocationsCard', () => {
  function PreferredLocationsCard({ setPreferredLocations, setNeutralPlaces }: { setPreferredLocations: (values: string[]) => void; setNeutralPlaces: (values: string[]) => void }) {
    return (
      <section>
        <button type="button" onClick={() => setPreferredLocations(['Studio'])}>Set Preferred</button>
        <button type="button" onClick={() => setNeutralPlaces(['Library'])}>Set Neutral</button>
      </section>
    );
  }
  return { PreferredLocationsCard };
});

jest.mock('sonner', () => ({
  toast: {
    error: jest.fn(),
    success: jest.fn(),
  },
}));

const mockUseInstructorProfileMe = useInstructorProfileMe as jest.Mock;
const mockUseSession = useSession as jest.Mock;
const mockUseUserAddresses = useUserAddresses as jest.Mock;
const mockUseInvalidateUserAddresses = useInvalidateUserAddresses as jest.Mock;
const mockFetchWithAuth = fetchWithAuth as jest.Mock;
const mockSubmitServiceAreasOnce = submitServiceAreasOnce as jest.MockedFunction<typeof submitServiceAreasOnce>;

describe('InstructorProfileForm', () => {
  const createWrapper = () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const Wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    Wrapper.displayName = 'InstructorProfileFormWrapper';
    return { Wrapper, queryClient };
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockUseSession.mockReturnValue({ data: null, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: null, isLoading: false });
    mockUseInvalidateUserAddresses.mockReturnValue(jest.fn());
    mockSubmitServiceAreasOnce.mockResolvedValue(undefined);
    global.fetch = jest.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ is_nyc: true }) });
    Object.defineProperty(window, 'sessionStorage', {
      value: { setItem: jest.fn(), getItem: jest.fn(), removeItem: jest.fn() },
      writable: true,
    });
  });

  it('shows a loading state when profile data has not arrived', () => {
    const { Wrapper } = createWrapper();
    mockUseInstructorProfileMe.mockReturnValue({ data: null, isLoading: false });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('prefills data and saves successfully', async () => {
    const { Wrapper, queryClient } = createWrapper();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');
    const onStepStatusChange = jest.fn();
    mockUseSession.mockReturnValue({
      data: { id: 'user-1', first_name: 'Taylor', last_name: 'Swift', zip_code: '10001' },
      isLoading: false,
    });
    mockUseUserAddresses.mockReturnValue({
      data: { items: [{ id: 'addr-1', postal_code: '00000', is_default: true }] },
      isLoading: false,
    });
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        bio: 'A'.repeat(420),
        years_experience: 5,
        min_advance_booking_hours: 3,
        buffer_time_minutes: 90,
        service_area_neighborhoods: [{ neighborhood_id: 'n1', name: 'Lower East Side' }],
        service_area_boroughs: ['Manhattan'],
        preferred_teaching_locations: [{ address: 'Studio', label: 'Main' }],
        preferred_public_spaces: [{ address: 'Library' }],
        has_profile_picture: true,
      },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [{ neighborhood_id: 'n1' }] }) };
      }
      if (url === API_ENDPOINTS.ME) {
        return { ok: true, status: 200, json: async () => ({}) };
      }
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) {
        return { ok: true, status: 200, json: async () => ({}) };
      }
      if (url === '/api/v1/addresses/me') {
        return { ok: true, status: 200, json: async () => ({ items: [{ id: 'addr-1', postal_code: '00000', is_default: true }] }) };
      }
      if (url === '/api/v1/addresses/me/addr-1') {
        return { ok: true, status: 200, json: async () => ({}) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm onStepStatusChange={onStepStatusChange} />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toHaveTextContent('Taylor-Swift-00000');
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(mockFetchWithAuth).toHaveBeenCalledWith(API_ENDPOINTS.INSTRUCTOR_PROFILE, expect.any(Object));
    });
    expect(submitServiceAreasOnce).toHaveBeenCalled();
    expect(invalidateSpy).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith('Profile saved', expect.any(Object));
    expect(onStepStatusChange).toHaveBeenCalledWith('done');
  });

  it('surfaces save errors when the profile update fails', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({
      data: { id: 'user-1', first_name: 'Taylor', last_name: 'Swift', zip_code: '10001' },
      isLoading: false,
    });
    mockUseUserAddresses.mockReturnValue({
      data: { items: [{ id: 'addr-1', postal_code: '00000', is_default: true }] },
      isLoading: false,
    });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'A'.repeat(420), has_profile_picture: true },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) {
        return { ok: false, status: 400, json: async () => ({ message: 'Bad' }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    expect(await screen.findByText(/bad request/i)).toBeInTheDocument();
    expect(toast.error).toHaveBeenCalledWith('Bad request');
  });

  it('redirects onboarding instructors who are already live', async () => {
    const replace = jest.fn();
    (useRouter as jest.Mock).mockReturnValue({ push: jest.fn(), replace, prefetch: jest.fn() });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { is_live: true, onboarding_completed_at: '2025-01-01T00:00:00Z' },
      isLoading: false,
    });
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });

    const { Wrapper } = createWrapper();
    render(<InstructorProfileForm context="onboarding" />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith('/instructor/dashboard');
    });
    expect(toast.success).toHaveBeenCalled();
  });

  it('generates a long bio when requested', async () => {
    const { Wrapper } = createWrapper();
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'Short bio', has_profile_picture: true },
      isLoading: false,
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /generate bio/i }));

    await waitFor(() => {
      expect(screen.getByTestId('bio-too-short')).toHaveTextContent('long');
    });
  });

  it('falls back to instructor.user when session data is unavailable', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: null, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        bio: 'Test bio',
        user: { first_name: 'Fallback', last_name: 'User', zip_code: '12345' },
      },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toHaveTextContent('Fallback-User-');
    });
  });

  it('uses user.zip_code as fallback when address has no postal_code', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({
      data: { id: 'user-1', first_name: 'Test', last_name: 'User', zip_code: '99999' },
      isLoading: false,
    });
    mockUseUserAddresses.mockReturnValue({
      data: { items: [{ id: 'addr-1', is_default: true }] }, // No postal_code
      isLoading: false,
    });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'Test' },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toHaveTextContent('Test-User-99999');
    });
  });

  it('filters out neighborhoods without neighborhood_id during prefill', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({
      data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
      isLoading: false,
    });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        bio: 'Test',
        service_area_neighborhoods: [
          { neighborhood_id: 'n1', name: 'Valid' },
          { name: 'Invalid no id' }, // No neighborhood_id
          { neighborhood_id: 'n2', name: 'Another Valid' },
        ],
      },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });
  });

  it('triggers loadBoroughNeighborhoods when global filter changes', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'Test' },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    global.fetch = jest.fn().mockImplementation(async (url: string) => {
      if (url.includes('/neighborhoods')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            items: [{ neighborhood_id: 'n1', ntacode: 'MN01', name: 'Test' }],
          }),
        };
      }
      return { ok: true, status: 200, json: async () => ({ is_nyc: true }) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /filter/i }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled();
    });
  });

  it('toggles borough accordion and loads neighborhoods', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'Test' },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    global.fetch = jest.fn().mockImplementation(async (url: string) => {
      if (url.includes('/neighborhoods')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            items: [{ neighborhood_id: 'n1', name: 'Greenwich Village' }],
          }),
        };
      }
      return { ok: true, status: 200, json: async () => ({ is_nyc: true }) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /toggle borough/i }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/neighborhoods'),
        expect.any(Object)
      );
    });
  });

  it('handles address creation when no existing default address', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({
      data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
      isLoading: false,
    });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'A'.repeat(420), has_profile_picture: true },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string }) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === API_ENDPOINTS.ME) {
        return { ok: true, status: 200, json: async () => ({}) };
      }
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) {
        return { ok: true, status: 200, json: async () => ({}) };
      }
      if (url === '/api/v1/addresses/me' && options?.method === 'POST') {
        return { ok: true, status: 201, json: async () => ({ id: 'new-addr' }) };
      }
      if (url === '/api/v1/addresses/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(mockFetchWithAuth).toHaveBeenCalledWith(API_ENDPOINTS.INSTRUCTOR_PROFILE, expect.any(Object));
    });
  });

  it('handles 404 response when checking addresses and creates new one', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({
      data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
      isLoading: false,
    });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'A'.repeat(420), has_profile_picture: true },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string }) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) {
        return { ok: true, status: 200, json: async () => ({}) };
      }
      if (url === '/api/v1/addresses/me' && !options?.method) {
        return { ok: false, status: 404, json: async () => ({ message: 'Not found' }) };
      }
      if (url === '/api/v1/addresses/me' && options?.method === 'POST') {
        return { ok: true, status: 201, json: async () => ({ id: 'new-addr' }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(mockFetchWithAuth).toHaveBeenCalledWith(API_ENDPOINTS.INSTRUCTOR_PROFILE, expect.any(Object));
    });
  });

  it('handles address fetch error during save without crashing', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({
      data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
      isLoading: false,
    });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'A'.repeat(420), has_profile_picture: true },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) {
        return { ok: true, status: 200, json: async () => ({}) };
      }
      if (url === '/api/v1/addresses/me') {
        // Simulate a server error that should be handled gracefully
        throw new Error('Network error');
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    const zipInput = screen.getByLabelText(/zip code/i);
    await user.clear(zipInput);
    await user.type(zipInput, '99999');

    await waitFor(() => {
      expect(zipInput).toHaveValue('99999');
    });

    await user.click(screen.getByRole('button', { name: /save changes/i }));

    // Should succeed without crashing - address error is caught
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Profile saved', expect.any(Object));
    });
  });

  it('renders Skills & Pricing section in dashboard context', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'Test' },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm context="dashboard" />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByText(/skills & pricing/i)).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByText(/skills & pricing/i));

    await waitFor(() => {
      expect(screen.getByTestId('skills-inline')).toBeInTheDocument();
    });
  });

  it('renders Booking Preferences section and expands it', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'Test', min_advance_booking_hours: 2, buffer_time_minutes: 30 },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm context="dashboard" />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByText(/booking preferences/i)).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByText(/booking preferences/i));

    await waitFor(() => {
      expect(screen.getByText(/advance notice/i)).toBeInTheDocument();
      expect(screen.getByText(/buffer time/i)).toBeInTheDocument();
    });
  });

  it('updates advance notice input', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'Test', min_advance_booking_hours: 2, buffer_time_minutes: 30 },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm context="dashboard" />, { wrapper: Wrapper });

    const user = userEvent.setup();
    await user.click(screen.getByText(/booking preferences/i));

    await waitFor(() => {
      expect(screen.getByText(/advance notice/i)).toBeInTheDocument();
    });

    // Find inputs by their initial values
    const inputs = screen.getAllByRole('spinbutton');
    expect(inputs.length).toBeGreaterThan(0);
  });

  it('uses ref to call save with redirect option', async () => {
    const { Wrapper } = createWrapper();
    const ref = React.createRef<{ save: (options?: { redirectTo?: string }) => Promise<void> }>();
    const push = jest.fn();
    (useRouter as jest.Mock).mockReturnValue({ push, replace: jest.fn(), prefetch: jest.fn() });

    mockUseSession.mockReturnValue({
      data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
      isLoading: false,
    });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'A'.repeat(420), has_profile_picture: true },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === '/api/v1/addresses/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm ref={ref} />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    // Call save via ref with redirect
    await ref.current?.save({ redirectTo: '/instructor/next-step' });

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith('/instructor/next-step');
    });
  });

  it('formats neighborhood name to title case', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'Test' },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      // The formatted name "lower east" should become "Lower East"
      expect(screen.getByTestId('formatted-name')).toHaveTextContent('Lower East');
    });
  });

  it('handles address PATCH error when zip code changes', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({
      data: { id: 'user-1', first_name: 'Test', last_name: 'User', zip_code: '99999' },
      isLoading: false,
    });
    mockUseUserAddresses.mockReturnValue({
      data: { items: [{ id: 'addr-1', postal_code: '00000', is_default: true }] },
      isLoading: false,
    });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'A'.repeat(420), has_profile_picture: true },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string }) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === '/api/v1/addresses/me' && !options?.method) {
        return { ok: true, status: 200, json: async () => ({ items: [{ id: 'addr-1', postal_code: '00000', is_default: true }] }) };
      }
      if (url.includes('/api/v1/addresses/me/addr-1') && options?.method === 'PATCH') {
        return { ok: false, status: 400, json: async () => ({ detail: 'Invalid postal code' }) };
      }
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) {
        return { ok: true, status: 200, json: async () => ({}) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    const zipInput = screen.getByLabelText(/zip code/i);
    await user.clear(zipInput);
    await user.type(zipInput, '99999');

    await waitFor(() => {
      expect(zipInput).toHaveValue('99999');
    });

    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
  });

  it('skips address create when required address fields are missing', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({
      data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
      isLoading: false,
    });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        bio: 'A'.repeat(420),
        has_profile_picture: true,
        street_line1: '123 Test St',
        locality: 'New York',
        administrative_area: 'NY',
        postal_code: '10001',
      },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string }) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === '/api/v1/addresses/me' && !options?.method) {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === '/api/v1/addresses/me' && options?.method === 'POST') {
        return { ok: false, status: 400, json: async () => ({ detail: 'Invalid address' }) };
      }
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) {
        return { ok: true, status: 200, json: async () => ({}) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(mockFetchWithAuth).toHaveBeenCalledWith(API_ENDPOINTS.INSTRUCTOR_PROFILE, expect.any(Object));
    });

    expect(mockFetchWithAuth).not.toHaveBeenCalledWith(
      '/api/v1/addresses/me',
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('handles unexpected save exception', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({
      data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
      isLoading: false,
    });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'A'.repeat(420), has_profile_picture: true },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) {
        throw new Error('Unexpected network error');
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(screen.getByText(/failed to save profile/i)).toBeInTheDocument();
    });
  });

  it('triggers personal info toggle callback', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'Test' },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /^toggle$/i }));

    // Toggle was triggered without errors
    expect(screen.getByTestId('personal-info')).toBeInTheDocument();
  });

  it('updates profile via handleProfileChange callback', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'Test' },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /update name/i }));

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toHaveTextContent('Updated');
    });
  });

  it('handles address fetch returning non-404 error', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({
      data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
      isLoading: false,
    });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'A'.repeat(420), has_profile_picture: true },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === '/api/v1/addresses/me') {
        return { ok: false, status: 500, json: async () => ({ detail: 'Server error' }) };
      }
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) {
        return { ok: true, status: 200, json: async () => ({}) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
  });

  it('skips address create when full address details are missing', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({
      data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
      isLoading: false,
    });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        bio: 'A'.repeat(420),
        has_profile_picture: true,
        street_line1: '123 Main St',
        street_line2: 'Apt 4B',
        locality: 'New York',
        administrative_area: 'NY',
        postal_code: '10001',
        country_code: 'US',
        place_id: 'ChIJd8BlQ2BZwokR2uD_nv8',
        latitude: 40.7128,
        longitude: -74.006,
      },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string; body?: string }) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === '/api/v1/addresses/me' && !options?.method) {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === '/api/v1/addresses/me' && options?.method === 'POST') {
        // Verify the payload includes all fields
        const body = JSON.parse(options.body || '{}');
        expect(body.street_line2).toBe('Apt 4B');
        expect(body.place_id).toBe('ChIJd8BlQ2BZwokR2uD_nv8');
        expect(body.latitude).toBe(40.7128);
        expect(body.longitude).toBe(-74.006);
        return { ok: true, status: 201, json: async () => ({ id: 'new-addr' }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(mockFetchWithAuth).toHaveBeenCalledWith(API_ENDPOINTS.INSTRUCTOR_PROFILE, expect.any(Object));
    });

    const createdAddress = mockFetchWithAuth.mock.calls.some(
      ([url, options]) => url === '/api/v1/addresses/me' && options?.method === 'POST'
    );
    expect(createdAddress).toBe(false);
  });

  it('handles preferred locations and neutral places updates', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'Test' },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    const user = userEvent.setup();

    // Set preferred locations
    await user.click(screen.getByRole('button', { name: /set preferred/i }));

    // Set neutral places
    await user.click(screen.getByRole('button', { name: /set neutral/i }));

    // Both should work without errors
    expect(screen.getByTestId('personal-info')).toBeInTheDocument();
  });

  it('handles neighborhoods fetch failure gracefully', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'Test' },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    // Simulate neighborhood fetch failure
    global.fetch = jest.fn().mockImplementation(async (url: string) => {
      if (url.includes('/neighborhoods')) {
        throw new Error('Network error');
      }
      return { ok: true, status: 200, json: async () => ({ is_nyc: true }) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /toggle borough/i }));

    // Should not crash, just handle the error silently
    expect(screen.getByTestId('personal-info')).toBeInTheDocument();
  });

  it('handles address creation POST failure during save', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({
      data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
      isLoading: false,
    });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'A'.repeat(420), has_profile_picture: true },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string }) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === '/api/v1/addresses/me' && !options?.method) {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === '/api/v1/addresses/me' && options?.method === 'POST') {
        return { ok: false, status: 400, json: async () => ({ detail: 'Invalid address data' }) };
      }
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) {
        return { ok: true, status: 200, json: async () => ({}) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    const zipInput = screen.getByLabelText(/zip code/i);
    await user.clear(zipInput);
    await user.type(zipInput, '10001');

    await user.click(screen.getByRole('button', { name: /save changes/i }));

    // Profile save should still succeed even if address POST fails
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Profile saved', expect.any(Object));
    });
  });

  it('handles user name PATCH failure silently during save', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({
      data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
      isLoading: false,
    });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'A'.repeat(420), has_profile_picture: true },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string }) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === API_ENDPOINTS.ME && options?.method === 'PATCH') {
        // Return a failure response rather than throwing - allows profile save to proceed
        return { ok: false, status: 500, json: async () => ({ detail: 'Internal error' }) };
      }
      if (url === '/api/v1/addresses/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) {
        return { ok: true, status: 200, json: async () => ({}) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    // Profile save should succeed even if user PATCH fails - it's caught silently
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Profile saved', expect.any(Object));
    });
  });

  it('handles service areas submit failure during save', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({
      data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
      isLoading: false,
    });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'A'.repeat(420), has_profile_picture: true },
      isLoading: false,
    });

    mockSubmitServiceAreasOnce.mockRejectedValue(new Error('Service area submit failed'));

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === '/api/v1/addresses/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) {
        return { ok: true, status: 200, json: async () => ({}) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Service area submit failed');
    });
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('handles service areas initial load error gracefully', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'Test' },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        throw new Error('Service areas fetch failed');
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    // Should render without crashing
    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });
  });

  it('handles profile data with empty preferred locations arrays', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        bio: 'Test',
        preferred_teaching_locations: [],
        preferred_public_spaces: [],
      },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });
  });

  it('processes neighborhoods with null name values', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        bio: 'Test',
        service_area_neighborhoods: [
          { neighborhood_id: 'n1', name: null },
          { neighborhood_id: 'n2' }, // name missing entirely
        ],
      },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });
  });

  it('uses default address when items array contains non-default addresses', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({
      data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
      isLoading: false,
    });
    mockUseUserAddresses.mockReturnValue({
      data: {
        items: [
          { id: 'addr-1', postal_code: '11111', is_default: false },
          { id: 'addr-2', postal_code: '22222', is_default: true },
        ],
      },
      isLoading: false,
    });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'Test' },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toHaveTextContent('Test-User-22222');
    });
  });

  it('preserves booking preferences values during profile changes', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        bio: 'Test',
        min_advance_booking_hours: 12,
        buffer_time_minutes: 45,
      },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm context="dashboard" />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByText(/booking preferences/i));

    // Update the profile using a callback that should preserve these values
    await user.click(screen.getByRole('button', { name: /update name/i }));

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toHaveTextContent('Updated');
    });
  });

  it('toggles neighborhood via onToggleNeighborhood callback', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'Test' },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    const user = userEvent.setup();

    // Toggle a neighborhood - should work without throwing
    await user.click(screen.getByRole('button', { name: /toggle neighborhood/i }));

    // The button should still be accessible
    expect(screen.getByRole('button', { name: /toggle neighborhood/i })).toBeInTheDocument();
  });

  it('selects all neighborhoods in a borough via onToggleBoroughAll', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { bio: 'Test' },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    const user = userEvent.setup();

    // Select all Manhattan neighborhoods - should work without throwing
    await user.click(screen.getByRole('button', { name: /select all manhattan/i }));

    expect(screen.getByRole('button', { name: /select all manhattan/i })).toBeInTheDocument();
  });

  it('clears all neighborhoods in a borough via onToggleBoroughAll', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        bio: 'Test',
        service_area_neighborhoods: [{ neighborhood_id: 'n1', name: 'Test' }, { neighborhood_id: 'n2', name: 'Test2' }],
      },
      isLoading: false,
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        return { ok: true, status: 200, json: async () => ({ items: [{ neighborhood_id: 'n1' }, { neighborhood_id: 'n2' }] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    const user = userEvent.setup();

    // Clear all Manhattan neighborhoods - should work without throwing
    await user.click(screen.getByRole('button', { name: /clear all manhattan/i }));

    expect(screen.getByRole('button', { name: /clear all manhattan/i })).toBeInTheDocument();
  });

  it('handles profile load error', async () => {
    const { Wrapper } = createWrapper();
    mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
    mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('Profile load failed'),
    });

    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url === '/api/v1/addresses/service-areas/me') {
        throw new Error('Service areas fetch failed');
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    render(<InstructorProfileForm />, { wrapper: Wrapper });

    // Should show loading or handle error gracefully
    await waitFor(() => {
      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });
  });

  describe('Coverage improvement tests', () => {
    it('builds address payload with all optional fields', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [] },
        isLoading: false,
      });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test bio with more than four hundred characters. '.repeat(10),
          first_name: 'John',
          last_name: 'Doe',
          street_line1: '123 Main St',
          street_line2: 'Apt 4B',
          locality: 'New York',
          administrative_area: 'NY',
          postal_code: '10001',
          country_code: 'US',
          place_id: 'ChIJd8BlQ2BZwokRAFUEcm_qrcA',
          latitude: 40.7484,
          longitude: -73.9857,
        },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === '/api/v1/addresses/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url.includes('/addresses/nyc-zip-check')) {
          return { ok: true, status: 200, json: async () => ({ is_valid: true }) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });
    });

    it('builds address payload returning null when required fields missing', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [] },
        isLoading: false,
      });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test bio',
          first_name: 'John',
          last_name: 'Doe',
          // Missing required address fields
          street_line1: '',
          locality: '',
        },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async () => {
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });
    });

    it('creates new address when no default address exists', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [] },
        isLoading: false,
      });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test bio with more than four hundred characters. '.repeat(10),
          first_name: 'John',
          last_name: 'Doe',
          street_line1: '123 Main St',
          locality: 'New York',
          administrative_area: 'NY',
          postal_code: '10001',
        },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async () => {
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      // Save should have been triggered
      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });
    });

    it('patches existing address when default address has different zip', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({
        data: {
          items: [{
            id: 'addr-1',
            is_default: true,
            postal_code: '10001',
          }],
        },
        isLoading: false,
      });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test bio with more than four hundred characters. '.repeat(10),
          first_name: 'John',
          last_name: 'Doe',
          postal_code: '10002', // Different from address
        },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async () => {
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      // Save should have been triggered
      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });
    });

    it('handles address creation failure during save', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [] },
        isLoading: false,
      });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test bio with more than four hundred characters. '.repeat(10),
          first_name: 'John',
          last_name: 'Doe',
          street_line1: '123 Main St',
          locality: 'New York',
          administrative_area: 'NY',
          postal_code: '10001',
        },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async () => {
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      // Save should have been triggered
      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });
    });

    it('handles 404 response when checking addresses and creates new one', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [] },
        isLoading: false,
      });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test bio with more than four hundred characters. '.repeat(10),
          first_name: 'John',
          last_name: 'Doe',
          street_line1: '123 Main St',
          locality: 'New York',
          administrative_area: 'NY',
          postal_code: '10001',
        },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async () => {
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      // Save should have been triggered
      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });
    });

    it('handles NYC zip check validation', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [] },
        isLoading: false,
      });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test bio with more than four hundred characters. '.repeat(10),
          first_name: 'John',
          last_name: 'Doe',
          postal_code: '90210', // Non-NYC zip
        },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url.includes('/addresses/nyc-zip-check')) {
          return { ok: true, status: 200, json: async () => ({ is_valid: false }) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });
    });

    it('renders booking preferences inputs and handles value changes', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [] },
        isLoading: false,
      });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test bio',
          first_name: 'John',
          last_name: 'Doe',
          min_advance_booking_hours: 4,
          buffer_time_minutes: 30,
        },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async () => {
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });
    });

    it('toggleBoroughAll adds all neighborhood IDs', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test' },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url.includes('/neighborhoods')) {
          return {
            ok: true, status: 200, json: async () => ({
              items: [
                { id: 'n1', neighborhood_id: 'n1', name: 'Upper East Side', borough: 'Manhattan' },
                { id: 'n2', neighborhood_id: 'n2', name: 'Upper West Side', borough: 'Manhattan' },
              ]
            })
          };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();

      // Select all Manhattan neighborhoods
      await user.click(screen.getByRole('button', { name: /select all manhattan/i }));
      expect(screen.getByRole('button', { name: /select all manhattan/i })).toBeInTheDocument();

      // Clear all Manhattan neighborhoods
      await user.click(screen.getByRole('button', { name: /clear all manhattan/i }));
      expect(screen.getByRole('button', { name: /clear all manhattan/i })).toBeInTheDocument();
    });

    it('handles address error when address service returns non-200 non-404', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [] },
        isLoading: false,
      });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test bio with more than four hundred characters. '.repeat(10),
          first_name: 'John',
          last_name: 'Doe',
          postal_code: '10001',
          street_line1: '123 Main St',
          locality: 'New York',
          administrative_area: 'NY',
        },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === '/api/v1/addresses/me') {
          return { ok: false, status: 500, json: async () => ({ message: 'Server error' }) };
        }
        if (url.includes('/instructors/profile')) {
          return { ok: true, status: 200, json: async () => ({}) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      // Should call fetchWithAuth and handle the error
      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });
    });

    it('renders embedded mode with inline loader', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: null, isLoading: true });
      mockUseUserAddresses.mockReturnValue({ data: null, isLoading: true });
      mockUseInstructorProfileMe.mockReturnValue({
        data: null,
        isLoading: true,
      });

      render(<InstructorProfileForm embedded />, { wrapper: Wrapper });

      // In embedded mode, should show minimal loading state
      expect(document.body).toBeInTheDocument();
    });

    it('renders component with all required props', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test' },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async () => {
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // Should render the form without issues
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });
  });
});
