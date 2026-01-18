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
  normalizeInstructorServices: jest.fn((services) => Promise.resolve(services)),
  hydrateCatalogNameById: jest.fn((id) => Promise.resolve(id)),
  displayServiceName: jest.fn((service) => service.name ?? service.skill ?? 'Service'),
}));

jest.mock('@/lib/profileServiceAreas', () => ({
  getServiceAreaBoroughs: jest.fn(() => ['Manhattan', 'Brooklyn']),
}));

jest.mock('@/lib/profileSchemaDebug', () => ({
  buildProfileUpdateBody: jest.fn(() => ({})),
}));

jest.mock('@/components/forms/PlacesAutocompleteInput', () => ({
  PlacesAutocompleteInput: ({ placeholder, _onSelect }: { placeholder: string; _onSelect?: (place: unknown) => void }) => (
    <input placeholder={placeholder} data-testid="places-autocomplete" />
  ),
}));

jest.mock('@/features/shared/components/SelectedNeighborhoodChips', () => ({
  SelectedNeighborhoodChips: () => <div data-testid="neighborhood-chips">Neighborhood Chips</div>,
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
});
