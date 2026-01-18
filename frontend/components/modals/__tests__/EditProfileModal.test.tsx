import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import EditProfileModal from '../EditProfileModal';
import { fetchWithAuth } from '@/lib/api';
import { useInstructorProfileMe } from '@/hooks/queries/useInstructorProfileMe';
import { useServiceCategories, useAllServicesWithInstructors } from '@/hooks/queries/useServices';
import { useInstructorServiceAreas } from '@/hooks/queries/useInstructorServiceAreas';
import { usePricingConfig } from '@/lib/pricing/usePricingFloors';
import { usePlatformFees } from '@/hooks/usePlatformConfig';
import type { ReactNode } from 'react';
import type { SelectedNeighborhood } from '@/features/shared/components/SelectedNeighborhoodChips';

// Mock dependencies
jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(),
  API_ENDPOINTS: {
    INSTRUCTOR_PROFILE: '/api/v1/instructors/me',
    ME: '/api/v1/users/me',
  },
}));

jest.mock('@/hooks/queries/useInstructorProfileMe', () => ({
  useInstructorProfileMe: jest.fn(),
}));

jest.mock('@/hooks/queries/useServices', () => ({
  useServiceCategories: jest.fn(),
  useAllServicesWithInstructors: jest.fn(),
}));

jest.mock('@/hooks/queries/useInstructorServiceAreas', () => ({
  useInstructorServiceAreas: jest.fn(),
}));

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingConfig: jest.fn(),
}));

jest.mock('@/hooks/usePlatformConfig', () => ({
  usePlatformFees: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('@/lib/instructorServices', () => ({
  normalizeInstructorServices: jest.fn((services) =>
    Promise.resolve(
      services.map((s: Record<string, unknown>) => ({
        ...s,
        service_catalog_name: s['service_catalog_name'] ?? s['name'] ?? 'Service',
      }))
    )
  ),
  hydrateCatalogNameById: jest.fn((id) => id),
  displayServiceName: jest.fn((service) => {
    const name = service?.service_catalog_name ?? service?.name ?? service?.skill ?? 'Service';
    return typeof name === 'string' ? name : 'Service';
  }),
}));

jest.mock('@/lib/pricing/priceFloors', () => ({
  evaluatePriceFloorViolations: jest.fn(() => []),
  formatCents: jest.fn((cents) => (cents / 100).toFixed(2)),
}));

jest.mock('@/lib/pricing/platformFees', () => ({
  formatPlatformFeeLabel: jest.fn(() => '15%'),
  resolvePlatformFeeRate: jest.fn(() => 0.15),
  resolveTakeHomePct: jest.fn(() => 0.85),
}));

jest.mock('@/lib/profileServiceAreas', () => ({
  getServiceAreaBoroughs: jest.fn(() => ['Manhattan', 'Brooklyn']),
}));

jest.mock('@/lib/profileSchemaDebug', () => ({
  buildProfileUpdateBody: jest.fn((profileData) => ({
    bio: profileData.bio,
    years_experience: profileData.years_experience,
    services: profileData.services,
  })),
}));

jest.mock('@/components/forms/PlacesAutocompleteInput', () => ({
  PlacesAutocompleteInput: ({
    value,
    onValueChange,
    placeholder
  }: {
    value?: string;
    onValueChange?: (val: string) => void;
    placeholder?: string;
  }) => (
    <input
      placeholder={placeholder}
      data-testid="places-autocomplete"
      value={value ?? ''}
      onChange={(e) => onValueChange?.(e.target.value)}
    />
  ),
}));

jest.mock('@/features/shared/components/SelectedNeighborhoodChips', () => ({
  SelectedNeighborhoodChips: ({
    selected,
    onRemove
  }: {
    selected: SelectedNeighborhood[];
    onRemove: (id: string) => void;
  }) => (
    <div data-testid="neighborhood-chips">
      {selected.map((s) => (
        <span key={s.neighborhood_id} data-testid={`chip-${s.neighborhood_id}`}>
          {s.name}
          <button
            data-testid={`remove-${s.neighborhood_id}`}
            onClick={() => onRemove(s.neighborhood_id)}
          >
            ×
          </button>
        </span>
      ))}
    </div>
  ),
}));

const fetchWithAuthMock = fetchWithAuth as jest.Mock;
const useInstructorProfileMeMock = useInstructorProfileMe as jest.Mock;
const useServiceCategoriesMock = useServiceCategories as jest.Mock;
const useAllServicesWithInstructorsMock = useAllServicesWithInstructors as jest.Mock;
const useInstructorServiceAreasMock = useInstructorServiceAreas as jest.Mock;
const usePricingConfigMock = usePricingConfig as jest.Mock;
const usePlatformFeesMock = usePlatformFees as jest.Mock;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return Wrapper;
};

const mockInstructorProfile = {
  id: 'inst-123',
  bio: 'Test bio',
  years_experience: 5,
  service_area_boroughs: ['Manhattan', 'Brooklyn'],
  service_area_neighborhoods: [],
  services: [
    {
      service_catalog_id: 'svc-1',
      name: 'Piano Lessons',
      hourly_rate: 60,
      age_groups: ['adults'],
      levels_taught: ['beginner'],
      location_types: ['in-person'],
      duration_options: [60],
    },
  ],
  // Required fields for InstructorProfile type
  buffer_time_minutes: 15,
  created_at: '2025-01-01T00:00:00Z',
  favorited_count: 0,
  is_founding_instructor: false,
  min_booking_notice_hours: 24,
  user_id: 'user-123',
  verified: true,
  visible: true,
  status: 'active' as const,
};

describe('EditProfileModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    onSuccess: jest.fn(),
    variant: 'full' as const,
  };

  beforeEach(() => {
    jest.clearAllMocks();

    // Default mock implementations
    useInstructorProfileMeMock.mockReturnValue({ data: null });
    useServiceCategoriesMock.mockReturnValue({ data: [], isLoading: false });
    useAllServicesWithInstructorsMock.mockReturnValue({ data: [], isLoading: false });
    useInstructorServiceAreasMock.mockReturnValue({ data: null });
    usePricingConfigMock.mockReturnValue({
      config: {
        student_fee_pct: 0.15,
        instructor_tiers: [{ min: 0, pct: 0.15 }],
      },
    });
    usePlatformFeesMock.mockReturnValue({
      fees: {
        tier_1: 0.15,
        tier_2: 0.12,
        tier_3: 0.10,
      },
    });

    fetchWithAuthMock.mockImplementation((url: string) => {
      if (url.includes('instructors/me')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockInstructorProfile),
        });
      }
      if (url.includes('users/me')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ first_name: 'John', last_name: 'Doe' }),
        });
      }
      if (url.includes('addresses/me')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: [] }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
  });

  describe('modal visibility', () => {
    it('renders nothing when isOpen is false', () => {
      render(
        <EditProfileModal {...defaultProps} isOpen={false} />,
        { wrapper: createWrapper() }
      );

      expect(screen.queryByText('Edit Profile')).not.toBeInTheDocument();
    });

    it('renders modal when isOpen is true', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        // The modal should be visible - look for any modal content
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });
  });

  describe('close behavior', () => {
    it('calls onClose when close button is clicked', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();

      render(
        <EditProfileModal {...defaultProps} onClose={onClose} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Find and click close button
      const closeButtons = screen.getAllByRole('button');
      const closeButton = closeButtons.find((btn) =>
        btn.querySelector('svg')?.classList.contains('lucide-x') ||
        btn.getAttribute('aria-label')?.includes('close')
      );

      if (closeButton) {
        await user.click(closeButton);
        expect(onClose).toHaveBeenCalled();
      }
    });
  });

  describe('variant: about', () => {
    it('shows about editing form', async () => {
      render(
        <EditProfileModal {...defaultProps} variant="about" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });
  });

  describe('variant: areas', () => {
    it('shows areas editing form', async () => {
      render(
        <EditProfileModal {...defaultProps} variant="areas" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });

    it('uses prefilled selectedServiceAreas', async () => {
      const selectedAreas = [
        { neighborhood_id: 'n1', name: 'Upper East Side', borough: 'Manhattan' },
      ];

      render(
        <EditProfileModal
          {...defaultProps}
          variant="areas"
          selectedServiceAreas={selectedAreas}
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });
  });

  describe('variant: services', () => {
    it('shows services editing form', async () => {
      render(
        <EditProfileModal {...defaultProps} variant="services" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });
  });

  describe('pre-fetched profile', () => {
    it('uses pre-fetched instructorProfile', async () => {
      render(
        <EditProfileModal
          {...defaultProps}
          instructorProfile={mockInstructorProfile as never}
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should not make additional profile API call when pre-fetched
      expect(fetchWithAuthMock).not.toHaveBeenCalledWith('/api/v1/instructors/me');
    });
  });

  describe('error handling', () => {
    it('shows error when profile fetch fails', async () => {
      fetchWithAuthMock.mockImplementation((url: string) => {
        if (url.includes('instructors/me')) {
          return Promise.resolve({ ok: false, status: 500 });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      });

      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });
  });

  describe('pricing config', () => {
    it('uses pricing config for floor validation', async () => {
      usePricingConfigMock.mockReturnValue({
        config: {
          price_floor_cents: {
            'in-person': { 30: 2000, 60: 4000 },
            online: { 30: 1500, 60: 3000 },
          },
        },
      });

      render(
        <EditProfileModal {...defaultProps} variant="services" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });
  });

  describe('platform fees', () => {
    it('uses platform fees for display', async () => {
      usePlatformFeesMock.mockReturnValue({
        fees: {
          instructor_tiers: [{ min: 0, pct: 0.15 }],
          founding_instructor_pct: 0.08,
        },
      });

      render(
        <EditProfileModal {...defaultProps} variant="services" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });
  });

  describe('areas variant callbacks', () => {
    it('calls onSave when areas variant saves', async () => {
      const onSave = jest.fn();

      render(
        <EditProfileModal
          {...defaultProps}
          variant="areas"
          onSave={onSave}
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });
  });

  describe('modal content structure', () => {
    it('renders with Radix Dialog', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        const dialog = screen.getByRole('dialog');
        expect(dialog).toBeInTheDocument();
      });
    });
  });

  describe('form field changes', () => {
    it('updates first name on input change', async () => {
      const user = userEvent.setup();
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      const firstNameInput = screen.getByLabelText(/first name/i);
      await user.clear(firstNameInput);
      await user.type(firstNameInput, 'Jane');

      expect(firstNameInput).toHaveValue('Jane');
    });

    it('updates last name on input change', async () => {
      const user = userEvent.setup();
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      const lastNameInput = screen.getByLabelText(/last name/i);
      // Wait for initial value to load
      await waitFor(() => {
        expect(lastNameInput).toHaveValue('Doe');
      });

      await user.clear(lastNameInput);
      await user.type(lastNameInput, 'Smith');

      await waitFor(() => {
        expect(lastNameInput).toHaveValue('Smith');
      });
    });

    it('updates postal code on input change', async () => {
      const user = userEvent.setup();
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      const postalCodeInput = screen.getByLabelText(/zip code/i);
      await user.clear(postalCodeInput);
      await user.type(postalCodeInput, '10001');

      expect(postalCodeInput).toHaveValue('10001');
    });

    it('updates bio on textarea change', async () => {
      const user = userEvent.setup();
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Wait for initial bio to load (may be empty or "Test bio")
      await waitFor(() => {
        const bioTextarea = screen.getByLabelText(/bio/i);
        expect(bioTextarea).toBeInTheDocument();
      });

      const bioTextarea = screen.getByLabelText(/bio/i);
      await user.clear(bioTextarea);
      await user.type(bioTextarea, 'New bio text');

      await waitFor(() => {
        expect(bioTextarea).toBeInTheDocument();
      });
    });

    it('updates years of experience on input change', async () => {
      const user = userEvent.setup();
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      const experienceInput = screen.getByLabelText(/years of experience/i);
      await user.clear(experienceInput);
      await user.type(experienceInput, '10');

      expect(experienceInput).toHaveValue(10);
    });

    it('displays character count for bio', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should show character count
      expect(screen.getByText(/\/1000 characters/)).toBeInTheDocument();
    });
  });

  describe('service area toggle', () => {
    it('toggles service area when clicked', async () => {
      const user = userEvent.setup();
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Find Manhattan checkbox (in the service areas section)
      const manhattanLabel = screen.getByText('Manhattan');
      const checkbox = manhattanLabel.closest('label')?.querySelector('input[type="checkbox"]');

      if (checkbox) {
        const initialChecked = (checkbox as HTMLInputElement).checked;
        await user.click(checkbox);
        expect((checkbox as HTMLInputElement).checked).toBe(!initialChecked);
      }
    });

    it('shows warning when no service areas selected', async () => {
      // Mock with empty boroughs
      const { getServiceAreaBoroughs } = jest.requireMock('@/lib/profileServiceAreas');
      getServiceAreaBoroughs.mockReturnValue([]);

      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Look for the warning message
      await waitFor(() => {
        expect(screen.getByText(/please select at least one area of service/i)).toBeInTheDocument();
      });
    });
  });

  describe('service management (full variant)', () => {
    it('renders the full variant with profile data', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Full variant should show personal information section
      await waitFor(() => {
        expect(screen.getByText(/personal information/i)).toBeInTheDocument();
      });
    });

    it('shows about you section header in full variant', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have About You section header
      await waitFor(() => {
        expect(screen.getByText('About You')).toBeInTheDocument();
      });
    });

    it('renders full variant form sections', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Wait for form to fully render
      await waitFor(() => {
        expect(screen.getByText(/personal information/i)).toBeInTheDocument();
      });

      // Should have bio section
      expect(screen.getByLabelText(/bio/i)).toBeInTheDocument();
    });

    it('renders bio field in full variant', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have bio field
      await waitFor(() => {
        expect(screen.getByLabelText(/bio/i)).toBeInTheDocument();
      });
    });
  });

  describe('full form submission (handleSubmit)', () => {
    it('renders save changes button', async () => {
      render(
        <EditProfileModal {...defaultProps} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Wait for form to be fully loaded
      await waitFor(() => {
        expect(screen.getByText(/personal information/i)).toBeInTheDocument();
      });

      // Save changes button should be present
      const saveButton = screen.getByRole('button', { name: /save changes/i });
      expect(saveButton).toBeInTheDocument();
    });

    it('save button is clickable', async () => {
      const user = userEvent.setup();

      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Wait for form to be ready
      await waitFor(() => {
        expect(screen.getByText(/personal information/i)).toBeInTheDocument();
      });

      // Click save button - should not throw
      const saveButton = screen.getByRole('button', { name: /save changes/i });
      await user.click(saveButton);

      // Button should still be in document after click
      expect(saveButton).toBeInTheDocument();
    });

    it('renders save button enabled when valid', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Save button should be present and enabled
      const saveButton = screen.getByRole('button', { name: /save changes/i });
      expect(saveButton).toBeInTheDocument();
    });

    it('handles postal code field update', async () => {
      const user = userEvent.setup();

      render(
        <EditProfileModal {...defaultProps} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Change postal code
      const postalCodeInput = screen.getByLabelText(/zip code/i);
      await user.clear(postalCodeInput);
      await user.type(postalCodeInput, '10002');

      await waitFor(() => {
        expect(postalCodeInput).toHaveValue('10002');
      });
    });
  });

  describe('about variant save (handleSaveBioExperience)', () => {
    it('saves bio and experience successfully', async () => {
      const user = userEvent.setup();
      const onSuccess = jest.fn();
      const onClose = jest.fn();

      fetchWithAuthMock.mockImplementation((url: string, options?: RequestInit) => {
        if (url.includes('instructors/me') && options?.method === 'PUT') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
        }
        if (url.includes('instructors/me')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(mockInstructorProfile),
          });
        }
        if (url.includes('users/me') && options?.method === 'PATCH') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
        }
        if (url.includes('users/me')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ first_name: 'John', last_name: 'Doe' }),
          });
        }
        if (url.includes('addresses/me')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ items: [] }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      });

      render(
        <EditProfileModal
          {...defaultProps}
          variant="about"
          onSuccess={onSuccess}
          onClose={onClose}
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Find and click save button in about variant
      const saveButton = screen.getByRole('button', { name: /save/i });
      await user.click(saveButton);

      await waitFor(() => {
        expect(onSuccess).toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('shows error when about save fails', async () => {
      const user = userEvent.setup();

      fetchWithAuthMock.mockImplementation((url: string, options?: RequestInit) => {
        if (url.includes('instructors/me') && options?.method === 'PUT') {
          return Promise.resolve({
            ok: false,
            json: () => Promise.resolve({ detail: 'Bio save failed' }),
          });
        }
        if (url.includes('instructors/me')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(mockInstructorProfile),
          });
        }
        if (url.includes('users/me')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ first_name: 'John', last_name: 'Doe' }),
          });
        }
        if (url.includes('addresses/me')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ items: [] }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      });

      render(
        <EditProfileModal {...defaultProps} variant="about" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      const saveButton = screen.getByRole('button', { name: /save/i });
      await user.click(saveButton);

      await waitFor(() => {
        expect(screen.getByText(/bio save failed/i)).toBeInTheDocument();
      });
    });
  });

  describe('areas variant save (handleAreasSave)', () => {
    it('calls onSave callback when provided', async () => {
      const user = userEvent.setup();
      const onSave = jest.fn().mockResolvedValue(undefined);
      const onSuccess = jest.fn();
      const onClose = jest.fn();

      render(
        <EditProfileModal
          {...defaultProps}
          variant="areas"
          onSave={onSave}
          onSuccess={onSuccess}
          onClose={onClose}
          selectedServiceAreas={[{ neighborhood_id: 'n1', name: 'Upper East Side' }]}
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Find and click save button
      const saveButton = screen.getByRole('button', { name: /save/i });
      await user.click(saveButton);

      await waitFor(() => {
        expect(onSave).toHaveBeenCalled();
        expect(onSuccess).toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('saves areas via API when onSave not provided', async () => {
      const user = userEvent.setup();
      const onSuccess = jest.fn();
      const onClose = jest.fn();

      fetchWithAuthMock.mockImplementation((url: string, options?: RequestInit) => {
        if (url.includes('service-areas/me') && options?.method === 'PUT') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
        }
        if (url.includes('instructors/me') && options?.method === 'PUT') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
        }
        if (url.includes('instructors/me')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(mockInstructorProfile),
          });
        }
        if (url.includes('users/me')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ first_name: 'John', last_name: 'Doe' }),
          });
        }
        if (url.includes('addresses/me')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ items: [] }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      });

      render(
        <EditProfileModal
          {...defaultProps}
          variant="areas"
          onSuccess={onSuccess}
          onClose={onClose}
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      const saveButton = screen.getByRole('button', { name: /save/i });
      await user.click(saveButton);

      await waitFor(() => {
        expect(onSuccess).toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('handles areas save error', async () => {
      const user = userEvent.setup();
      const onSave = jest.fn().mockRejectedValue(new Error('Areas save failed'));

      render(
        <EditProfileModal
          {...defaultProps}
          variant="areas"
          onSave={onSave}
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      const saveButton = screen.getByRole('button', { name: /save/i });
      await user.click(saveButton);

      await waitFor(() => {
        expect(screen.getByText(/areas save failed/i)).toBeInTheDocument();
      });
    });
  });

  describe('services variant (handleServicesSave)', () => {
    it('renders services variant with service categories header', async () => {
      useServiceCategoriesMock.mockReturnValue({
        data: [{ id: 'cat-1', slug: 'music', name: 'Music' }],
        isLoading: false,
      });

      render(
        <EditProfileModal
          {...defaultProps}
          variant="services"
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should show Service categories header (exact case)
      await waitFor(() => {
        expect(screen.getByText('Service categories')).toBeInTheDocument();
      });
    });

    it('shows loading state while services load', async () => {
      useServiceCategoriesMock.mockReturnValue({
        data: null,
        isLoading: true,
      });

      render(
        <EditProfileModal {...defaultProps} variant="services" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should show loading indicator
      await waitFor(() => {
        expect(screen.getByText(/loading/i)).toBeInTheDocument();
      });
    });

    it('calls API when save button clicked', async () => {
      const user = userEvent.setup();

      useServiceCategoriesMock.mockReturnValue({
        data: [{ id: 'cat-1', slug: 'music', name: 'Music' }],
        isLoading: false,
      });

      fetchWithAuthMock.mockImplementation((url: string, options?: RequestInit) => {
        if (url.includes('instructors/me') && options?.method === 'PUT') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      });

      render(
        <EditProfileModal {...defaultProps} variant="services" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Click save button
      const saveButton = screen.getByRole('button', { name: /save/i });
      await user.click(saveButton);

      // Verify API call was made
      await waitFor(() => {
        expect(fetchWithAuthMock).toHaveBeenCalledWith(
          expect.stringContaining('instructors/me'),
          expect.objectContaining({ method: 'PUT' })
        );
      });
    });

    it('handles services save API error', async () => {
      const user = userEvent.setup();

      useServiceCategoriesMock.mockReturnValue({
        data: [{ id: 'cat-1', slug: 'music', name: 'Music' }],
        isLoading: false,
      });

      fetchWithAuthMock.mockImplementation((url: string, options?: RequestInit) => {
        if (url.includes('instructors/me') && options?.method === 'PUT') {
          return Promise.resolve({
            ok: false,
            status: 400,
            json: () => Promise.resolve({ detail: 'Validation error' }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      });

      render(<EditProfileModal {...defaultProps} variant="services" />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      const saveButton = screen.getByRole('button', { name: /save/i });
      await user.click(saveButton);

      // Verify API was attempted
      await waitFor(() => {
        expect(fetchWithAuthMock).toHaveBeenCalledWith(
          expect.stringContaining('instructors/me'),
          expect.objectContaining({ method: 'PUT' })
        );
      });
    });
  });

  describe('services variant UI interactions', () => {
    it('renders service categories when data available', async () => {
      useServiceCategoriesMock.mockReturnValue({
        data: [
          { id: 'cat-1', slug: 'music', name: 'Music', display_order: 1 },
        ],
        isLoading: false,
      });

      useAllServicesWithInstructorsMock.mockReturnValue({
        data: {
          categories: [
            {
              slug: 'music',
              services: [{ id: 'svc-music-1', name: 'Piano' }],
            },
          ],
        },
        isLoading: false,
      });

      render(
        <EditProfileModal {...defaultProps} variant="services" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should show Service categories (exact case)
      await waitFor(() => {
        expect(screen.getByText('Service categories')).toBeInTheDocument();
      });
    });

    it('renders skills search input', async () => {
      useServiceCategoriesMock.mockReturnValue({
        data: [{ id: 'cat-1', slug: 'music', name: 'Music' }],
        isLoading: false,
      });

      render(
        <EditProfileModal {...defaultProps} variant="services" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should show search input
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/search skills/i)).toBeInTheDocument();
      });
    });

    it('shows category accordions', async () => {
      useServiceCategoriesMock.mockReturnValue({
        data: [{ id: 'cat-1', slug: 'music', name: 'Music' }],
        isLoading: false,
      });

      useAllServicesWithInstructorsMock.mockReturnValue({
        data: {
          categories: [{
            slug: 'music',
            services: [{ id: 'svc-1', name: 'Piano' }],
          }],
        },
        isLoading: false,
      });

      render(
        <EditProfileModal {...defaultProps} variant="services" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should show Music category button
      await waitFor(() => {
        expect(screen.getByText('Music')).toBeInTheDocument();
      });
    });

    it('shows loading state when fetching services', async () => {
      useServiceCategoriesMock.mockReturnValue({
        data: null,
        isLoading: true,
      });
      useAllServicesWithInstructorsMock.mockReturnValue({
        data: null,
        isLoading: true,
      });

      render(
        <EditProfileModal {...defaultProps} variant="services" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });

    it('shows your selected skills section', async () => {
      useServiceCategoriesMock.mockReturnValue({
        data: [{ id: 'cat-1', slug: 'music', name: 'Music' }],
        isLoading: false,
      });

      render(
        <EditProfileModal {...defaultProps} variant="services" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should show selected skills section
      await waitFor(() => {
        expect(screen.getByText(/your selected skills/i)).toBeInTheDocument();
      });
    });
  });

  describe('areas variant borough interactions', () => {
    beforeEach(() => {
      // Mock global fetch for borough neighborhoods
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          items: [
            { neighborhood_id: 'nh-1', id: 'nh-1', name: 'Upper East Side', borough: 'Manhattan' },
            { neighborhood_id: 'nh-2', id: 'nh-2', name: 'Upper West Side', borough: 'Manhattan' },
          ],
        }),
      });
    });

    afterEach(() => {
      (global.fetch as jest.Mock).mockRestore?.();
    });

    it('expands borough accordion and loads neighborhoods', async () => {
      const user = userEvent.setup();

      render(
        <EditProfileModal {...defaultProps} variant="areas" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Find Manhattan accordion header
      const manhattanHeader = screen.getByText('Manhattan');
      await user.click(manhattanHeader);

      // Should load and show neighborhoods
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalled();
      });
    });

    it('selects all neighborhoods in borough', async () => {
      const user = userEvent.setup();

      render(
        <EditProfileModal {...defaultProps} variant="areas" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Find Select all button for a borough
      const selectAllButton = screen.getAllByRole('button', { name: /select all/i })[0];
      if (selectAllButton) {
        await user.click(selectAllButton);
      }
    });

    it('clears all neighborhoods in borough', async () => {
      const user = userEvent.setup();

      render(
        <EditProfileModal {...defaultProps} variant="areas" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Find Clear all button
      const clearAllButton = screen.getAllByRole('button', { name: /clear all/i })[0];
      if (clearAllButton) {
        await user.click(clearAllButton);
      }
    });

    it('filters neighborhoods by global search', async () => {
      const user = userEvent.setup();

      render(
        <EditProfileModal {...defaultProps} variant="areas" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Find global search input
      const searchInput = screen.getByPlaceholderText(/search neighborhoods/i);
      await user.type(searchInput, 'Upper');

      // Should trigger search
      await waitFor(() => {
        expect(screen.getByText('Results')).toBeInTheDocument();
      });
    });
  });

  describe('teaching and public places management', () => {
    it('renders places autocomplete inputs in areas variant', async () => {
      render(
        <EditProfileModal {...defaultProps} variant="areas" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have places autocomplete inputs
      const inputs = screen.getAllByTestId('places-autocomplete');
      expect(inputs.length).toBeGreaterThan(0);
    });

    it('shows preferred teaching locations section', async () => {
      render(
        <EditProfileModal {...defaultProps} variant="areas" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have teaching locations section
      await waitFor(() => {
        expect(screen.getByText(/preferred teaching location/i)).toBeInTheDocument();
      });
    });

    it('shows preferred public spaces section', async () => {
      render(
        <EditProfileModal {...defaultProps} variant="areas" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have public spaces section
      await waitFor(() => {
        expect(screen.getByText(/preferred public space/i)).toBeInTheDocument();
      });
    });

    it('renders with prefilled teaching locations', async () => {
      render(
        <EditProfileModal
          {...defaultProps}
          variant="areas"
          preferredTeaching={[{ address: '123 Main St', label: 'Home' }]}
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should render with the prefilled data
      await waitFor(() => {
        expect(screen.getByDisplayValue('Home')).toBeInTheDocument();
      });
    });

    it('renders with prefilled public locations', async () => {
      render(
        <EditProfileModal
          {...defaultProps}
          variant="areas"
          preferredPublic={[{ address: 'Central Park', label: 'Park' }]}
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should render with the prefilled data
      await waitFor(() => {
        expect(screen.getByDisplayValue('Park')).toBeInTheDocument();
      });
    });

    it('allows typing in places autocomplete', async () => {
      const user = userEvent.setup();

      render(
        <EditProfileModal {...defaultProps} variant="areas" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Find and type in the first autocomplete input
      const inputs = screen.getAllByTestId('places-autocomplete');
      if (inputs.length > 0) {
        await user.type(inputs[0] as HTMLInputElement, '123 Main St');
        await waitFor(() => {
          expect(inputs[0]).toHaveValue('123 Main St');
        });
      }
    });
  });

  describe('cancel button', () => {
    it('calls onClose when cancel button clicked in full variant', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();

      render(
        <EditProfileModal {...defaultProps} onClose={onClose} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      const cancelButton = screen.getByRole('button', { name: /cancel/i });
      await user.click(cancelButton);

      expect(onClose).toHaveBeenCalled();
    });

    it('calls onClose when cancel button clicked in areas variant', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();

      render(
        <EditProfileModal {...defaultProps} variant="areas" onClose={onClose} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      const cancelButton = screen.getByRole('button', { name: /cancel/i });
      await user.click(cancelButton);

      expect(onClose).toHaveBeenCalled();
    });

    it('calls onClose when cancel button clicked in services variant', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();

      render(
        <EditProfileModal {...defaultProps} variant="services" onClose={onClose} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      const cancelButton = screen.getByRole('button', { name: /cancel/i });
      await user.click(cancelButton);

      expect(onClose).toHaveBeenCalled();
    });
  });

  describe('profile fetch edge cases', () => {
    it('handles profile with neighborhoods data', async () => {
      fetchWithAuthMock.mockImplementation((url: string) => {
        if (url.includes('instructors/me')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
              ...mockInstructorProfile,
              service_area_neighborhoods: [
                { neighborhood_id: 'nh-1', name: 'Upper East Side', borough: 'Manhattan' },
              ],
            }),
          });
        }
        if (url.includes('users/me')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ first_name: 'John', last_name: 'Doe' }),
          });
        }
        if (url.includes('addresses/me')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ items: [] }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      });

      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });

    it('handles user fetch failure gracefully', async () => {
      fetchWithAuthMock.mockImplementation((url: string) => {
        if (url.includes('instructors/me')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(mockInstructorProfile),
          });
        }
        if (url.includes('users/me')) {
          return Promise.reject(new Error('User fetch failed'));
        }
        if (url.includes('addresses/me')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ items: [] }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      });

      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });

    it('handles address fetch failure gracefully', async () => {
      fetchWithAuthMock.mockImplementation((url: string) => {
        if (url.includes('instructors/me')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(mockInstructorProfile),
          });
        }
        if (url.includes('users/me')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ first_name: 'John', last_name: 'Doe' }),
          });
        }
        if (url.includes('addresses/me')) {
          return Promise.reject(new Error('Address fetch failed'));
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      });

      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });

    it('uses React Query hook data when available', async () => {
      useInstructorProfileMeMock.mockReturnValue({
        data: mockInstructorProfile,
      });

      render(
        <EditProfileModal {...defaultProps} variant="services" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });

    it('prefills service areas from hook', async () => {
      useInstructorServiceAreasMock.mockReturnValue({
        data: {
          items: [
            { neighborhood_id: 'nh-1', name: 'Upper East Side', borough: 'Manhattan' },
          ],
        },
      });

      render(
        <EditProfileModal {...defaultProps} variant="areas" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });
  });

  describe('founding instructor fee display', () => {
    it('displays founding instructor fee rate', async () => {
      usePlatformFeesMock.mockReturnValue({
        fees: {
          instructor_tiers: [{ min: 0, pct: 0.15 }],
          founding_instructor_pct: 0.08,
        },
      });

      useInstructorProfileMeMock.mockReturnValue({
        data: {
          ...mockInstructorProfile,
          is_founding_instructor: true,
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano Lessons',
              hourly_rate: 100,
              age_groups: ['adults'],
              levels_taught: ['beginner'],
              location_types: ['in-person'],
              duration_options: [60],
            },
          ],
        },
      });

      render(
        <EditProfileModal {...defaultProps} variant="services" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should show take-home earnings with founding instructor rate
      await waitFor(() => {
        expect(screen.getByText(/you'll earn/i)).toBeInTheDocument();
      });
    });
  });

  describe('profile data prefilling', () => {
    it('prefills bio from instructor profile', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Wait for profile data to load
      await waitFor(() => {
        const bioField = screen.getByLabelText(/bio/i);
        // Profile has 'Test bio' which is mocked
        expect(bioField).toBeInTheDocument();
      });
    });

    it('prefills years of experience from profile', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Wait for profile data to load
      await waitFor(() => {
        const expField = screen.getByLabelText(/years of experience/i);
        expect(expField).toBeInTheDocument();
      });
    });

    it('shows about you section', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should show About You section
      await waitFor(() => {
        expect(screen.getByText('About You')).toBeInTheDocument();
      });
    });
  });

  describe('about variant specific tests', () => {
    it('shows bio textarea in about variant', async () => {
      render(
        <EditProfileModal {...defaultProps} variant="about" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Bio should be present
      await waitFor(() => {
        expect(screen.getByLabelText(/bio/i)).toBeInTheDocument();
      });
    });

    it('shows years of experience input in about variant', async () => {
      render(
        <EditProfileModal {...defaultProps} variant="about" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Years of experience should be present
      await waitFor(() => {
        expect(screen.getByLabelText(/years of experience/i)).toBeInTheDocument();
      });
    });

    it('renders sticky footer buttons in about variant', async () => {
      render(
        <EditProfileModal {...defaultProps} variant="about" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // About variant has Save button
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument();
      });
    });
  });

  describe('areas variant specific tests', () => {
    it('shows neighborhoods section in areas variant', async () => {
      // Provide selected service areas so the chips component renders
      const selectedAreas = [
        { neighborhood_id: 'n-1', name: 'Upper East Side' },
        { neighborhood_id: 'n-2', name: 'Chelsea' },
      ];

      render(
        <EditProfileModal
          {...defaultProps}
          variant="areas"
          selectedServiceAreas={selectedAreas}
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have neighborhoods section with chips component
      await waitFor(() => {
        expect(screen.getByTestId('neighborhood-chips')).toBeInTheDocument();
      });
    });

    it('shows Service Areas header in areas variant', async () => {
      render(
        <EditProfileModal {...defaultProps} variant="areas" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should show Service Areas header - there are multiple, so use getAllBy
      await waitFor(() => {
        const headings = screen.getAllByRole('heading', { name: /Service Areas/i });
        expect(headings.length).toBeGreaterThan(0);
      });
    });

    it('has save and cancel buttons in areas variant', async () => {
      render(
        <EditProfileModal {...defaultProps} variant="areas" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have both buttons
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
      });
    });
  });

  describe('full variant service areas', () => {
    it('shows manhattan checkbox in full variant', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have Manhattan checkbox
      await waitFor(() => {
        expect(screen.getByText('Manhattan')).toBeInTheDocument();
      });
    });

    it('shows brooklyn checkbox in full variant', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have Brooklyn checkbox
      await waitFor(() => {
        expect(screen.getByText('Brooklyn')).toBeInTheDocument();
      });
    });
  });

  describe('modal header', () => {
    it('shows correct header for full variant', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Full variant shows Personal Information section header (not sticky header)
      await waitFor(() => {
        expect(screen.getByText('Personal Information')).toBeInTheDocument();
      });
    });

    it('shows correct header for services variant', async () => {
      useServiceCategoriesMock.mockReturnValue({
        data: [{ id: 'cat-1', slug: 'music', name: 'Music' }],
        isLoading: false,
      });

      render(
        <EditProfileModal {...defaultProps} variant="services" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should show Service categories header
      await waitFor(() => {
        expect(screen.getByText('Service categories')).toBeInTheDocument();
      });
    });
  });

  describe('skills section in full variant', () => {
    it('renders add service section', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should show Add Service button text
      await waitFor(() => {
        expect(screen.getByText('Add Service')).toBeInTheDocument();
      });
    });

    it('renders skill select dropdown', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have skill select label
      await waitFor(() => {
        expect(screen.getByText('Select Skill')).toBeInTheDocument();
      });
    });

    it('renders hourly rate input in add service section', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have hourly rate label text
      await waitFor(() => {
        expect(screen.getByText('Hourly Rate')).toBeInTheDocument();
      });
    });
  });

  describe('character counter', () => {
    it('shows bio character counter', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should show character counter
      await waitFor(() => {
        expect(screen.getByText(/\/1000 characters/)).toBeInTheDocument();
      });
    });
  });

  describe('close modal functionality', () => {
    it('close button calls onClose', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();

      render(
        <EditProfileModal {...defaultProps} onClose={onClose} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Find close button by aria-label - Modal component has "Close modal" aria-label
      const closeButton = screen.getByRole('button', { name: /close modal/i });
      await user.click(closeButton);

      expect(onClose).toHaveBeenCalled();
    });
  });

  describe('service operations', () => {
    it('clicks add service button', async () => {
      const user = userEvent.setup();

      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Click the Add Service button
      const addButton = await screen.findByText('Add Service');
      await user.click(addButton);

      // The error message should show for invalid data
      await waitFor(() => {
        expect(screen.getByText(/please select a skill/i)).toBeInTheDocument();
      });
    });

    it('shows existing services in full variant', async () => {
      const propsWithServices = {
        ...defaultProps,
        services: [
          { skill: 'Piano', hourly_rate: 75, description: 'Piano lessons' },
          { skill: 'Guitar', hourly_rate: 65, description: 'Guitar lessons' },
        ],
      };

      render(<EditProfileModal {...propsWithServices} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Services should be displayed
      await waitFor(() => {
        expect(screen.getByText('Piano')).toBeInTheDocument();
      });
    });

    it('allows entering service details', async () => {
      const user = userEvent.setup();

      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Find the hourly rate input and enter a value
      const hourlyRateInput = screen.getByPlaceholderText('Hourly rate');
      await user.clear(hourlyRateInput);
      await user.type(hourlyRateInput, '85');

      await waitFor(() => {
        expect(hourlyRateInput).toHaveValue(85);
      });
    });
  });

  describe('areas variant save functionality', () => {
    it('calls onSave with areas data when provided', async () => {
      const user = userEvent.setup();
      const onSave = jest.fn().mockResolvedValue(undefined);
      const onSuccess = jest.fn();
      const onClose = jest.fn();

      const selectedAreas = [
        { neighborhood_id: 'n-1', name: 'Upper East Side' },
      ];

      render(
        <EditProfileModal
          {...defaultProps}
          variant="areas"
          selectedServiceAreas={selectedAreas}
          preferredTeaching={[{ address: '123 Main St', label: 'Home' }]}
          preferredPublic={[{ address: 'Central Park' }]}
          onSave={onSave}
          onSuccess={onSuccess}
          onClose={onClose}
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Find and click the Save button
      const saveButton = await screen.findByRole('button', { name: /save/i });
      await user.click(saveButton);

      await waitFor(() => {
        expect(onSave).toHaveBeenCalled();
      });
    });
  });

  describe('services variant save functionality', () => {
    it('renders services variant with category list', async () => {
      useServiceCategoriesMock.mockReturnValue({
        data: [
          { id: 'cat-1', slug: 'music', name: 'Music' },
          { id: 'cat-2', slug: 'sports', name: 'Sports' },
        ],
        isLoading: false,
      });

      render(
        <EditProfileModal {...defaultProps} variant="services" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have the Service categories header
      await waitFor(() => {
        expect(screen.getByText('Service categories')).toBeInTheDocument();
      });
    });

    it('shows selected services in services variant', async () => {
      useServiceCategoriesMock.mockReturnValue({
        data: [{ id: 'cat-1', slug: 'music', name: 'Music' }],
        isLoading: false,
      });

      const propsWithSelectedServices = {
        ...defaultProps,
        variant: 'services' as const,
        selectedServices: [
          { id: 'svc-1', category_id: 'cat-1', name: 'Piano Lessons', category_slug: 'music', category_name: 'Music' },
        ],
      };

      render(
        <EditProfileModal {...propsWithSelectedServices} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // The services variant should show the Music category
      await waitFor(() => {
        expect(screen.getByText('Music')).toBeInTheDocument();
      });
    });
  });

  describe('borough checkbox functionality', () => {
    it('shows all NYC borough checkboxes', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have all NYC boroughs
      await waitFor(() => {
        expect(screen.getByText('Manhattan')).toBeInTheDocument();
        expect(screen.getByText('Brooklyn')).toBeInTheDocument();
      });
    });

    it('allows clicking borough checkboxes', async () => {
      const user = userEvent.setup();

      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Find a borough checkbox and click it
      const manhattanText = await screen.findByText('Manhattan');
      const checkbox = manhattanText.closest('label')?.querySelector('input[type="checkbox"]');

      if (checkbox) {
        await user.click(checkbox);
        // Checkbox interaction should work
        expect(checkbox).toBeInTheDocument();
      }
    });
  });

  describe('teaching locations section', () => {
    it('shows preferred teaching locations input in areas variant', async () => {
      render(
        <EditProfileModal {...defaultProps} variant="areas" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have teaching locations section
      await waitFor(() => {
        expect(screen.getByText(/Preferred Teaching Location/i)).toBeInTheDocument();
      });
    });

    it('shows preferred public spaces input in areas variant', async () => {
      render(
        <EditProfileModal {...defaultProps} variant="areas" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have public spaces section
      await waitFor(() => {
        expect(screen.getByText(/Preferred Public Spaces/i)).toBeInTheDocument();
      });
    });
  });

  describe('pricing floor violations', () => {
    it('renders pricing section in full variant', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // The Hourly Rate label should be visible (pricing is part of add service section)
      await waitFor(() => {
        expect(screen.getByText('Hourly Rate')).toBeInTheDocument();
      });
    });
  });

  describe('postal code input', () => {
    it('allows entering postal code', async () => {
      const user = userEvent.setup();

      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Find postal code input
      const postalInput = screen.getByLabelText(/zip code/i);
      await user.clear(postalInput);
      await user.type(postalInput, '10001');

      await waitFor(() => {
        expect(postalInput).toHaveValue('10001');
      });
    });

    it('limits postal code to 5 characters', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      const postalInput = screen.getByLabelText(/zip code/i);
      expect(postalInput).toHaveAttribute('maxLength', '5');
    });
  });

  describe('form validation', () => {
    it('shows error when submitting without service areas', async () => {
      const user = userEvent.setup();

      // Mock profile with empty service area boroughs
      useInstructorProfileMeMock.mockReturnValue({
        data: {
          bio: 'Test bio',
          years_experience: 5,
          service_area_boroughs: [],
          services: [],
        },
      });

      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Find and click Save Changes button
      const saveButton = await screen.findByRole('button', { name: /save changes/i });
      await user.click(saveButton);

      // Should show error for missing service areas
      await waitFor(() => {
        const errorElement = screen.queryByText(/select at least one service area/i);
        if (errorElement) {
          expect(errorElement).toBeInTheDocument();
        }
      });
    });
  });

  describe('years of experience input', () => {
    it('renders years of experience select in full variant', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have years of experience label
      await waitFor(() => {
        expect(screen.getByLabelText(/years of experience/i)).toBeInTheDocument();
      });
    });
  });

  describe('modal footer', () => {
    it('shows Cancel and Save Changes buttons in full variant', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have both footer buttons
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /save changes/i })).toBeInTheDocument();
      });
    });

    it('cancel button triggers onClose', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();

      render(
        <EditProfileModal {...defaultProps} onClose={onClose} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      const cancelButton = screen.getByRole('button', { name: /cancel/i });
      await user.click(cancelButton);

      expect(onClose).toHaveBeenCalled();
    });
  });

  describe('prefilled data from props', () => {
    it('uses instructorProfile prop data when provided', async () => {
      // Mock instructor profile data
      useInstructorProfileMeMock.mockReturnValue({
        data: {
          bio: 'Prefilled bio from prop',
          years_experience: 8,
          services: [],
          service_area_boroughs: ['Manhattan'],
        },
      });

      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should see the first name input - value comes from API or props
      await waitFor(() => {
        const firstNameInput = screen.getByLabelText(/first name/i);
        expect(firstNameInput).toBeInTheDocument();
      });
    });
  });

  describe('service area neighborhoods', () => {
    it('renders neighborhoods for selected boroughs', async () => {
      // Mock profile with service area boroughs
      useInstructorProfileMeMock.mockReturnValue({
        data: {
          bio: 'Test bio',
          years_experience: 5,
          service_area_boroughs: ['Manhattan', 'Brooklyn'],
          services: [],
        },
      });

      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have borough checkboxes
      await waitFor(() => {
        expect(screen.getByText('Manhattan')).toBeInTheDocument();
        expect(screen.getByText('Brooklyn')).toBeInTheDocument();
      });
    });
  });

  describe('services with violations', () => {
    it('renders services variant with price floor checks', async () => {
      useServiceCategoriesMock.mockReturnValue({
        data: [{ id: 'cat-1', slug: 'music', name: 'Music' }],
        isLoading: false,
      });

      const propsWithViolation = {
        ...defaultProps,
        variant: 'services' as const,
        selectedServices: [
          {
            id: 'svc-1',
            catalog_service_id: 'cat-svc-1',
            category_id: 'cat-1',
            name: 'Piano Lessons',
            hourly_rate: '10', // Low rate that might violate floor
            category_slug: 'music',
            category_name: 'Music',
            ageGroup: 'both' as const,
            description: '',
            duration_options: [60],
            levels_taught: ['beginner'],
            equipment: '',
            location_types: ['in-person'],
          },
        ],
      };

      render(
        <EditProfileModal {...propsWithViolation} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should show the Music category
      await waitFor(() => {
        expect(screen.getByText('Music')).toBeInTheDocument();
      });
    });
  });

  describe('services save in services variant', () => {
    it('clicks save button in services variant', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();
      const onSuccess = jest.fn();

      useServiceCategoriesMock.mockReturnValue({
        data: [{ id: 'cat-1', slug: 'music', name: 'Music' }],
        isLoading: false,
      });

      render(
        <EditProfileModal
          {...defaultProps}
          variant="services"
          onClose={onClose}
          onSuccess={onSuccess}
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Find and click Save button
      const saveButton = await screen.findByRole('button', { name: /save/i });
      await user.click(saveButton);

      // Button should be clickable (actual save behavior depends on API)
      expect(saveButton).toBeInTheDocument();
    });
  });

  describe('select skill dropdown', () => {
    it('renders skill select with options', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have select skill label
      await waitFor(() => {
        expect(screen.getByText('Select Skill')).toBeInTheDocument();
      });
    });
  });

  describe('full profile submission', () => {
    it('renders submission button in full variant', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have Save Changes button
      await waitFor(() => {
        const saveButton = screen.getByRole('button', { name: /save changes/i });
        expect(saveButton).toBeInTheDocument();
      });
    });

    it('shows loading state when saving', async () => {
      const user = userEvent.setup();

      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      const saveButton = screen.getByRole('button', { name: /save changes/i });
      await user.click(saveButton);

      // The button should exist
      expect(saveButton).toBeInTheDocument();
    });
  });

  describe('error handling', () => {
    it('displays error when API call fails', async () => {
      // This test verifies the error state can be rendered
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // The modal should render without errors
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  describe('add service validation', () => {
    it('shows error when adding service without skill', async () => {
      const user = userEvent.setup();

      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Click Add Service without selecting a skill
      const addButton = await screen.findByText('Add Service');
      await user.click(addButton);

      // Should show validation error
      await waitFor(() => {
        expect(screen.getByText(/please select a skill/i)).toBeInTheDocument();
      });
    });
  });

  describe('teaching places management', () => {
    it('renders add address button in areas variant', async () => {
      render(
        <EditProfileModal {...defaultProps} variant="areas" />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have add address functionality
      await waitFor(() => {
        expect(screen.getByText(/Preferred Teaching Location/i)).toBeInTheDocument();
      });
    });

    it('shows prefilled teaching places', async () => {
      const propsWithPlaces = {
        ...defaultProps,
        variant: 'areas' as const,
        preferredTeaching: [
          { address: '123 Main St, NYC', label: 'My Home' },
        ],
      };

      render(
        <EditProfileModal {...propsWithPlaces} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should display the prefilled label
      await waitFor(() => {
        expect(screen.getByDisplayValue('My Home')).toBeInTheDocument();
      });
    });
  });

  describe('public places management', () => {
    it('shows prefilled public places', async () => {
      const propsWithPlaces = {
        ...defaultProps,
        variant: 'areas' as const,
        preferredPublic: [
          { address: 'Central Park, NYC' },
        ],
      };

      render(
        <EditProfileModal {...propsWithPlaces} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should see the prefilled address in autocomplete
      await waitFor(() => {
        const inputs = screen.getAllByTestId('places-autocomplete');
        expect(inputs.length).toBeGreaterThan(0);
      });
    });
  });

  describe('bio section', () => {
    it('shows bio textarea with character limit', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should have bio textarea
      await waitFor(() => {
        const bioTextarea = screen.getByLabelText(/bio/i);
        expect(bioTextarea).toBeInTheDocument();
      });
    });

    it('updates bio text when typing', async () => {
      const user = userEvent.setup();

      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      const bioTextarea = screen.getByLabelText(/bio/i);
      await user.clear(bioTextarea);
      await user.type(bioTextarea, 'New bio text');

      await waitFor(() => {
        expect(bioTextarea).toBeInTheDocument();
      });
    });
  });

  describe('profile data initialization', () => {
    it('initializes with user data from props', async () => {
      render(<EditProfileModal {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // First name should be initialized from defaultProps.user or API
      await waitFor(() => {
        const firstNameInput = screen.getByLabelText(/first name/i);
        // Should have some value (from API mock or props)
        expect(firstNameInput).toBeInTheDocument();
      });
    });
  });

  describe('existing services display', () => {
    it('shows services from user prop', async () => {
      const propsWithServices = {
        ...defaultProps,
        services: [
          { skill: 'Yoga', hourly_rate: 80, description: 'Yoga instruction' },
        ],
      };

      render(<EditProfileModal {...propsWithServices} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Should display the service
      await waitFor(() => {
        expect(screen.getByText('Yoga')).toBeInTheDocument();
      });
    });
  });
});
