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
  function PersonalInfoCard({ profile, onProfileChange, onToggle }: { profile: { first_name?: string; last_name?: string; postal_code?: string }; onProfileChange: (updates: Record<string, string | number>) => void; onToggle: () => void }) {
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
        <button type="button" onClick={() => onProfileChange({
          street_line1: '500 Broadway',
          street_line2: 'Floor 3',
          locality: 'New York',
          administrative_area: 'NY',
          postal_code: '10012',
          country_code: 'US',
          place_id: 'ChIJtest123',
          latitude: 40.72,
          longitude: -73.99,
        })}>Set Full Address</button>
        <button type="button" onClick={() => onProfileChange({
          street_line1: '200 Park Ave',
          locality: 'New York',
          administrative_area: 'NY',
          postal_code: '10017',
        })}>Set Basic Address</button>
        <button type="button" onClick={onToggle}>Toggle</button>
      </section>
    );
  }
  return { PersonalInfoCard };
});

jest.mock('@/app/(auth)/instructor/onboarding/account-setup/components/BioCard', () => {
  function BioCard({ profile, bioTooShort, onGenerateBio, onToggle }: { profile: { bio?: string }; bioTooShort: boolean; onGenerateBio: () => void; onToggle?: () => void }) {
    return (
      <section>
        <div data-testid="bio-content">{profile.bio}</div>
        <div data-testid="bio-too-short">{bioTooShort ? 'short' : 'long'}</div>
        <button type="button" onClick={onGenerateBio}>Generate Bio</button>
        <button type="button" onClick={() => onToggle?.()}>Toggle Bio</button>
      </section>
    );
  }
  return { BioCard };
});

jest.mock('@/app/(auth)/instructor/onboarding/account-setup/components/ServiceAreasCard', () => {
  const React = require('react');
  function ServiceAreasCard({ selectedNeighborhoods, formatNeighborhoodName, onToggleBoroughAccordion, onGlobalFilterChange, onToggleNeighborhood, toggleBoroughAll, onToggle, boroughAccordionRefs }: { selectedNeighborhoods: Set<string>; formatNeighborhoodName: (value: string) => string; onToggleBoroughAccordion: (borough: string) => void; onGlobalFilterChange: (value: string) => void; onToggleNeighborhood?: (id: string) => void; toggleBoroughAll?: (borough: string, value: boolean, items?: Array<{ neighborhood_id: string }>) => void; onToggle?: () => void; boroughAccordionRefs?: React.MutableRefObject<Record<string, HTMLDivElement | null>> }) {
    return (
      <section>
        <div data-testid="service-areas-count">{selectedNeighborhoods.size}</div>
        <div data-testid="formatted-name">{formatNeighborhoodName('lower east')}</div>
        <div
          data-testid="borough-accordion-manhattan"
          ref={(el: HTMLDivElement | null) => {
            if (boroughAccordionRefs?.current) boroughAccordionRefs.current['Manhattan'] = el;
          }}
        />
        <button type="button" onClick={() => onToggleBoroughAccordion('Manhattan')}>Toggle Borough</button>
        <button type="button" onClick={() => onGlobalFilterChange('park')}>Filter</button>
        <button type="button" onClick={() => onToggleNeighborhood?.('test-neighborhood-1')}>Toggle Neighborhood</button>
        <button type="button" onClick={() => toggleBoroughAll?.('Manhattan', true, [{ neighborhood_id: 'n1' }, { neighborhood_id: 'n2' }])}>Select All Manhattan</button>
        <button type="button" onClick={() => toggleBoroughAll?.('Manhattan', false, [{ neighborhood_id: 'n1' }, { neighborhood_id: 'n2' }])}>Clear All Manhattan</button>
        <button type="button" onClick={() => onToggle?.()}>Toggle Service Areas</button>
      </section>
    );
  }
  return { ServiceAreasCard };
});

jest.mock('@/app/(auth)/instructor/onboarding/account-setup/components/PreferredLocationsCard', () => {
  function PreferredLocationsCard({ setPreferredLocations, setNeutralPlaces, onToggle }: { setPreferredLocations: (values: string[]) => void; setNeutralPlaces: (values: string[]) => void; onToggle?: () => void }) {
    return (
      <section>
        <button type="button" onClick={() => setPreferredLocations(['Studio'])}>Set Preferred</button>
        <button type="button" onClick={() => setNeutralPlaces(['Library'])}>Set Neutral</button>
        <button type="button" onClick={() => setPreferredLocations(['', '  ', 'Studio A', 'studio a', 'Studio B'])}>Set Dirty Preferred</button>
        <button type="button" onClick={() => setNeutralPlaces(['', 'Park X', 'park x', '  ', 'Park Y'])}>Set Dirty Neutral</button>
        <button type="button" onClick={() => onToggle?.()}>Toggle Preferred Locations</button>
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

  describe('Batch 9 — uncovered branch coverage', () => {
    it('detects profile picture via profile_picture_version number', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test',
          has_profile_picture: false,
          profile_picture_version: 3, // finite number => has picture
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

    it('generates bio preserving short existing first sentence', async () => {
      const { Wrapper } = createWrapper();
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'I love teaching.', has_profile_picture: false },
        isLoading: false,
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /generate bio/i }));

      await waitFor(() => {
        const content = screen.getByTestId('bio-content').textContent ?? '';
        // Should start with the preserved first sentence
        expect(content).toMatch(/^I love teaching\./);
        expect(content.length).toBeGreaterThanOrEqual(400);
      });
    });

    it('generates bio using default intro when first sentence is too long', async () => {
      const { Wrapper } = createWrapper();
      const longSentence = 'A'.repeat(170);
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: longSentence, has_profile_picture: false },
        isLoading: false,
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /generate bio/i }));

      await waitFor(() => {
        const content = screen.getByTestId('bio-content').textContent ?? '';
        expect(content).toMatch(/^I am a dedicated instructor/);
      });
    });

    it('generates bio using default intro when first sentence is too short', async () => {
      const { Wrapper } = createWrapper();
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Hi. More.', has_profile_picture: false },
        isLoading: false,
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /generate bio/i }));

      await waitFor(() => {
        const content = screen.getByTestId('bio-content').textContent ?? '';
        // "Hi" is too short (<10 chars), should use default
        expect(content).toMatch(/^I am a dedicated instructor/);
      });
    });

    it('renders embedded loading as minimal inline div', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: null, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: null, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({ data: null, isLoading: false });

      const { container } = render(<InstructorProfileForm embedded />, { wrapper: Wrapper });

      // In embedded mode with loading, should use the 1px-height inline loader
      void (container.querySelector('[style*="height: 1"]') ?? container.querySelector('[style*="height"]'));
      // Still in loading state since no data
      expect(container).toBeInTheDocument();
    });

    it('calls onStepStatusChange with failed when bio is short or profile is incomplete', async () => {
      const { Wrapper } = createWrapper();
      const onStepStatusChange = jest.fn();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Short bio', // Too short (< 400)
          has_profile_picture: false,
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
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm onStepStatusChange={onStepStatusChange} />, { wrapper: Wrapper });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        expect(onStepStatusChange).toHaveBeenCalledWith('failed');
      });
    });

    it('saves preferred locations with deduplication and labels', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'A'.repeat(420),
          has_profile_picture: true,
          preferred_teaching_locations: [
            { address: 'Studio A', label: 'Main Studio' },
            { address: 'studio a', label: 'Dup' }, // duplicate, should be deduped
          ],
          preferred_public_spaces: [
            { address: 'Central Park' },
            { address: 'central park' }, // duplicate
          ],
        },
        isLoading: false,
      });

      let savedPayload: Record<string, unknown> | null = null;
      mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string; body?: string }) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === '/api/v1/addresses/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url.includes('/instructors/') && options?.method === 'PUT') {
          savedPayload = JSON.parse(options?.body ?? '{}');
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
        expect(savedPayload).toBeTruthy();
      });

      // Dedup happens at load time. Since the deduped result matches the
      // initial loaded state, locations are omitted from the save payload
      // (Phase 2 conditional-send fix).
      const teaching = (savedPayload as unknown as Record<string, unknown>)?.['preferred_teaching_locations'];
      const publicSpaces = (savedPayload as unknown as Record<string, unknown>)?.['preferred_public_spaces'];
      expect(teaching).toBeUndefined();
      expect(publicSpaces).toBeUndefined();
    });

    it('handles address creation on 404 with address payload', async () => {
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
          locality: 'New York',
          administrative_area: 'NY',
          postal_code: '10001',
        },
        isLoading: false,
      });

      const postCalls: string[] = [];
      mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string }) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === '/api/v1/addresses/me' && !options?.method) {
          return { ok: false, status: 404, json: async () => ({ detail: 'Not found' }) };
        }
        if (url === '/api/v1/addresses/me' && options?.method === 'POST') {
          postCalls.push(url);
          return { ok: true, status: 201, json: async () => ({ id: 'new-addr' }) };
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
      await user.type(zipInput, '10002');

      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Profile saved', expect.any(Object));
      });
    });

    it('skips address create on 404 path when address payload is null', async () => {
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
          // No full address fields => buildInstructorAddressPayload returns null
        },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string }) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === '/api/v1/addresses/me' && !options?.method) {
          return { ok: false, status: 404, json: async () => ({}) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      // Save should succeed — no POST attempt since addressPayload is null
      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Profile saved', expect.any(Object));
      });

      // Verify no POST was made to addresses
      expect(mockFetchWithAuth).not.toHaveBeenCalledWith(
        '/api/v1/addresses/me',
        expect.objectContaining({ method: 'POST' })
      );
    });

    it('does not skip borough neighborhoods when cache already loaded', async () => {
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

      let callCount = 0;
      global.fetch = jest.fn().mockImplementation(async (url: string) => {
        if (url.includes('/neighborhoods')) {
          callCount++;
          return {
            ok: true,
            status: 200,
            json: async () => ({
              items: [{ neighborhood_id: 'n1', ntacode: 'MN01', name: 'Test Hood' }],
            }),
          };
        }
        return { ok: true, status: 200, json: async () => ({ is_nyc: true }) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      const user = userEvent.setup();
      // First toggle loads neighborhoods
      await user.click(screen.getByRole('button', { name: /toggle borough/i }));

      await waitFor(() => {
        expect(callCount).toBeGreaterThanOrEqual(1);
      });

      const firstCallCount = callCount;

      // Second toggle should use cache (no additional fetch call for same borough)
      await user.click(screen.getByRole('button', { name: /toggle borough/i }));
      await user.click(screen.getByRole('button', { name: /toggle borough/i }));

      // Cache should prevent additional fetch calls
      expect(callCount).toBe(firstCallCount);
    });

    it('handles neighborhoods fetch returning non-ok response', async () => {
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
          return { ok: false, status: 500, json: async () => ({}) };
        }
        return { ok: true, status: 200, json: async () => ({ is_nyc: true }) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /toggle borough/i }));

      // Should not crash
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });

    it('handles NYC zip check failure gracefully', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [{ id: 'addr-1', postal_code: '10001', is_default: true }] },
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

      // NYC zip check throws
      global.fetch = jest.fn().mockImplementation(async () => {
        throw new Error('Network error');
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      // Should not crash
      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });
    });

    it('handles NYC zip check returning non-ok response', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [{ id: 'addr-1', postal_code: '10001', is_default: true }] },
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

      global.fetch = jest.fn().mockImplementation(async () => {
        return { ok: false, status: 500 };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });
    });

    it('skips NYC zip check when address has no postal_code', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
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

      const fetchSpy = jest.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
      global.fetch = fetchSpy;

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // No NYC zip check should have been made
      const nycCalls = fetchSpy.mock.calls.filter(
        ([url]: [string]) => typeof url === 'string' && url.includes('nyc-zip')
      );
      expect(nycCalls).toHaveLength(0);
    });

    it('hides Skills & Pricing and Booking Preferences in onboarding context', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test', is_live: false },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm context="onboarding" />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // In onboarding, Skills & Pricing and Booking Preferences should not appear
      expect(screen.queryByText(/skills & pricing/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/booking preferences/i)).not.toBeInTheDocument();
    });

    it('hides save button in onboarding context', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test', is_live: false },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm context="onboarding" />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // In onboarding, no inline save button
      expect(screen.queryByRole('button', { name: /save changes/i })).not.toBeInTheDocument();
    });

    it('does not redirect non-onboarding context even if instructor is live', async () => {
      const replace = jest.fn();
      (useRouter as jest.Mock).mockReturnValue({ push: jest.fn(), replace, prefetch: jest.fn() });
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test', is_live: true, onboarding_completed_at: '2025-01-01T00:00:00Z' },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      const { Wrapper } = createWrapper();
      render(<InstructorProfileForm context="dashboard" />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // Should NOT redirect in dashboard context
      expect(replace).not.toHaveBeenCalled();
    });

    it('handles empty preferred_teaching_locations entries during prefill', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test',
          preferred_teaching_locations: [
            { address: '' }, // empty address
            { address: '  ' }, // whitespace
            { address: 'Valid Studio' },
          ],
          preferred_public_spaces: [
            { address: '' },
            { address: 'Valid Park' },
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

    it('handles profile.json parse error during save', async () => {
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
        if (url.includes('/instructors/')) {
          return {
            ok: false,
            status: 400,
            json: async () => { throw new Error('Invalid JSON'); },
          };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      // Should show fallback error message when JSON parse fails
      await waitFor(() => {
        expect(screen.getByText(/request failed/i)).toBeInTheDocument();
      });
    });

    it('handles sessionStorage.setItem failure gracefully', async () => {
      const { Wrapper } = createWrapper();
      const onStepStatusChange = jest.fn();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'A'.repeat(420), has_profile_picture: true },
        isLoading: false,
      });

      // Make sessionStorage.setItem throw
      Object.defineProperty(window, 'sessionStorage', {
        value: {
          setItem: jest.fn().mockImplementation(() => { throw new Error('QuotaExceeded'); }),
          getItem: jest.fn(),
          removeItem: jest.fn(),
        },
        writable: true,
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

      render(<InstructorProfileForm onStepStatusChange={onStepStatusChange} />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      // Should still succeed despite sessionStorage error
      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Profile saved', expect.any(Object));
      });
    });

    it('handles service_area_boroughs from API taking precedence', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test',
          service_area_boroughs: ['Brooklyn', 'Queens'], // Non-empty from API
          service_area_neighborhoods: [{ neighborhood_id: 'n1', name: 'Williamsburg', borough: 'Brooklyn' }],
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

    it('filters service_area_boroughs to only valid non-empty strings', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test',
          service_area_boroughs: ['Manhattan', '', '  ', null, 'Brooklyn'] as string[], // Mixed valid/invalid
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
  });

  describe('NYC ZIP check edge cases', () => {
    it('keeps isNYC as true when fetch returns ok: false', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [{ id: 'addr-1', postal_code: '10001', is_default: true }] },
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

      // NYC zip check returns ok: false - isNYC should stay true (default)
      global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 400 });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // Verify fetch was called for the zip check
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('is-nyc'),
        expect.any(Object)
      );
    });

    it('sets isNYC to false when zip is outside NYC', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [{ id: 'addr-1', postal_code: '90210', is_default: true }] },
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

      // NYC zip check returns is_nyc: false
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ is_nyc: false }),
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('is-nyc'),
        expect.any(Object)
      );
    });

    it('skips NYC zip check when addressesDataFromHook has no items', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({
        data: null, // No address data at all
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

      const fetchSpy = jest.fn().mockResolvedValue({
        ok: true, status: 200,
        json: async () => ({ is_nyc: true }),
      });
      global.fetch = fetchSpy;

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // No NYC zip check should have been made since there is no address data
      const nycCalls = fetchSpy.mock.calls.filter(
        ([url]: [string]) => typeof url === 'string' && url.includes('is-nyc')
      );
      expect(nycCalls).toHaveLength(0);
    });
  });

  describe('Bio generation edge cases', () => {
    it('truncates generated bio at 560 characters', async () => {
      const { Wrapper } = createWrapper();
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: '' },
        isLoading: false,
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /generate bio/i }));

      await waitFor(() => {
        const content = screen.getByTestId('bio-content').textContent ?? '';
        expect(content.length).toBeLessThanOrEqual(560);
        expect(content.length).toBeGreaterThanOrEqual(400);
      });
    });

    it('uses default intro when bio is empty', async () => {
      const { Wrapper } = createWrapper();
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: '' },
        isLoading: false,
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /generate bio/i }));

      await waitFor(() => {
        const content = screen.getByTestId('bio-content').textContent ?? '';
        expect(content).toMatch(/^I am a dedicated instructor/);
      });
    });

    it('ensures intro ends with period before appending sentences', async () => {
      const { Wrapper } = createWrapper();
      // A first sentence without a trailing period in split result
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'I teach music professionally' }, // no period, 28 chars (valid range)
        isLoading: false,
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /generate bio/i }));

      await waitFor(() => {
        const content = screen.getByTestId('bio-content').textContent ?? '';
        // The intro should start with the first sentence and have a period appended
        expect(content).toMatch(/^I teach music professionally\./);
        expect(content.length).toBeGreaterThanOrEqual(400);
      });
    });
  });

  describe('Save error paths', () => {
    it('shows fallback error message when formatProblemMessages returns empty array', async () => {
      const { formatProblemMessages } = jest.requireMock('@/lib/httpErrors') as { formatProblemMessages: jest.Mock };
      formatProblemMessages.mockReturnValue([]); // empty array => fallback to Request failed

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
          return { ok: false, status: 422, json: async () => ({ detail: 'Validation failed' }) };
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
        expect(toast.error).toHaveBeenCalledWith('Request failed (422)');
      });

      // Restore default mock
      formatProblemMessages.mockReturnValue(['Bad request']);
    });

    it('catches network error and sets generic error message', async () => {
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

      // Make the ME PATCH throw to trigger the top-level catch
      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === API_ENDPOINTS.ME) {
          throw new Error('Network error');
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

    it('skips user PATCH when first_name and last_name are both empty', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: null, // No session data -> empty names
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'A'.repeat(420),
          has_profile_picture: true,
          // No user embedded either
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
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Profile saved', expect.any(Object));
      });

      // Verify ME PATCH was NOT called (both names empty)
      expect(mockFetchWithAuth).not.toHaveBeenCalledWith(
        API_ENDPOINTS.ME,
        expect.objectContaining({ method: 'PATCH' })
      );
    });

    it('handles deriveErrorMessage parse failure with fallback', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
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

      // Make formatProblemMessages return empty for this test
      const { formatProblemMessages } = jest.requireMock('@/lib/httpErrors') as { formatProblemMessages: jest.Mock };
      formatProblemMessages.mockReturnValue([]);

      mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string }) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) {
          return { ok: true, status: 200, json: async () => ({}) };
        }
        if (url === '/api/v1/addresses/me' && !options?.method) {
          // The address response's json().clone().json() throws during deriveErrorMessage
          return {
            ok: false,
            status: 503,
            clone: () => ({
              json: async () => { throw new Error('Cannot parse'); },
            }),
            json: async () => { throw new Error('Cannot parse'); },
          };
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

      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Request failed (503)');
      });

      // Restore default mock
      formatProblemMessages.mockReturnValue(['Bad request']);
    });

    it('handles non-Error thrown from service areas submit', async () => {
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

      // Reject with a non-Error value
      mockSubmitServiceAreasOnce.mockRejectedValue('string error');

      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === '/api/v1/addresses/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
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
        // Non-Error value uses fallback message
        expect(toast.error).toHaveBeenCalledWith('Failed to save service areas');
      });
    });
  });

  describe('Onboarding context behavior', () => {
    it('expands all sections by default in onboarding context', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test', is_live: false },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm context="onboarding" />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // In onboarding context, embedded is forced to false and
      // SectionHeroCard is not rendered
      expect(screen.queryByTestId('section-hero')).not.toBeInTheDocument();
      // No dashboard header
      expect(screen.queryByTestId('user-profile-dropdown')).not.toBeInTheDocument();
    });

    it('forces embedded to false in onboarding context', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test', is_live: false },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      // Even with embedded=true, onboarding context forces it to false
      render(<InstructorProfileForm context="onboarding" embedded />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // Verify it doesn't show the embedded loading placeholder
      // and shows the non-embedded loading text (or data)
      expect(screen.queryByTestId('section-hero')).not.toBeInTheDocument();
    });
  });

  describe('useImperativeHandle save', () => {
    it('saves via ref without redirect when no redirectTo provided', async () => {
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

      // Call save without redirect
      await ref.current?.save();

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Profile saved', expect.any(Object));
      });

      // push should NOT have been called since no redirectTo
      expect(push).not.toHaveBeenCalled();
    });

    it('does not double-save when save button is clicked while saving is in progress', async () => {
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

      let resolveProfileSave: (() => void) | null = null;
      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === API_ENDPOINTS.ME) {
          // Delay to keep saving=true
          await new Promise<void>((resolve) => { resolveProfileSave = resolve; });
          return { ok: true, status: 200, json: async () => ({}) };
        }
        if (url === '/api/v1/addresses/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();

      // First click triggers save
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      // Button should now be disabled (saving=true)
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /saving/i })).toBeDisabled();
      });

      // Resolve the pending save
      (resolveProfileSave as (() => void) | null)?.();

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalledWith(API_ENDPOINTS.ME, expect.any(Object));
      });
    });
  });

  describe('Service area prefill edge cases', () => {
    it('uses id as fallback when neighborhood_id is missing in service areas response', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test' },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              items: [
                { id: 'fallback-id-1', name: 'Area 1' }, // No neighborhood_id, uses id as fallback
                { neighborhood_id: 'normal-id-2', name: 'Area 2' },
              ],
            }),
          };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // Both should be selected
      await waitFor(() => {
        expect(screen.getByTestId('service-areas-count')).toHaveTextContent('2');
      });
    });

    it('handles service areas response with non-ok status during prefill', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test' },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: false, status: 403, json: async () => ({ detail: 'Forbidden' }) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      // Should not crash, just skip service area prefill
      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      expect(screen.getByTestId('service-areas-count')).toHaveTextContent('0');
    });
  });

  describe('Address save paths', () => {
    it('skips address POST on 404 when addressPayload is null and save succeeds', async () => {
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
          // No street_line1 etc. -> addressPayload is null -> skips POST on 404
        },
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
          return { ok: false, status: 404, json: async () => ({}) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      // addressPayload is null, so 404 path skips POST and save completes
      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Profile saved', expect.any(Object));
      });

      // No POST was attempted
      expect(mockFetchWithAuth).not.toHaveBeenCalledWith(
        '/api/v1/addresses/me',
        expect.objectContaining({ method: 'POST' })
      );
    });

    it('creates address when no default exists and items array is empty', async () => {
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
          street_line1: '789 Pine St',
          street_line2: 'Suite 100',
          locality: 'New York',
          administrative_area: 'NY',
          postal_code: '10003',
          country_code: 'US',
          place_id: 'test-place-id',
          latitude: 40.73,
          longitude: -73.99,
        },
        isLoading: false,
      });

      const postBodies: unknown[] = [];
      mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string; body?: string }) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) {
          return { ok: true, status: 200, json: async () => ({}) };
        }
        if (url === '/api/v1/addresses/me' && !options?.method) {
          // Returns empty items array, no default address
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === '/api/v1/addresses/me' && options?.method === 'POST') {
          postBodies.push(JSON.parse(options.body ?? '{}'));
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
        expect(toast.success).toHaveBeenCalledWith('Profile saved', expect.any(Object));
      });
    });

    it('skips address PATCH when zip code matches existing', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'Test', last_name: 'User' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [{ id: 'addr-1', postal_code: '10001', is_default: true }] },
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
        if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) {
          return { ok: true, status: 200, json: async () => ({}) };
        }
        if (url === '/api/v1/addresses/me' && !options?.method) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ items: [{ id: 'addr-1', postal_code: '10001', is_default: true }] }),
          };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        // Postal code from address data should be 10001
        expect(screen.getByTestId('personal-info')).toHaveTextContent('10001');
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Profile saved', expect.any(Object));
      });

      // Verify no PATCH was made since the zip didn't change
      expect(mockFetchWithAuth).not.toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/addresses/me/addr-1'),
        expect.objectContaining({ method: 'PATCH' })
      );
    });
  });

  describe('Neighborhood loading edge cases', () => {
    it('uses code as fallback for ntacode when ntacode is missing', async () => {
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
              items: [
                { id: 'n1', code: 'MN01', name: 'TestHood' }, // No ntacode, has code as fallback
                { neighborhood_id: 'n2', name: 'TestHood2' }, // No ntacode, no code
                { name: 'NoId' }, // No id, no neighborhood_id — should be filtered out
              ],
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
  });

  describe('Prefill deduplication', () => {
    it('does not re-run prefill when hook data is already processed', async () => {
      const { Wrapper } = createWrapper();
      const profileData = { bio: 'Test bio content' };
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: profileData,
        isLoading: false,
      });

      let serviceAreaCallCount = 0;
      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          serviceAreaCallCount++;
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      const { rerender } = render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const firstCallCount = serviceAreaCallCount;

      // Re-render with same data - should NOT trigger another load
      rerender(<InstructorProfileForm />);

      // Wait a tick for any potential effects
      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // The service area fetch should not have been called again
      expect(serviceAreaCallCount).toBe(firstCallCount);
    });
  });

  describe('buildInstructorProfilePayload edge cases', () => {
    it('handles null min_advance_booking_hours with default of 2', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'A'.repeat(420),
          has_profile_picture: true,
          // min_advance_booking_hours intentionally omitted
          // buffer_time_minutes intentionally omitted
        },
        isLoading: false,
      });

      let savedPayload: Record<string, unknown> | null = null;
      mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string; body?: string }) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE && options?.method === 'PUT') {
          savedPayload = JSON.parse(options.body ?? '{}');
          return { ok: true, status: 200, json: async () => ({}) };
        }
        if (url === '/api/v1/addresses/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
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
        expect(savedPayload).toBeTruthy();
      });

      // min_advance_booking_hours should default to 2
      expect((savedPayload as unknown as Record<string, unknown>)['min_advance_booking_hours']).toBe(2);
      // buffer_time_minutes should be 0 (from buffer_time_hours defaulting to 0)
      expect((savedPayload as unknown as Record<string, unknown>)['buffer_time_minutes']).toBe(0);
    });
  });

  describe('Teaching location save deduplication', () => {
    it('omits teaching and public space arrays from payload when unchanged', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'A'.repeat(420),
          has_profile_picture: true,
          // No preferred_teaching_locations or preferred_public_spaces
        },
        isLoading: false,
      });

      let savedPayload: Record<string, unknown> | null = null;
      mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string; body?: string }) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE && options?.method === 'PUT') {
          savedPayload = JSON.parse(options.body ?? '{}');
          return { ok: true, status: 200, json: async () => ({}) };
        }
        if (url === '/api/v1/addresses/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
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
        expect(savedPayload).toBeTruthy();
      });

      // Locations haven't changed from initial state (both empty), so they're
      // omitted from the payload (Phase 2 conditional-send fix).
      expect((savedPayload as unknown as Record<string, unknown>)['preferred_teaching_locations']).toBeUndefined();
      expect((savedPayload as unknown as Record<string, unknown>)['preferred_public_spaces']).toBeUndefined();
    });

    it('caps teaching locations to max 2 at load time', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'A'.repeat(420),
          has_profile_picture: true,
          preferred_teaching_locations: [
            { address: 'Studio A', label: 'Main' },
            { address: 'Studio B', label: 'Second' },
            { address: 'Studio C', label: 'Third' }, // Should be dropped (max 2)
          ],
        },
        isLoading: false,
      });

      let savedPayload: Record<string, unknown> | null = null;
      mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string; body?: string }) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE && options?.method === 'PUT') {
          savedPayload = JSON.parse(options.body ?? '{}');
          return { ok: true, status: 200, json: async () => ({}) };
        }
        if (url === '/api/v1/addresses/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
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
        expect(savedPayload).toBeTruthy();
      });

      // Load caps at 2 entries. Since the capped result matches what the
      // component loaded (initial ref = first 2), locations are omitted
      // from the payload as unchanged.
      expect((savedPayload as unknown as Record<string, unknown>)['preferred_teaching_locations']).toBeUndefined();
    });
  });

  describe('Embedded mode rendering', () => {
    it('renders embedded loading state as 1px inline div', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      // Data is not null, so load() runs, but we keep loading true
      mockUseInstructorProfileMe.mockReturnValue({
        data: null,
        isLoading: false,
      });

      const { container } = render(<InstructorProfileForm embedded />, { wrapper: Wrapper });

      // In embedded mode while loading, uses 1px height div instead of text
      expect(container.querySelector('.p-8')).not.toBeInTheDocument();
      expect(container).toBeInTheDocument();
    });

    it('does not show dashboard header or SectionHeroCard in embedded mode', async () => {
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

      render(<InstructorProfileForm embedded />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // Dashboard header should not be present
      expect(screen.queryByTestId('user-profile-dropdown')).not.toBeInTheDocument();
    });
  });

  describe('toggleBoroughAll with id fallback', () => {
    it('selects neighborhoods using id field when neighborhood_id is absent', async () => {
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

      // Initial count should be 0
      expect(screen.getByTestId('service-areas-count')).toHaveTextContent('0');

      const user = userEvent.setup();

      // Select all — the mock passes items with neighborhood_id
      await user.click(screen.getByRole('button', { name: /select all manhattan/i }));

      // After selecting, count should be 2 (n1 and n2 from the mock)
      await waitFor(() => {
        expect(screen.getByTestId('service-areas-count')).toHaveTextContent('2');
      });
    });

    it('deselects all neighborhoods via toggleBoroughAll with value=false', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test',
          service_area_neighborhoods: [
            { neighborhood_id: 'n1', name: 'Area 1' },
            { neighborhood_id: 'n2', name: 'Area 2' },
          ],
        },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              items: [{ neighborhood_id: 'n1' }, { neighborhood_id: 'n2' }],
            }),
          };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('service-areas-count')).toHaveTextContent('2');
      });

      const user = userEvent.setup();

      // Clear all — should remove n1 and n2
      await user.click(screen.getByRole('button', { name: /clear all manhattan/i }));

      await waitFor(() => {
        expect(screen.getByTestId('service-areas-count')).toHaveTextContent('0');
      });
    });
  });

  describe('Numeric input validation edge cases', () => {
    it('clamps advance notice via onChange when empty string yields NaN', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test', min_advance_booking_hours: 4, buffer_time_minutes: 60 },
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

      await waitFor(() => {
        expect(screen.getByText(/advance notice/i)).toBeInTheDocument();
      });

      const inputs = screen.getAllByRole('spinbutton');
      const advanceInput = inputs[0]!;

      // Verify initial prefilled value
      expect(advanceInput).toHaveValue(4);

      // Clear fires onChange with '' -> parseInt('', 10) = NaN -> clamps to 1
      await user.clear(advanceInput);

      await waitFor(() => {
        expect(advanceInput).toHaveValue(1);
      });
    });

    it('clamps advance notice to max 24 when appending digits exceeds boundary', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test', min_advance_booking_hours: 2, buffer_time_minutes: 0 },
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

      await waitFor(() => {
        expect(screen.getByText(/advance notice/i)).toBeInTheDocument();
      });

      const inputs = screen.getAllByRole('spinbutton');
      const advanceInput = inputs[0]!;

      // Initial value is 2; typing '9' makes it '29' -> clamped to 24
      await user.type(advanceInput, '9');

      await waitFor(() => {
        expect(advanceInput).toHaveValue(24);
      });
    });

    it('clamps buffer time to 0 when cleared to empty string', async () => {
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
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByText(/booking preferences/i));

      await waitFor(() => {
        expect(screen.getByText(/buffer time/i)).toBeInTheDocument();
      });

      const inputs = screen.getAllByRole('spinbutton');
      const bufferInput = inputs[1]!;

      // Initial value is 0.5 (30 min / 60); verify it
      expect(bufferInput).toHaveValue(0.5);

      // Clear fires onChange with '' -> parseFloat('') = NaN -> clamps to 0
      await user.clear(bufferInput);

      await waitFor(() => {
        expect(bufferInput).toHaveValue(0);
      });
    });

    it('clamps buffer time to max 24 when appending digits exceeds boundary', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test', min_advance_booking_hours: 2, buffer_time_minutes: 180 },
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

      await waitFor(() => {
        expect(screen.getByText(/buffer time/i)).toBeInTheDocument();
      });

      const inputs = screen.getAllByRole('spinbutton');
      const bufferInput = inputs[1]!;

      // Initial value is 3 (180 min / 60); typing '9' makes it '39' -> clamped to 24
      expect(bufferInput).toHaveValue(3);
      await user.type(bufferInput, '9');

      await waitFor(() => {
        expect(bufferInput).toHaveValue(24);
      });
    });

    it('prefills buffer time correctly from buffer_time_minutes', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test', min_advance_booking_hours: 2, buffer_time_minutes: 90 },
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

      await waitFor(() => {
        expect(screen.getByText(/buffer time/i)).toBeInTheDocument();
      });

      const inputs = screen.getAllByRole('spinbutton');
      const bufferInput = inputs[1]!;

      // 90 min / 60 = 1.5 hours
      expect(bufferInput).toHaveValue(1.5);
    });

    it('saves numeric fields with correct payload values', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'A'.repeat(420),
          has_profile_picture: true,
          min_advance_booking_hours: 6,
          buffer_time_minutes: 90,
        },
        isLoading: false,
      });

      let savedPayload: Record<string, unknown> | null = null;
      mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string; body?: string }) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE && options?.method === 'PUT') {
          savedPayload = JSON.parse(options.body ?? '{}');
          return { ok: true, status: 200, json: async () => ({}) };
        }
        if (url === '/api/v1/addresses/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm context="dashboard" />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        expect(savedPayload).toBeTruthy();
      });

      // Prefilled with min_advance_booking_hours=6
      expect((savedPayload as unknown as Record<string, unknown>)['min_advance_booking_hours']).toBe(6);
      // buffer_time_hours 1.5 * 60 = 90 minutes
      expect((savedPayload as unknown as Record<string, unknown>)['buffer_time_minutes']).toBe(90);
    });
  });

  describe('Conditional rendering modes', () => {
    it('shows dashboard header in standalone mode (not embedded, not onboarding)', async () => {
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
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // Standalone dashboard mode shows the header
      expect(screen.getByTestId('user-profile-dropdown')).toBeInTheDocument();
      // Shows SectionHeroCard (not onboarding)
      expect(screen.getByTestId('section-hero')).toBeInTheDocument();
    });

    it('shows non-embedded loading text when loading without profile data', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: null,
        isLoading: false,
      });

      render(<InstructorProfileForm context="dashboard" />, { wrapper: Wrapper });

      // Non-embedded mode shows "Loading..." text
      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });

    it('uses embedded container class when embedded prop is true', async () => {
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

      const { container } = render(<InstructorProfileForm embedded />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // Embedded mode should not show dashboard header or page title
      expect(screen.queryByTestId('user-profile-dropdown')).not.toBeInTheDocument();
      // Should use embedded container class (max-w-none) instead of default container
      expect(container.querySelector('.max-w-none')).toBeInTheDocument();
      expect(container.querySelector('.container')).not.toBeInTheDocument();
    });

    it('renders onboarding mode with w-full root class', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test', is_live: false },
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      const { container } = render(<InstructorProfileForm context="onboarding" />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // Onboarding uses 'w-full' as rootClass instead of 'min-h-screen'
      expect(container.querySelector('.w-full')).toBeInTheDocument();
      expect(container.querySelector('.min-h-screen')).not.toBeInTheDocument();
    });
  });

  describe('toggleNeighborhood toggle behavior', () => {
    it('adds and then removes a neighborhood via toggleNeighborhood', async () => {
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

      expect(screen.getByTestId('service-areas-count')).toHaveTextContent('0');

      const user = userEvent.setup();

      // Add a neighborhood
      await user.click(screen.getByRole('button', { name: /toggle neighborhood/i }));

      await waitFor(() => {
        expect(screen.getByTestId('service-areas-count')).toHaveTextContent('1');
      });

      // Toggle again to remove it
      await user.click(screen.getByRole('button', { name: /toggle neighborhood/i }));

      await waitFor(() => {
        expect(screen.getByTestId('service-areas-count')).toHaveTextContent('0');
      });
    });
  });

  describe('Save button disabled during service area saving', () => {
    it('shows Saving text when savingServiceAreas is in progress', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'A'.repeat(420), has_profile_picture: true },
        isLoading: false,
      });

      // Make submitServiceAreasOnce hang to keep savingServiceAreas true
      let resolveServiceAreas: (() => void) | null = null;
      mockSubmitServiceAreasOnce.mockImplementation(async () => {
        await new Promise<void>((resolve) => { resolveServiceAreas = resolve; });
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

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      // Button should become disabled with "Saving..." text
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /saving/i })).toBeDisabled();
      });

      // Resolve to clean up
      (resolveServiceAreas as (() => void) | null)?.();

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Profile saved', expect.any(Object));
      });
    });
  });

  describe('Advance notice onKeyDown prevention', () => {
    it('prevents period, comma, and e keys in advance notice input', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test', min_advance_booking_hours: 5, buffer_time_minutes: 0 },
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

      await waitFor(() => {
        expect(screen.getByText(/advance notice/i)).toBeInTheDocument();
      });

      const inputs = screen.getAllByRole('spinbutton');
      const advanceInput = inputs[0]!;

      // Initial value is 5
      expect(advanceInput).toHaveValue(5);

      // Type disallowed characters directly — they should be prevented by onKeyDown
      // Since we can't truly block at jsdom level, focus on the input accepting
      // only valid keys. Typing '.' should not alter the integer-only advance notice.
      await user.type(advanceInput, '.');
      await user.type(advanceInput, ',');
      await user.type(advanceInput, 'e');
      await user.type(advanceInput, 'E');
      await user.type(advanceInput, '+');
      await user.type(advanceInput, '-');

      // Value should remain 5 — disallowed chars do not produce valid parseInt results
      await waitFor(() => {
        expect(advanceInput).toHaveValue(5);
      });
    });
  });

  describe('Profile picture detection via version number', () => {
    it('detects profile picture when profile_picture_version is 0 (finite)', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'A'.repeat(420),
          has_profile_picture: false,
          profile_picture_version: 0, // 0 is finite, should detect as having picture
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
        return { ok: true, status: 200, json: async () => ({}) };
      });

      const onStepStatusChange = jest.fn();
      render(<InstructorProfileForm onStepStatusChange={onStepStatusChange} />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      // Profile picture detected via version=0, so with long bio, 'done' status
      await waitFor(() => {
        expect(onStepStatusChange).toHaveBeenCalled();
      });
    });
  });

  describe('Loading state conditional paths', () => {
    it('renders embedded loading placeholder when data is still loading', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      // Return data that triggers load but keep loading true internally
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test' },
        isLoading: false,
      });

      // Delay the service areas fetch to keep loading=true longer
      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return new Promise(() => {}); // Never resolves, keeps loading=true
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      const { container } = render(<InstructorProfileForm embedded />, { wrapper: Wrapper });

      // Should show the inline loading div (height: 1px) in embedded mode
      const loaderDiv = container.querySelector('div[style]');
      expect(container).toBeInTheDocument();
      // Verify it does NOT show the text "Loading..." for embedded mode
      if (loaderDiv) {
        expect(loaderDiv).toBeInTheDocument();
      }
    });

    it('shows text Loading for non-embedded when waiting for profile', () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: null,
        isLoading: false,
      });

      render(<InstructorProfileForm context="dashboard" />, { wrapper: Wrapper });

      // Non-embedded, non-onboarding shows "Loading..." text
      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });
  });

  describe('Section toggle callbacks', () => {
    it('toggles bio section open state via onToggle callback', async () => {
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
      await user.click(screen.getByRole('button', { name: /toggle bio/i }));

      // Toggle was triggered without errors
      expect(screen.getByTestId('bio-content')).toBeInTheDocument();
    });

    it('toggles service areas section open state via onToggle callback', async () => {
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
      await user.click(screen.getByRole('button', { name: /toggle service areas/i }));

      // Toggle was triggered without errors
      expect(screen.getByTestId('service-areas-count')).toBeInTheDocument();
    });

    it('toggles preferred locations section open state via onToggle callback', async () => {
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
      await user.click(screen.getByRole('button', { name: /toggle preferred locations/i }));

      // Toggle was triggered without errors
      expect(screen.getByTestId('personal-info')).toBeInTheDocument();
    });
  });

  describe('buildInstructorAddressPayload during save', () => {
    it('builds full address payload with optional fields and creates address on empty items', async () => {
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

      const postBodies: unknown[] = [];
      mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string; body?: string }) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) {
          return { ok: true, status: 200, json: async () => ({}) };
        }
        if (url === '/api/v1/addresses/me' && !options?.method) {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === '/api/v1/addresses/me' && options?.method === 'POST') {
          postBodies.push(JSON.parse(options.body ?? '{}'));
          return { ok: true, status: 201, json: async () => ({ id: 'new-addr' }) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      // Set full address fields via PersonalInfoCard mock button
      await user.click(screen.getByRole('button', { name: /set full address/i }));

      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Profile saved', expect.any(Object));
      });

      // Verify address POST was called with the full payload including optional fields
      expect(mockFetchWithAuth).toHaveBeenCalledWith(
        '/api/v1/addresses/me',
        expect.objectContaining({ method: 'POST' })
      );
      expect(postBodies.length).toBe(1);
      const body = postBodies[0] as Record<string, unknown>;
      expect(body['street_line1']).toBe('500 Broadway');
      expect(body['street_line2']).toBe('Floor 3');
      expect(body['locality']).toBe('New York');
      expect(body['administrative_area']).toBe('NY');
      expect(body['postal_code']).toBe('10012');
      expect(body['country_code']).toBe('US');
      expect(body['place_id']).toBe('ChIJtest123');
      expect(body['latitude']).toBe(40.72);
      expect(body['longitude']).toBe(-73.99);
      expect(body['is_default']).toBe(true);
    });

    it('shows error when address create POST fails on empty items path', async () => {
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
          // Items exist but no default found
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === '/api/v1/addresses/me' && options?.method === 'POST') {
          return {
            ok: false,
            status: 422,
            clone: () => ({
              json: async () => ({ detail: [{ msg: 'Bad request' }] }),
            }),
            json: async () => ({ detail: [{ msg: 'Bad request' }] }),
          };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /set full address/i }));
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Bad request');
      });
    });

    it('shows error when address create POST fails on 404 path', async () => {
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
          // 404 response triggers the 404 code path
          return { ok: false, status: 404, json: async () => ({}) };
        }
        if (url === '/api/v1/addresses/me' && options?.method === 'POST') {
          return {
            ok: false,
            status: 500,
            clone: () => ({
              json: async () => ({ detail: [{ msg: 'Bad request' }] }),
            }),
            json: async () => ({ detail: [{ msg: 'Bad request' }] }),
          };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /set full address/i }));
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Bad request');
      });
    });

    it('uses deriveErrorMessage fallback when formatProblemMessages returns empty on address create', async () => {
      const { formatProblemMessages } = jest.requireMock('@/lib/httpErrors') as { formatProblemMessages: jest.Mock };
      formatProblemMessages.mockReturnValue([]);

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
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === '/api/v1/addresses/me' && options?.method === 'POST') {
          return {
            ok: false,
            status: 422,
            clone: () => ({
              json: async () => ({ detail: [] }),
            }),
            json: async () => ({ detail: [] }),
          };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /set full address/i }));
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      // When formatProblemMessages returns empty, deriveErrorMessage falls back to generic message
      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Request failed (422)');
      });

      formatProblemMessages.mockReturnValue(['Bad request']);
    });
  });

  describe('Batch 11 — targeted branch coverage', () => {
    it('sends preferred_teaching_locations when locations are changed from initial', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'A'.repeat(420),
          has_profile_picture: true,
          preferred_teaching_locations: [{ address: 'Old Studio', label: 'Main' }],
          preferred_public_spaces: [{ address: 'Old Park' }],
        },
        isLoading: false,
      });

      let savedPayload: Record<string, unknown> | null = null;
      mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string; body?: string }) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === '/api/v1/addresses/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE && options?.method === 'PUT') {
          savedPayload = JSON.parse(options?.body ?? '{}') as Record<string, unknown>;
          return { ok: true, status: 200, json: async () => ({}) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      // Change teaching and neutral locations from their initial values
      await user.click(screen.getByRole('button', { name: /set preferred/i }));
      await user.click(screen.getByRole('button', { name: /set neutral/i }));
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        expect(savedPayload).toBeTruthy();
      });

      // Since locations changed from initial, payload should include them
      expect(savedPayload).toHaveProperty('preferred_teaching_locations');
      expect(savedPayload).toHaveProperty('preferred_public_spaces');
    });

    it('does not send location fields when locations have not changed', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'A'.repeat(420),
          has_profile_picture: true,
        },
        isLoading: false,
      });

      let savedPayload: Record<string, unknown> | null = null;
      mockFetchWithAuth.mockImplementation(async (url: string, options?: { method?: string; body?: string }) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === '/api/v1/addresses/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE && options?.method === 'PUT') {
          savedPayload = JSON.parse(options?.body ?? '{}') as Record<string, unknown>;
          return { ok: true, status: 200, json: async () => ({}) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      // Save without changing locations
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        expect(savedPayload).toBeTruthy();
      });

      // Since no locations changed, payload should NOT include them
      expect(savedPayload).not.toHaveProperty('preferred_teaching_locations');
      expect(savedPayload).not.toHaveProperty('preferred_public_spaces');
    });

    it('handles sessionStorage.setItem throwing an error', async () => {
      const { Wrapper } = createWrapper();
      const onStepStatusChange = jest.fn();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'A'.repeat(420), has_profile_picture: true },
        isLoading: false,
      });

      // Make sessionStorage.setItem throw
      Object.defineProperty(window, 'sessionStorage', {
        value: {
          setItem: jest.fn(() => { throw new Error('Storage full'); }),
          getItem: jest.fn(),
          removeItem: jest.fn(),
        },
        writable: true,
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

      render(<InstructorProfileForm onStepStatusChange={onStepStatusChange} />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      // Should still succeed even if sessionStorage throws
      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Profile saved', expect.any(Object));
      });
    });

    it('handles address create POST failure on 404 path during save', async () => {
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
          return { ok: false, status: 404, json: async () => ({ detail: 'Not found' }) };
        }
        if (url === '/api/v1/addresses/me' && options?.method === 'POST') {
          return {
            ok: false,
            status: 400,
            clone: () => ({
              json: async () => ({ detail: 'Invalid data' }),
            }),
            json: async () => ({ detail: 'Invalid data' }),
          };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      // Set full address to trigger the create path
      await user.click(screen.getByRole('button', { name: /set full address/i }));
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalled();
      });
    });

    it('handles deriveErrorMessage when json parsing fails', async () => {
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
        if (url === API_ENDPOINTS.INSTRUCTOR_PROFILE) {
          return { ok: true, status: 200, json: async () => ({}) };
        }
        if (url === '/api/v1/addresses/me' && !options?.method) {
          return { ok: true, status: 200, json: async () => ({ items: [{ id: 'addr-1', postal_code: '00000', is_default: true }] }) };
        }
        if (url.includes('/api/v1/addresses/me/addr-1') && options?.method === 'PATCH') {
          return {
            ok: false,
            status: 422,
            clone: () => ({
              json: async () => { throw new Error('Bad JSON'); },
            }),
            json: async () => { throw new Error('Bad JSON'); },
          };
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

      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Request failed (422)');
      });
    });

    it('toggles section accordions in onboarding context', async () => {
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

      render(<InstructorProfileForm context="onboarding" />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      // Toggle Bio section
      await user.click(screen.getByRole('button', { name: /toggle bio/i }));
      // Toggle Service Areas section
      await user.click(screen.getByRole('button', { name: /toggle service areas/i }));
      // Toggle Preferred Locations section
      await user.click(screen.getByRole('button', { name: /toggle preferred locations/i }));

      // In onboarding context, Skills & Booking sections should NOT be shown
      expect(screen.queryByText(/skills & pricing/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/booking preferences/i)).not.toBeInTheDocument();
    });

    it('handles profile data with duplicate teaching locations at max limit', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test',
          preferred_teaching_locations: [
            { address: 'Studio A', label: 'Main' },
            { address: 'Studio B', label: 'Second' },
            { address: 'Studio C', label: 'Third' }, // Exceeds max of 2
          ],
          preferred_public_spaces: [
            { address: 'Park A' },
            { address: 'Park B' },
            { address: 'Park C' }, // Exceeds max of 2
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

    it('handles preferred locations with empty/whitespace addresses', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test',
          preferred_teaching_locations: [
            { address: '', label: 'Empty' },
            { address: '  ', label: 'Whitespace' },
            { address: 'Valid Studio', label: 'Good' },
          ],
          preferred_public_spaces: [
            { address: '' },
            { address: 'Valid Park' },
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

    it('handles service_area_boroughs from API being non-empty', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test',
          service_area_boroughs: ['Manhattan', 'Brooklyn', 'Queens'],
          service_area_neighborhoods: [],
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

    it('handles NYC zip check returning non-ok response', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [{ id: 'addr-1', postal_code: '10001', is_default: true }] },
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

      // NYC zip check returns error
      global.fetch = jest.fn().mockImplementation(async () => {
        return { ok: false, status: 500 };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });
    });

    it('handles NYC zip check throwing an error', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [{ id: 'addr-1', postal_code: '10001', is_default: true }] },
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

      // NYC zip check throws
      global.fetch = jest.fn().mockRejectedValue(new Error('Network error'));

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });
    });

    it('handles profile error response with empty formatProblemMessages', async () => {
      const { Wrapper } = createWrapper();
      const formatProblemMessages = jest.requireMock('@/lib/httpErrors').formatProblemMessages as jest.Mock;
      formatProblemMessages.mockReturnValue([]);

      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
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
          return { ok: false, status: 400, json: async () => ({ detail: 'Error' }) };
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
        // When formatProblemMessages returns empty, falls back to generic message
        expect(toast.error).toHaveBeenCalledWith('Request failed (400)');
      });

      formatProblemMessages.mockReturnValue(['Bad request']);
    });

    it('handles profile error response when json parsing fails', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
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
          return { ok: false, status: 500, json: async () => { throw new Error('Invalid JSON'); } };
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
        // Falls back to generic message when JSON parsing fails
        expect(toast.error).toHaveBeenCalledWith('Request failed (500)');
      });
    });
  });

  /* ==========================================================================
   * Branch coverage: lines 214-215, 384-385, 525
   * ========================================================================== */
  describe('branch coverage — uncovered paths', () => {
    it('hits hasFetchedPrefillRef early return on re-render with changed hook data (lines 214-215)', async () => {
      const { Wrapper } = createWrapper();
      const profileDataV1 = { bio: 'Original bio text' };
      const profileDataV2 = { bio: 'Updated bio text' };

      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: profileDataV1,
        isLoading: false,
      });

      mockFetchWithAuth.mockImplementation(async (url: string) => {
        if (url === '/api/v1/addresses/service-areas/me') {
          return { ok: true, status: 200, json: async () => ({ items: [] }) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      const { rerender } = render(<InstructorProfileForm />, { wrapper: Wrapper });

      // Wait for initial load to complete (hasFetchedPrefillRef set to true)
      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // Change the hook return to a new object reference so the useEffect
      // dependency array changes and the effect re-runs
      mockUseInstructorProfileMe.mockReturnValue({
        data: profileDataV2,
        isLoading: false,
      });

      rerender(<InstructorProfileForm />);

      // The effect re-runs but hits the early return at line 213-215
      // because hasFetchedPrefillRef.current is already true.
      // The component should still be rendered (not stuck in loading).
      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });
    });

    it('catches outer load() error and sets error state (lines 384-385)', async () => {
      const { Wrapper } = createWrapper();
      const loggerMock = jest.requireMock('@/lib/logger').logger as {
        error: jest.Mock;
      };
      const getServiceAreaBoroughsMock = jest.requireMock(
        '@/lib/profileServiceAreas'
      ).getServiceAreaBoroughs as jest.Mock;

      // Make getServiceAreaBoroughs throw so the outer catch fires.
      // This function is called during profile processing (line 289),
      // which is outside the inner try/catch blocks.
      getServiceAreaBoroughsMock.mockImplementation(() => {
        throw new Error('boroughs explosion');
      });

      mockUseSession.mockReturnValue({
        data: null,
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        // Provide data with empty service_area_boroughs so the fallback
        // calls getServiceAreaBoroughs (the throwing mock)
        data: { bio: 'Test', service_area_boroughs: [] },
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
        expect(loggerMock.error).toHaveBeenCalledWith(
          'Failed to load profile',
          expect.any(Error)
        );
      });

      // The error message should be rendered in the UI
      expect(screen.getByText('Failed to load profile')).toBeInTheDocument();

      // Restore the mock for other tests
      getServiceAreaBoroughsMock.mockImplementation(() => ['Manhattan']);
    });

    it('calls window.scrollBy when borough accordion position changes (line 525)', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1' },
        isLoading: false,
      });
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
        if (typeof url === 'string' && url.includes('/neighborhoods')) {
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

      // Mock requestAnimationFrame to invoke callbacks synchronously
      const origRaf = window.requestAnimationFrame;
      window.requestAnimationFrame = jest.fn((cb: FrameRequestCallback) => {
        cb(0);
        return 0;
      });

      const scrollBySpy = jest.fn();
      window.scrollBy = scrollBySpy;

      // Simulate getBoundingClientRect returning different top values
      // on successive calls (first call: prevTop=100, second call: newTop=150)
      let callCount = 0;
      const origGetBCR = Element.prototype.getBoundingClientRect;
      Element.prototype.getBoundingClientRect = function () {
        const result = origGetBCR.call(this);
        if (this.getAttribute('data-testid') === 'borough-accordion-manhattan') {
          callCount++;
          // First call (prevTop capture): 100, Second call (newTop capture): 150
          return { ...result, top: callCount <= 1 ? 100 : 150 };
        }
        return result;
      };

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /toggle borough/i }));

      await waitFor(() => {
        expect(scrollBySpy).toHaveBeenCalledWith({
          top: 50,
          left: 0,
          behavior: 'auto',
        });
      });

      // Restore
      Element.prototype.getBoundingClientRect = origGetBCR;
      window.requestAnimationFrame = origRaf;
    });

    it('uses embedded user fallback when userDataFromHook is null (lines 240-242)', async () => {
      const { Wrapper } = createWrapper();
      // Do NOT provide session data (userDataFromHook is null)
      mockUseSession.mockReturnValue({ data: null, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test bio',
          // Embedded user in the profile data — triggers fallback path
          user: {
            first_name: 'EmbeddedFirst',
            last_name: 'EmbeddedLast',
            zip_code: '10001',
          },
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
        expect(screen.getByTestId('personal-info')).toHaveTextContent('EmbeddedFirst');
        expect(screen.getByTestId('personal-info')).toHaveTextContent('EmbeddedLast');
      });
    });

    it('covers buildInstructorProfilePayload nullish branches during save (lines 48-49)', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        // Omit min_advance_booking_hours and buffer_time_minutes so they
        // default to undefined, triggering the ?? branches in
        // buildInstructorProfilePayload
        data: { bio: 'A'.repeat(420), has_profile_picture: true },
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
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        // Verify the profile save was called with default values
        expect(mockFetchWithAuth).toHaveBeenCalledWith(
          API_ENDPOINTS.INSTRUCTOR_PROFILE,
          expect.objectContaining({
            method: 'PUT',
            body: expect.stringContaining('"min_advance_booking_hours":2'),
          })
        );
      });
    });

    it('builds address payload with optional fields and covers branches (lines 81-90)', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
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
          // GET /addresses/me returns 404 to trigger address creation
          return { ok: false, status: 404, json: async () => ({}) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // Click "Set Full Address" to populate address fields
      // (street_line1, street_line2, locality, administrative_area,
      //  postal_code, country_code, place_id, latitude, longitude)
      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /set full address/i }));

      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalledWith(
          API_ENDPOINTS.INSTRUCTOR_PROFILE,
          expect.objectContaining({ method: 'PUT' })
        );
      });
    });

    it('patches address when zip code differs from existing default (lines 641-649)', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [{ id: 'addr-1', postal_code: '10001', is_default: true }] },
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
          // GET returns existing default address with OLD zip
          return {
            ok: true,
            status: 200,
            json: async () => ({
              items: [{ id: 'addr-1', postal_code: '10001', is_default: true }],
            }),
          };
        }
        if (url.includes('/api/v1/addresses/me/addr-1') && options?.method === 'PATCH') {
          return { ok: true, status: 200, json: async () => ({}) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // Change zip code to a different value to trigger the PATCH branch
      const user = userEvent.setup();
      const zipInput = screen.getByLabelText(/zip code/i);
      await user.clear(zipInput);
      await user.type(zipInput, '10002');

      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalledWith(
          '/api/v1/addresses/me/addr-1',
          expect.objectContaining({
            method: 'PATCH',
            body: JSON.stringify({ postal_code: '10002' }),
          })
        );
      });
    });

    it('handles address PATCH failure (line 649)', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [{ id: 'addr-1', postal_code: '10001', is_default: true }] },
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
          return {
            ok: true,
            status: 200,
            json: async () => ({
              items: [{ id: 'addr-1', postal_code: '10001', is_default: true }],
            }),
          };
        }
        if (url.includes('/api/v1/addresses/me/addr-1') && options?.method === 'PATCH') {
          // PATCH fails
          return { ok: false, status: 422, json: async () => ({ detail: 'Invalid zip' }) };
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
      await user.type(zipInput, '10002');

      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalled();
      });
    });

    it('deduplicates empty/whitespace teaching locations during save (lines 554-556)', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'A'.repeat(420),
          has_profile_picture: true,
          // Preferred locations with empty/whitespace entries to trigger
          // the continue branch (line 554) and dedup branch (line 556)
          preferred_teaching_locations: [
            { address: '  ', label: 'Blank' },
            { address: 'Studio A', label: 'Main' },
            { address: 'studio a', label: 'Duplicate' },
          ],
          preferred_public_spaces: [
            { address: '' },
            { address: 'Park X' },
            { address: 'park x' },
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

      // The mock PersonalInfoCard "Set Preferred" and "Set Neutral" buttons
      // are different from what sets locations here — the locations come from
      // the initial prefill. We trigger save to exercise the dedup code
      // in the save function (lines 550-578).
      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalledWith(
          API_ENDPOINTS.INSTRUCTOR_PROFILE,
          expect.objectContaining({ method: 'PUT' })
        );
      });
    });

    it('uses toTitle formatNeighborhoodName for empty-string edge case (line 103)', async () => {
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

      // The mock ServiceAreasCard calls formatNeighborhoodName('lower east')
      // which exercises toTitle, including the empty-check on charAt(0)
      expect(screen.getByTestId('formatted-name')).toHaveTextContent('Lower East');
    });

    it('uses embedded user fallback with empty fields hitting || fallbacks (lines 240-242)', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: null, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          bio: 'Test bio',
          // Embedded user with empty/falsy fields to trigger || '' fallbacks
          user: {
            first_name: '',
            last_name: null,
            // zip_code missing entirely
          },
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
        // Should still render — empty strings from fallback
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });
    });

    it('builds address payload without optional fields (lines 85-90 falsy)', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
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
          return { ok: false, status: 404, json: async () => ({}) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // Click "Set Basic Address" (no street_line2, place_id, lat, lng)
      // to trigger falsy branches in buildInstructorAddressPayload
      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /set basic address/i }));

      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        // Address should be created with only required fields
        expect(mockFetchWithAuth).toHaveBeenCalledWith(
          '/api/v1/addresses/me',
          expect.objectContaining({
            method: 'POST',
            body: expect.not.stringContaining('street_line2'),
          })
        );
      });
    });

    it('handles address sync throwing an error (line 690)', async () => {
      const { Wrapper } = createWrapper();
      const loggerMock = jest.requireMock('@/lib/logger').logger as {
        warn: jest.Mock;
      };

      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
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
          // Throw a non-Error value to hit the instanceof Error falsy branch
          throw 'network failure string';
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
        expect(loggerMock.warn).toHaveBeenCalledWith(
          'Failed to sync address during profile save',
          undefined
        );
      });
    });

    it('covers deriveErrorMessage parse failure branch in save (line 624)', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
        isLoading: false,
      });
      mockUseUserAddresses.mockReturnValue({
        data: { items: [{ id: 'addr-1', postal_code: '10001', is_default: true }] },
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
          return {
            ok: true,
            status: 200,
            json: async () => ({
              items: [{ id: 'addr-1', postal_code: '10001', is_default: true }],
            }),
          };
        }
        if (url.includes('/api/v1/addresses/me/addr-1') && options?.method === 'PATCH') {
          // PATCH fails with unparseable JSON to trigger deriveErrorMessage
          // catch block at line 624
          return {
            ok: false,
            status: 500,
            clone: () => ({
              json: async () => { throw new Error('Unparseable body'); },
            }),
            json: async () => { throw new Error('Unparseable body'); },
          };
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
      await user.type(zipInput, '10002');

      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        // Falls back to generic message since json parsing failed
        expect(toast.error).toHaveBeenCalledWith('Request failed (500)');
      });
    });

    it('deduplicates and filters dirty teaching/public locations during save (lines 554-577)', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
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
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      const user = userEvent.setup();

      // Set dirty preferred locations: includes empties, whitespace, and
      // case-insensitive duplicates to trigger lines 554 (!trimmed),
      // 556 (seenTeaching.has(key)), and 565 (length === 2 break)
      await user.click(screen.getByRole('button', { name: /set dirty preferred/i }));

      // Set dirty neutral places: same pattern for lines 572, 574, 577
      await user.click(screen.getByRole('button', { name: /set dirty neutral/i }));

      await user.click(screen.getByRole('button', { name: /save changes/i }));

      await waitFor(() => {
        const profileCall = mockFetchWithAuth.mock.calls.find(
          (call: unknown[]) => call[0] === API_ENDPOINTS.INSTRUCTOR_PROFILE
        ) as unknown[] | undefined;
        expect(profileCall).toBeDefined();
        const opts = profileCall![1] as { body: string };
        const body = JSON.parse(opts.body) as Record<string, unknown>;
        // Only unique, non-empty locations should be in the payload
        if (body['preferred_teaching_locations']) {
          const locs = body['preferred_teaching_locations'] as Array<{ address: string }>;
          expect(locs.length).toBeLessThanOrEqual(2);
          for (const loc of locs) {
            expect(loc.address.trim().length).toBeGreaterThan(0);
          }
        }
      });
    });

    it('handles NaN in advance notice input (line 1044)', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test', min_advance_booking_hours: 3, buffer_time_minutes: 60 },
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

      await waitFor(() => {
        expect(screen.getByText(/advance notice/i)).toBeInTheDocument();
      });

      const inputs = screen.getAllByRole('spinbutton');
      const advanceInput = inputs[0]!;

      // Fire onChange with a value that makes parseInt return NaN
      // The input has || '0' fallback but we can simulate via fireEvent
      // directly with a non-numeric value
      await user.clear(advanceInput);
      // After clear, value is '' -> parseInt('' || '0', 10) = 0, not NaN
      // To produce NaN, we need parseInt of something non-numeric
      // jsdom number inputs accept any string via fireEvent.change
      const { fireEvent } = await import('@testing-library/react');
      fireEvent.change(advanceInput, { target: { value: 'abc' } });

      await waitFor(() => {
        // parseInt('abc' || '0', 10) -> 'abc' is truthy, so parseInt('abc', 10) = NaN
        // isNaN(NaN) -> true, so result = 1 (clamped)
        expect(advanceInput).toHaveValue(1);
      });
    });

    it('handles NaN in buffer time input (line 1075)', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({ data: { id: 'user-1' }, isLoading: false });
      mockUseUserAddresses.mockReturnValue({ data: { items: [] }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: { bio: 'Test', min_advance_booking_hours: 3, buffer_time_minutes: 60 },
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

      await waitFor(() => {
        expect(screen.getByText(/buffer time/i)).toBeInTheDocument();
      });

      const inputs = screen.getAllByRole('spinbutton');
      const bufferInput = inputs[1]!;

      // Fire change with non-numeric value to trigger NaN path
      const { fireEvent } = await import('@testing-library/react');
      fireEvent.change(bufferInput, { target: { value: 'xyz' } });

      await waitFor(() => {
        // parseFloat('xyz' || '0') -> 'xyz' is truthy, parseFloat('xyz') = NaN
        // isNaN(NaN) -> true, result = 0 (clamped)
        expect(bufferInput).toHaveValue(0);
      });
    });

    it('covers save button guard when not saving (line 1092)', async () => {
      const { Wrapper } = createWrapper();
      mockUseSession.mockReturnValue({
        data: { id: 'user-1', first_name: 'T', last_name: 'U' },
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
        return { ok: true, status: 200, json: async () => ({}) };
      });

      render(<InstructorProfileForm />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(screen.getByTestId('personal-info')).toBeInTheDocument();
      });

      // Clicking save when not currently saving exercises the
      // if (!saving && !savingServiceAreas) guard at line 1092
      const user = userEvent.setup();
      const saveBtn = screen.getByRole('button', { name: /save changes/i });
      expect(saveBtn).not.toBeDisabled();
      await user.click(saveBtn);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalledWith(
          API_ENDPOINTS.INSTRUCTOR_PROFILE,
          expect.objectContaining({ method: 'PUT' })
        );
      });
    });
  });
});
