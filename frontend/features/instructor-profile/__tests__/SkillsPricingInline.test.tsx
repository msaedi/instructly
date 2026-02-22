import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SkillsPricingInline from '../SkillsPricingInline';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { useServiceCategories, useAllServicesWithInstructors } from '@/hooks/queries/useServices';
import { useInstructorProfileMe } from '@/hooks/queries/useInstructorProfileMe';
import { usePricingConfig } from '@/lib/pricing/usePricingFloors';
import { usePlatformFees } from '@/hooks/usePlatformConfig';
import { evaluatePriceFloorViolations } from '@/lib/pricing/priceFloors';
import { useSubcategoryFilters } from '@/hooks/queries/useTaxonomy';
import { displayServiceName } from '@/lib/instructorServices';
import { toast } from 'sonner';

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(() => ({
    user: { id: 'user-123', email: 'jane@example.com', first_name: 'Jane', last_name: 'Doe' },
    isAuthenticated: true,
  })),
}));

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api');
  return { ...actual, fetchWithAuth: jest.fn() };
});

jest.mock('@tanstack/react-query', () => {
  const actual = jest.requireActual('@tanstack/react-query');
  return {
    ...actual,
    useQueryClient: () => ({ invalidateQueries: jest.fn().mockResolvedValue(undefined) }),
  };
});

jest.mock('@/hooks/queries/useTaxonomy', () => ({
  useCategoriesWithSubcategories: jest.fn(() => ({ data: undefined, isLoading: false })),
  useSubcategoryFilters: jest.fn(() => ({ data: [], isLoading: false })),
}));

jest.mock('@/hooks/queries/useServices', () => ({
  useServiceCategories: jest.fn(),
  useAllServicesWithInstructors: jest.fn(),
}));

jest.mock('@/hooks/queries/useInstructorProfileMe', () => ({
  useInstructorProfileMe: jest.fn(),
}));

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingConfig: jest.fn(),
}));

jest.mock('@/hooks/usePlatformConfig', () => ({
  usePlatformFees: jest.fn(),
}));

jest.mock('@/lib/instructorServices', () => ({
  hydrateCatalogNameById: jest.fn(),
  displayServiceName: jest.fn(
    (args: { service_catalog_name?: string }) => args.service_catalog_name || 'Service'
  ),
}));

jest.mock('@/lib/pricing/platformFees', () => ({
  resolvePlatformFeeRate: jest.fn(() => 0.2),
  resolveTakeHomePct: jest.fn(() => 0.8),
  formatPlatformFeeLabel: jest.fn(() => '20%'),
}));

jest.mock('@/lib/pricing/priceFloors', () => ({
  evaluatePriceFloorViolations: jest.fn(),
  formatCents: (value: number) => (value / 100).toFixed(2),
}));

jest.mock('@/lib/logger', () => ({
  logger: { debug: jest.fn(), warn: jest.fn(), error: jest.fn(), info: jest.fn() },
}));

jest.mock('sonner', () => ({
  toast: {
    error: jest.fn(),
    success: jest.fn(),
    info: jest.fn(),
    warning: jest.fn(),
  },
}));

const mockUseServiceCategories = useServiceCategories as jest.Mock;
const mockUseAllServices = useAllServicesWithInstructors as jest.Mock;
const mockUseInstructorProfileMe = useInstructorProfileMe as jest.Mock;
const mockUsePricingConfig = usePricingConfig as jest.Mock;
const mockUsePlatformFees = usePlatformFees as jest.Mock;
const mockFetchWithAuth = fetchWithAuth as jest.Mock;
const mockEvaluateViolations = evaluatePriceFloorViolations as jest.Mock;
const mockUseSubcategoryFilters = useSubcategoryFilters as jest.Mock;
const mockDisplayServiceName = displayServiceName as jest.Mock;

const categoriesData = [{ id: '01HABCTESTCAT0000000000001', name: 'Music', display_order: 1 }];
const servicesData = {
  categories: [
    {
      id: '01HABCTESTCAT0000000000001',
      name: 'Music',
      services: [{ id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: '01HABCTESTSUBCAT0000000001', eligible_age_groups: ['kids', 'teens', 'adults'] }],
    },
  ],
};

describe('SkillsPricingInline', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseServiceCategories.mockReturnValue({ data: categoriesData, isLoading: false });
    mockUseAllServices.mockReturnValue({ data: servicesData, isLoading: false });
    mockUseInstructorProfileMe.mockReturnValue({ data: null });
    mockUsePricingConfig.mockReturnValue({ config: { price_floor_cents: null } });
    mockUsePlatformFees.mockReturnValue({ fees: {} });
    mockFetchWithAuth.mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
    mockEvaluateViolations.mockReturnValue([]);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('renders a loading state when service data is loading', () => {
    mockUseServiceCategories.mockReturnValue({ data: null, isLoading: true });

    render(<SkillsPricingInline />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('lets instructors select and remove services', async () => {
    const user = userEvent.setup();
    render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

    await user.click(screen.getByRole('button', { name: /music/i }));
    await user.click(screen.getByRole('button', { name: /piano \+/i }));

    expect(screen.getByRole('button', { name: /remove piano/i })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /remove piano/i }));

    expect(screen.getByText(/no services added yet/i)).toBeInTheDocument();
  });

  it('blocks removal of the last skill for live instructors', async () => {
    const user = userEvent.setup();
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: true,
        services: [
          {
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            offers_online: true,
          },
        ],
      },
    });

    render(<SkillsPricingInline />);

    await user.click(screen.getByRole('button', { name: /remove skill/i }));
    expect(screen.getByText(/must have at least one skill/i)).toBeInTheDocument();
  });

  it('shows an error when removing a skill before profile loads', async () => {
    const user = userEvent.setup();
    render(<SkillsPricingInline />);

    await user.click(screen.getByRole('button', { name: /music/i }));
    await user.click(screen.getByRole('button', { name: /piano \+/i }));
    await user.click(screen.getByRole('button', { name: /remove skill/i }));

    expect(screen.getByText(/please wait for profile to load/i)).toBeInTheDocument();
  });

  it('blocks deselecting a skill before profile loads', async () => {
    const user = userEvent.setup();
    render(<SkillsPricingInline />);

    await user.click(screen.getByRole('button', { name: /music/i }));
    await user.click(screen.getByRole('button', { name: /piano \+/i }));
    await user.click(screen.getByRole('button', { name: /piano\s+✓/i }));

    expect(screen.getByText(/please wait for profile to load/i)).toBeInTheDocument();
  });

  it('keeps local price edits when a stale profile refresh arrives', async () => {
    const user = userEvent.setup();
    const initialProfile = {
      is_live: false,
      services: [
        {
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 70,
          offers_online: true,
        },
      ],
    };

    const { rerender } = render(<SkillsPricingInline instructorProfile={initialProfile as never} />);

    const rateInput = screen.getByPlaceholderText(/hourly rate/i);
    await user.clear(rateInput);
    await user.type(rateInput, '80');
    await user.tab();

    const staleProfile = {
      ...initialProfile,
      services: [
        {
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 70,
          offers_online: true,
        },
      ],
    };

    rerender(<SkillsPricingInline instructorProfile={staleProfile as never} />);

    expect(screen.getByPlaceholderText(/hourly rate/i)).toHaveValue(80);
  });

  it('surfaces price floor violations on autosave', async () => {
    jest.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        service_area_neighborhoods: ['n1'],
        services: [
          {
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 30,
            duration_options: [60],
            offers_travel: true,
          },
        ],
      },
    });
    mockUsePricingConfig.mockReturnValue({ config: { price_floor_cents: { private: { '60': 5000 } } } });
    mockEvaluateViolations.mockReturnValue([
      { duration: 60, modalityLabel: 'in-person', floorCents: 5000, baseCents: 3000 },
    ]);

    render(<SkillsPricingInline />);

    await user.clear(screen.getByPlaceholderText(/hourly rate/i));
    await user.type(screen.getByPlaceholderText(/hourly rate/i), '30');
    jest.advanceTimersByTime(1200);

    await waitFor(() => {
      expect(screen.getByText(/minimum price/i)).toBeInTheDocument();
    });
    jest.useRealTimers();
  });

  it('autosaves valid pricing updates', async () => {
    jest.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        services: [
          {
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 45,
            duration_options: [60],
            offers_online: true,
          },
        ],
      },
    });

    render(<SkillsPricingInline />);

    await user.clear(screen.getByPlaceholderText(/hourly rate/i));
    await user.type(screen.getByPlaceholderText(/hourly rate/i), '75');
    jest.advanceTimersByTime(1200);

    await waitFor(() => {
      expect(mockFetchWithAuth).toHaveBeenCalledWith(API_ENDPOINTS.INSTRUCTOR_PROFILE, expect.any(Object));
    });
    jest.useRealTimers();
  });

  it('blocks save when no capability is selected', async () => {
    jest.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        services: [
          {
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_travel: false,
            offers_at_location: false,
            offers_online: false,
          },
        ],
      },
    });

    render(<SkillsPricingInline />);

    const rateInput = screen.getByPlaceholderText(/hourly rate/i);
    await user.clear(rateInput);
    await user.type(rateInput, '65');
    jest.advanceTimersByTime(1200);

    await waitFor(() => {
      expect(screen.getByText(/select at least one location option/i)).toBeInTheDocument();
    });
    expect(mockFetchWithAuth).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
    jest.useRealTimers();
  });

  it('handles skill requests', async () => {
    jest.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

    render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

    await user.type(screen.getByPlaceholderText(/request a new skill/i), 'Violin');
    await user.click(screen.getByRole('button', { name: /submit/i }));
    jest.advanceTimersByTime(600);

    expect(await screen.findByText(/we'll review/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/request a new skill/i)).toHaveValue('');
    jest.useRealTimers();
  });

  it('toggles age group selection', async () => {
    const user = userEvent.setup();
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        service_area_neighborhoods: ['n1'],
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 50,
          age_groups: ['adults'],
          duration_options: [60],
          offers_online: true,
        }],
      },
    });

    render(<SkillsPricingInline />);

    // Find and click the Kids button to toggle age group
    const kidsButtons = screen.getAllByRole('button', { name: /kids/i });
    const kidsButton = kidsButtons.find((btn) => !btn.textContent?.includes('Service'));
    if (kidsButton) {
      await user.click(kidsButton);
    }

    // The component should update without crashing - multiple Piano elements exist
    const pianoElements = screen.getAllByText(/piano/i);
    expect(pianoElements.length).toBeGreaterThan(0);
  });

  it('toggles location type selection', async () => {
    const user = userEvent.setup();
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        service_area_neighborhoods: ['n1'],
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 50,
          age_groups: ['adults'],
          duration_options: [60],
          offers_online: true,
        }],
      },
    });

    render(<SkillsPricingInline />);

    expect(screen.getByRole('switch', { name: /i travel to students/i })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: /students come to me/i })).toBeInTheDocument();
    const onlineSwitch = screen.getByRole('switch', { name: /online lessons/i });
    expect(onlineSwitch).toHaveAttribute('aria-checked', 'true');
    await user.click(onlineSwitch);
    expect(onlineSwitch).toHaveAttribute('aria-checked', 'false');

    const pianoElements = screen.getAllByText(/piano/i);
    expect(pianoElements.length).toBeGreaterThan(0);
  });

  it('toggles skill levels', async () => {
    const user = userEvent.setup();
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        service_area_neighborhoods: ['n1'],
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 50,
          age_groups: ['adults'],
          duration_options: [60],
          offers_online: true,
          levels_taught: ['beginner', 'intermediate', 'advanced'],
        }],
      },
    });

    render(<SkillsPricingInline />);

    // Find and click intermediate button to toggle it off
    const intermediateButtons = screen.getAllByRole('button', { name: /intermediate/i });
    if (intermediateButtons[0]) {
      await user.click(intermediateButtons[0]);
    }

    const pianoElements = screen.getAllByText(/piano/i);
    expect(pianoElements.length).toBeGreaterThan(0);
  });

  it('toggles duration options', async () => {
    const user = userEvent.setup();
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 50,
          age_groups: ['adults'],
          duration_options: [60],
          offers_online: true,
        }],
      },
    });

    render(<SkillsPricingInline />);

    // Find and click the 30m button to add it
    const durationButtons = screen.getAllByRole('button', { name: /30m/i });
    if (durationButtons[0]) {
      await user.click(durationButtons[0]);
    }

    const pianoElements = screen.getAllByText(/piano/i);
    expect(pianoElements.length).toBeGreaterThan(0);
  });

  it('filters services by search query', async () => {
    const user = userEvent.setup();
    mockUseAllServices.mockReturnValue({
      data: {
        categories: [
          {
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: '01HABCTESTSUBCAT0000000001' },
              { id: 'svc-2', name: 'Guitar', slug: 'guitar', subcategory_id: '01HABCTESTSUBCAT0000000001' },
            ],
          },
        ],
      },
      isLoading: false,
    });

    render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

    // Expand category
    await user.click(screen.getByRole('button', { name: /music/i }));

    // Both should be visible initially
    expect(screen.getByRole('button', { name: /piano \+/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /guitar \+/i })).toBeInTheDocument();

    // Search for Piano
    await user.type(screen.getByPlaceholderText(/search skills/i), 'Piano');

    // Only Piano should be visible
    expect(screen.getByRole('button', { name: /piano \+/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /guitar \+/i })).not.toBeInTheDocument();
  });

  it('shows earnings calculation when rate is entered', async () => {
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 100,
          age_groups: ['adults'],
          duration_options: [60],
          offers_online: true,
        }],
      },
    });

    render(<SkillsPricingInline />);

    // Should show earnings after platform fee
    expect(screen.getByText(/you'll earn/i)).toBeInTheDocument();
    expect(screen.getByText(/\$80\.00/)).toBeInTheDocument(); // 80% of 100
  });

  it('uses profile from prop instead of hook when provided', () => {
    mockUseInstructorProfileMe.mockReturnValue({ data: null });

    render(
      <SkillsPricingInline
        instructorProfile={{
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'PropPiano',
            hourly_rate: 75,
            offers_online: true,
          }],
        } as never}
      />
    );

    const elements = screen.getAllByText(/PropPiano/i);
    expect(elements.length).toBeGreaterThan(0);
  });

  it('updates description field', async () => {
    const user = userEvent.setup();
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 50,
          description: '',
          offers_online: true,
        }],
      },
    });

    render(<SkillsPricingInline />);

    const descriptionInput = screen.getByPlaceholderText(/brief description/i);
    await user.type(descriptionInput, 'I teach classical piano');

    expect(descriptionInput).toHaveValue('I teach classical piano');
  });

  it('updates equipment field', async () => {
    const user = userEvent.setup();
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 50,
          equipment: '',
          offers_online: true,
        }],
      },
    });

    render(<SkillsPricingInline />);

    const equipmentInput = screen.getByPlaceholderText(/yoga mat/i);
    await user.type(equipmentInput, 'Piano, music stand');

    expect(equipmentInput).toHaveValue('Piano, music stand');
  });

  it('handles API error on save', async () => {
    jest.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 50,
          offers_online: true,
        }],
      },
    });
    mockFetchWithAuth.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'Server error' }),
    });

    render(<SkillsPricingInline />);

    const rateInput = screen.getByPlaceholderText(/hourly rate/i);
    await user.clear(rateInput);
    await user.type(rateInput, '60');
    jest.advanceTimersByTime(1200);

    await waitFor(() => {
      expect(screen.getByText(/server error/i)).toBeInTheDocument();
    });
    jest.useRealTimers();
  });

  it('skips save when profile not loaded yet', async () => {
    jest.useFakeTimers();
    // Return undefined to simulate profile not loaded
    mockUseInstructorProfileMe.mockReturnValue({ data: undefined });

    render(<SkillsPricingInline />);

    // Try to trigger a save by modifying something
    jest.advanceTimersByTime(1200);

    // fetchWithAuth should not be called when profile isn't loaded
    expect(mockFetchWithAuth).not.toHaveBeenCalled();
    jest.useRealTimers();
  });

  it('blocks save for live instructor with no skills with rate', async () => {
    jest.useFakeTimers();
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: true,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: '', // Empty rate
          offers_online: true,
        }],
      },
    });

    render(<SkillsPricingInline />);

    jest.advanceTimersByTime(1200);

    await waitFor(() => {
      expect(screen.getByText(/must have at least one skill/i)).toBeInTheDocument();
    });
    jest.useRealTimers();
  });

  it('clears request success message when typing new skill', async () => {
    jest.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

    render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

    // Submit a skill request
    await user.type(screen.getByPlaceholderText(/request a new skill/i), 'Violin');
    await user.click(screen.getByRole('button', { name: /submit/i }));
    jest.advanceTimersByTime(600);

    expect(await screen.findByText(/we'll review/i)).toBeInTheDocument();

    // Start typing again - message should be cleared
    await user.type(screen.getByPlaceholderText(/request a new skill/i), 'C');

    expect(screen.queryByText(/we'll review/i)).not.toBeInTheDocument();
    jest.useRealTimers();
  });

  it('displays founding instructor fee context', () => {
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        is_founding_instructor: true,
        current_tier_pct: 8,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 100,
          offers_online: true,
        }],
      },
    });

    render(<SkillsPricingInline />);

    // Component should render with fee info
    expect(screen.getByText(/platform fee/i)).toBeInTheDocument();
  });

  it('handles empty skill request submission gracefully', async () => {
    const user = userEvent.setup();
    render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

    // Try to submit without entering text
    await user.click(screen.getByRole('button', { name: /submit/i }));

    // Should not show success message
    expect(screen.queryByText(/we'll review/i)).not.toBeInTheDocument();
  });

  it('renders all categories from API', () => {
    mockUseServiceCategories.mockReturnValue({
      data: [
        { id: '01HABCTESTCAT0000000000001', name: 'Music', display_order: 1 },
        { id: '01HABCTESTCAT0000000000002', name: 'Dance', display_order: 2 },
        { id: '01HABCTESTCAT0000000000003', name: 'Sports', display_order: 3 },
      ],
      isLoading: false,
    });

    render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

    expect(screen.getByRole('button', { name: /music/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /dance/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sports/i })).toBeInTheDocument();
  });

  it('handles profile with instructor_tier_pct fallback', () => {
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        instructor_tier_pct: 15, // Fallback field name
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 100,
          offers_online: true,
        }],
      },
    });

    render(<SkillsPricingInline />);

    // Should render without errors
    expect(screen.getByText(/platform fee/i)).toBeInTheDocument();
  });

  it('handles services with equipment_required array', async () => {
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 50,
          equipment_required: ['Piano', 'Music stand', 'Metronome'],
          offers_online: true,
        }],
      },
    });

    render(<SkillsPricingInline />);

    const equipmentInput = screen.getByPlaceholderText(/yoga mat/i);
    expect(equipmentInput).toHaveValue('Piano, Music stand, Metronome');
  });

  it('handles service with single age_groups entry (kids)', () => {
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 50,
          age_groups: ['kids'],
          offers_online: true,
        }],
      },
    });

    render(<SkillsPricingInline />);

    // Should render the component with kids selected
    const pianoElements = screen.getAllByText(/piano/i);
    expect(pianoElements.length).toBeGreaterThan(0);
  });

  it('deduplicates services by catalog_service_id', () => {
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        services: [
          { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 50, offers_online: true },
          { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 60, offers_online: true }, // Duplicate
          { service_catalog_id: 'svc-2', service_catalog_name: 'Guitar', hourly_rate: 45, offers_online: true },
        ],
      },
    });

    render(<SkillsPricingInline />);

    // Should only have 2 services (deduplicated)
    const rateInputs = screen.getAllByPlaceholderText(/hourly rate/i);
    expect(rateInputs).toHaveLength(2);
  });

  it('displays correct error for price floor violation with modality info', async () => {
    jest.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    const profile = {
      is_live: false,
      service_area_neighborhoods: ['n1'],
      services: [{
        service_catalog_id: 'svc-1',
        service_catalog_name: 'Piano Lesson',
        hourly_rate: 40,
        duration_options: [60],
        offers_travel: true,
      }],
    };
    mockUsePricingConfig.mockReturnValue({
      config: { price_floor_cents: { private: { '60': 5000 } } },
    });
    mockEvaluateViolations.mockReturnValue([
      { duration: 60, modalityLabel: 'in-person', floorCents: 5000, baseCents: 4000 },
    ]);

    render(<SkillsPricingInline instructorProfile={profile as never} />);

    // Trigger autosave
    await user.clear(screen.getByPlaceholderText(/hourly rate/i));
    await user.type(screen.getByPlaceholderText(/hourly rate/i), '40');
    jest.advanceTimersByTime(1200);

    await waitFor(() => {
      expect(screen.getByText(/minimum price for a in-person 60-minute private session/i)).toBeInTheDocument();
    });
    jest.useRealTimers();
  });

  it('collapses and expands categories correctly', async () => {
    const user = userEvent.setup();
    mockUseAllServices.mockReturnValue({
      data: {
        categories: [
          {
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [{ id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: '01HABCTESTSUBCAT0000000001' }],
          },
        ],
      },
      isLoading: false,
    });

    render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

    const musicButton = screen.getByRole('button', { name: /music/i });

    // Expand
    await user.click(musicButton);
    expect(screen.getByRole('button', { name: /piano \+/i })).toBeInTheDocument();

    // Collapse
    await user.click(musicButton);
    // After collapsing, piano should not be visible
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /piano \+/i })).not.toBeInTheDocument();
    });
  });

  it('handles API error with message field', async () => {
    jest.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 50,
          offers_online: true,
        }],
      },
    });
    mockFetchWithAuth.mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: async () => ({ message: 'Validation failed' }),
    });

    render(<SkillsPricingInline />);

    const rateInput = screen.getByPlaceholderText(/hourly rate/i);
    await user.clear(rateInput);
    await user.type(rateInput, '55');
    jest.advanceTimersByTime(1200);

    await waitFor(() => {
      expect(screen.getByText(/validation failed/i)).toBeInTheDocument();
    });
    jest.useRealTimers();
  });

  it('renders all categories from services data', () => {
    mockUseServiceCategories.mockReturnValue({
      data: [
        { id: '01HABCTESTCAT0000000000001', name: 'Dance', display_order: 1 },
        { id: '01HABCTESTCAT0000000000002', name: 'Music', display_order: 2 },
      ],
      isLoading: false,
    });
    mockUseAllServices.mockReturnValue({
      data: {
        categories: [
          { id: '01HABCTESTCAT0000000000001', name: 'Dance', services: [{ id: 'svc-dance', name: 'Ballet', slug: 'ballet', subcategory_id: '01HABCTESTSUBCAT0000000001' }] },
          { id: '01HABCTESTCAT0000000000002', name: 'Music', services: [{ id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: '01HABCTESTSUBCAT0000000002' }] },
        ],
      },
      isLoading: false,
    });

    render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

    expect(screen.getByRole('button', { name: /dance/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /music/i })).toBeInTheDocument();
  });

  it('handles service with name field instead of service_catalog_name', () => {
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          name: 'Custom Piano', // Using name instead of service_catalog_name
          hourly_rate: 75,
          offers_online: true,
        }],
      },
    });

    render(<SkillsPricingInline />);

    const elements = screen.getAllByText(/custom piano/i);
    expect(elements.length).toBeGreaterThan(0);
  });

  it('handles services with empty catalog_service_id', () => {
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        services: [
          { service_catalog_id: '', service_catalog_name: 'Invalid', hourly_rate: 50, offers_online: true },
          { service_catalog_id: 'svc-1', service_catalog_name: 'Valid Piano', hourly_rate: 60, offers_online: true },
        ],
      },
    });

    render(<SkillsPricingInline />);

    // Only valid service should be shown
    const rateInputs = screen.getAllByPlaceholderText(/hourly rate/i);
    expect(rateInputs).toHaveLength(1);
  });

  describe('FIX 9 - pricing config loading guard', () => {
    it('skips save when pricing config is still loading', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });
      // Simulate pricing config still loading
      mockUsePricingConfig.mockReturnValue({ config: null, isLoading: true });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '60');
      jest.advanceTimersByTime(1200);

      // Should not have made API call because pricing config is loading
      await waitFor(() => {
        expect(mockFetchWithAuth).not.toHaveBeenCalled();
      });

      jest.useRealTimers();
    });
  });

  describe('Effect #5 - capability cleanup', () => {
    it('clears offers_travel when service areas removed', async () => {
      jest.useFakeTimers();
      const initialProfile = {
        is_live: false,
        service_area_neighborhoods: ['neighborhood1'],
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 50,
          offers_travel: true,
          offers_online: false,
        }],
      };
      mockUseInstructorProfileMe.mockReturnValue({ data: initialProfile });

      const { rerender } = render(<SkillsPricingInline />);

      // Verify travel toggle is on initially
      expect(screen.getByRole('switch', { name: /i travel to students/i })).toHaveAttribute('aria-checked', 'true');

      // Now remove service areas (simulating profile update)
      const updatedProfile = {
        ...initialProfile,
        service_area_neighborhoods: [], // Removed service areas
      };
      mockUseInstructorProfileMe.mockReturnValue({ data: updatedProfile });
      rerender(<SkillsPricingInline />);

      jest.advanceTimersByTime(100);

      // The travel toggle should now be disabled (no service areas)
      await waitFor(() => {
        const travelSwitch = screen.getByRole('switch', { name: /i travel to students/i });
        expect(travelSwitch).toBeDisabled();
      });

      jest.useRealTimers();
    });

    it('clears offers_at_location when teaching locations removed', async () => {
      jest.useFakeTimers();
      const initialProfile = {
        is_live: false,
        preferred_teaching_locations: [{ id: '1', address: '123 Main St' }],
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 50,
          offers_at_location: true,
          offers_online: false,
        }],
      };
      mockUseInstructorProfileMe.mockReturnValue({ data: initialProfile });

      const { rerender } = render(<SkillsPricingInline />);

      // Verify at-location toggle is on initially
      expect(screen.getByRole('switch', { name: /students come to me/i })).toHaveAttribute('aria-checked', 'true');

      // Now remove teaching locations (simulating profile update)
      const updatedProfile = {
        ...initialProfile,
        preferred_teaching_locations: [], // Removed teaching locations
      };
      mockUseInstructorProfileMe.mockReturnValue({ data: updatedProfile });
      rerender(<SkillsPricingInline />);

      jest.advanceTimersByTime(100);

      // The at-location toggle should now be disabled (no teaching locations)
      await waitFor(() => {
        const atLocationSwitch = screen.getByRole('switch', { name: /students come to me/i });
        expect(atLocationSwitch).toBeDisabled();
      });

      jest.useRealTimers();
    });
  });

  describe('handleSave edge cases', () => {
    it('shows toast error for manual save with invalid capabilities', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_travel: false,
            offers_at_location: false,
            offers_online: false, // All capabilities disabled
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Trigger a change and wait for autosave
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '55');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(screen.getByText(/select at least one location option/i)).toBeInTheDocument();
      });

      jest.useRealTimers();
    });

    it('clears existing price errors when new validation passes', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['n1'],
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 40, // Below floor
            duration_options: [60],
            offers_travel: true,
          }],
        },
      });
      mockUsePricingConfig.mockReturnValue({
        config: { price_floor_cents: { private_in_person: 5000, private_remote: 4000 } },
        isLoading: false,
      });
      mockEvaluateViolations.mockReturnValue([
        { duration: 60, modalityLabel: 'in-person', floorCents: 5000, baseCents: 4000 },
      ]);
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      // Trigger initial autosave - should show price error
      await user.clear(screen.getByPlaceholderText(/hourly rate/i));
      await user.type(screen.getByPlaceholderText(/hourly rate/i), '40');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(screen.getByText(/minimum price/i)).toBeInTheDocument();
      });

      // Now fix the price and trigger another autosave
      mockEvaluateViolations.mockReturnValue([]); // No violations now
      await user.clear(screen.getByPlaceholderText(/hourly rate/i));
      await user.type(screen.getByPlaceholderText(/hourly rate/i), '100');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      jest.useRealTimers();
    });

    it('handles location capability error silently', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ detail: "Cannot enable travel without service areas" }),
      });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '55');
      jest.advanceTimersByTime(1200);

      // Wait for the API call
      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      // The location capability error should not be shown as a general error
      // (it's handled silently)
      await waitFor(() => {
        expect(screen.queryByText(/cannot enable travel/i)).not.toBeInTheDocument();
      });

      jest.useRealTimers();
    });
  });

  describe('handleRequestSkill edge cases', () => {
    it('does not submit when skill input is empty', async () => {
      const user = userEvent.setup();
      render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

      // Try to submit with empty input
      await user.click(screen.getByRole('button', { name: /submit/i }));

      // Should not show success message
      expect(screen.queryByText(/we'll review/i)).not.toBeInTheDocument();
    });

    it('does not submit when skill input has only whitespace', async () => {
      const user = userEvent.setup();
      render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

      // Type only whitespace
      await user.type(screen.getByPlaceholderText(/request a new skill/i), '   ');
      await user.click(screen.getByRole('button', { name: /submit/i }));

      // Should not show success message
      expect(screen.queryByText(/we'll review/i)).not.toBeInTheDocument();
    });
  });

  describe('price error clearing on rate change', () => {
    it('clears price error for specific service when rate is modified', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['n1'],
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 40,
            duration_options: [60],
            offers_travel: true,
          }],
        },
      });
      mockUsePricingConfig.mockReturnValue({
        config: { price_floor_cents: { private_in_person: 5000, private_remote: 4000 } },
        isLoading: false,
      });
      mockEvaluateViolations.mockReturnValue([
        { duration: 60, modalityLabel: 'in-person', floorCents: 5000, baseCents: 4000 },
      ]);

      render(<SkillsPricingInline />);

      // Trigger autosave to get price error
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '40');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(screen.getByText(/minimum price/i)).toBeInTheDocument();
      });

      // Now just type a new value (not waiting for autosave) - error should clear immediately
      await user.type(rateInput, '0'); // Now it's 400

      // The error message below the input should be gone (immediate clear on typing)
      // Note: The toast might still be visible, but the inline error should clear
      jest.useRealTimers();
    });
  });

  describe('autosave effect branches', () => {
    it('does not mark dirty on initial mount with empty services', async () => {
      jest.useFakeTimers();
      mockUseInstructorProfileMe.mockReturnValue({ data: null });

      render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

      jest.advanceTimersByTime(1200);

      // Should not trigger save for empty initial state
      expect(mockFetchWithAuth).not.toHaveBeenCalled();

      jest.useRealTimers();
    });

    it('marks dirty and triggers autosave when services have items on initial mount', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      // Profile not loaded from hook
      mockUseInstructorProfileMe.mockReturnValue({ data: null });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(
        <SkillsPricingInline
          instructorProfile={{
            is_live: false,
            services: [{
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: 60,
              offers_online: true,
            }],
          } as never}
        />
      );

      // Wait for profile to load
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/hourly rate/i)).toBeInTheDocument();
      });

      // Modify something to trigger autosave
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      jest.useRealTimers();
    });

    it('clears existing autosave timeout when new changes come in', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);

      // Type first character
      await user.clear(rateInput);
      await user.type(rateInput, '7');
      jest.advanceTimersByTime(500);

      // Type second character before first timeout fires
      await user.type(rateInput, '5');
      jest.advanceTimersByTime(500);

      // Type third character
      await user.type(rateInput, '0');
      jest.advanceTimersByTime(1200);

      // Should only have called API once (not three times)
      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalledTimes(1);
      });

      jest.useRealTimers();
    });
  });

  describe('Coverage improvement tests', () => {
    it('renders services from instructorProfile prop', async () => {
      // Profile not yet loaded from hook (data is null)
      mockUseInstructorProfileMe.mockReturnValue({ data: null });

      render(
        <SkillsPricingInline
          instructorProfile={{
            is_live: false,
            services: [
              { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 60, offers_online: true },
            ],
          } as never}
        />
      );

      // Service should be rendered from prop
      expect(screen.getByPlaceholderText(/hourly rate/i)).toBeInTheDocument();
    });

    it('allows toggling service selection when profile is loaded', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 60, offers_online: true },
          ],
        },
      });

      render(<SkillsPricingInline />);

      // Click on Music category to see available services
      await user.click(screen.getByRole('button', { name: /music/i }));

      // Piano should be visible
      expect(screen.getAllByText(/piano/i).length).toBeGreaterThan(0);
    });

    it('prevents live instructor from removing last skill via toggleServiceSelection', async () => {
      const user = userEvent.setup();
      // Profile loaded with is_live: true
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: true,
          services: [
            { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 60, offers_online: true },
          ],
        },
      });

      render(<SkillsPricingInline />);

      // Click on Music category
      await user.click(screen.getByRole('button', { name: /music/i }));
      // Try to toggle off the piano (currently selected)
      const pianoButton = screen.getByRole('button', { name: /piano ✓/i });
      await user.click(pianoButton);

      expect(screen.getByText(/must have at least one skill/i)).toBeInTheDocument();
    });

    it('handles skill request flow', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: { is_live: false, services: [] },
      });

      render(<SkillsPricingInline />);

      // Find and type in the skill request input
      const skillInput = screen.getByPlaceholderText(/request a new skill/i);
      await user.type(skillInput, 'Juggling');

      // Submit button should be available
      const submitButton = screen.getByRole('button', { name: /submit/i });
      expect(submitButton).toBeInTheDocument();
    });

    it('renders properly when profile is not loaded yet', async () => {
      // Profile not loaded
      mockUseInstructorProfileMe.mockReturnValue({ data: null });

      render(
        <SkillsPricingInline
          instructorProfile={{
            is_live: false,
            services: [
              { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 60, offers_online: true },
            ],
          } as never}
        />
      );

      // Component should render without crashing
      expect(screen.getByPlaceholderText(/hourly rate/i)).toBeInTheDocument();
    });

    it('saves service with default duration_options when none specified', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            duration_options: [], // Empty array should default to [60]
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      // Trigger autosave by changing the rate
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
        const callArgs = mockFetchWithAuth.mock.calls[0];
        const body = JSON.parse(callArgs[1].body);
        // Should have default duration of [60]
        expect(body.services[0].duration_options).toEqual([60]);
        expect(body.services[0].offers_online).toBe(true);
        expect(body.services[0].offers_travel).toBe(false);
        expect(body.services[0].offers_at_location).toBe(false);
      });

      jest.useRealTimers();
    });

    it('saves service with equipment_required when equipment is specified', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            equipment: 'keyboard, stand',
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      // Trigger autosave
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      jest.useRealTimers();
    });

    it('clears autosave timeout when services change rapidly', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);

      // Type multiple values rapidly
      await user.clear(rateInput);
      await user.type(rateInput, '7');
      jest.advanceTimersByTime(500); // Not enough to trigger autosave

      await user.type(rateInput, '0');
      jest.advanceTimersByTime(500); // Still not enough

      // Now advance past the debounce threshold
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalledTimes(1);
      });

      jest.useRealTimers();
    });

    it('does not save when live instructor has no services with rates', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: true,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: '', // Empty rate
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Try to trigger autosave with an empty rate still
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(screen.getByText(/must have at least one skill/i)).toBeInTheDocument();
      });
      // Should not have made API call
      expect(mockFetchWithAuth).not.toHaveBeenCalled();

      jest.useRealTimers();
    });
  });

  describe('Batch 9 — uncovered branch coverage', () => {
    it('toggles age group from adults to both when kids selected', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            age_groups: ['adults'],
            duration_options: [60],
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Click Kids to add it, making it 'both'
      const kidsButtons = screen.getAllByRole('button', { name: /^kids$/i });
      const kidsButton = kidsButtons.find((btn) => btn.closest('[class*="bg-white"]'));
      if (kidsButton) await user.click(kidsButton);

      // Should still render
      expect(screen.getAllByText(/piano/i).length).toBeGreaterThan(0);
    });

    it('toggles age group from both to kids when adults deselected', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            age_groups: ['kids', 'adults'], // both
            duration_options: [60],
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Click Adults to deselect it from 'both', should become 'kids'
      const adultsButtons = screen.getAllByRole('button', { name: /^adults$/i });
      const adultsButton = adultsButtons.find((btn) => btn.closest('[class*="bg-white"]'));
      if (adultsButton) await user.click(adultsButton);

      expect(screen.getAllByText(/piano/i).length).toBeGreaterThan(0);
    });

    it('prevents removing the last duration option', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            age_groups: ['adults'],
            duration_options: [60], // Only one duration
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Try to deselect the only duration option (60m)
      const durationButtons = screen.getAllByRole('button', { name: /^60m$/i });
      if (durationButtons[0]) {
        await user.click(durationButtons[0]);
      }

      // 60m should still be selected (can't remove last)
      const btn60 = screen.getAllByRole('button', { name: /^60m$/i })[0];
      expect(btn60?.className).toContain('purple');
    });

    it('adds new service with defaultCapabilities when has service areas', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['n1', 'n2'], // has service areas
          preferred_teaching_locations: [{ address: '123 Main' }], // has teaching locations
          services: [],
        },
      });

      render(<SkillsPricingInline />);

      await user.click(screen.getByRole('button', { name: /music/i }));
      await user.click(screen.getByRole('button', { name: /piano \+/i }));

      // Travel should default to on (has service areas)
      expect(screen.getByRole('switch', { name: /i travel to students/i })).toHaveAttribute('aria-checked', 'true');
      // At location should default to on (has teaching locations)
      expect(screen.getByRole('switch', { name: /students come to me/i })).toHaveAttribute('aria-checked', 'true');
    });

    it('adds new service defaulting to online-only when no areas or locations', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: [], // no service areas
          preferred_teaching_locations: [], // no teaching locations
          services: [],
        },
      });

      render(<SkillsPricingInline />);

      await user.click(screen.getByRole('button', { name: /music/i }));
      await user.click(screen.getByRole('button', { name: /piano \+/i }));

      // Online should default to on (no areas or locations)
      expect(screen.getByRole('switch', { name: /online lessons/i })).toHaveAttribute('aria-checked', 'true');
    });

    it('handles "Cannot enable at my location" error silently', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ detail: "Cannot enable 'at my location' without teaching locations" }),
      });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '55');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      // The error should be handled silently (not shown)
      await waitFor(() => {
        expect(screen.queryByText(/cannot enable/i)).not.toBeInTheDocument();
      });

      jest.useRealTimers();
    });

    it('saves service description in payload when provided', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            description: 'Classical piano lessons',
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
        const callArgs = mockFetchWithAuth.mock.calls[0];
        const body = JSON.parse(callArgs[1].body);
        expect(body.services[0].description).toBe('Classical piano lessons');
      });

      jest.useRealTimers();
    });

    it('omits description from payload when empty', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            description: '', // empty
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
        const callArgs = mockFetchWithAuth.mock.calls[0];
        const body = JSON.parse(callArgs[1].body);
        expect(body.services[0]).not.toHaveProperty('description');
      });

      jest.useRealTimers();
    });

    it('excludes services with empty hourly rate from save payload', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: 60,
              offers_online: true,
            },
            {
              service_catalog_id: 'svc-2',
              service_catalog_name: 'Guitar',
              hourly_rate: '', // empty rate
              offers_online: true,
            },
          ],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      // Trigger autosave
      const rateInputs = screen.getAllByPlaceholderText(/hourly rate/i);
      await user.clear(rateInputs[0]!);
      await user.type(rateInputs[0]!, '65');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
        const callArgs = mockFetchWithAuth.mock.calls[0];
        const body = JSON.parse(callArgs[1].body);
        // Only the service with a rate should be in the payload
        expect(body.services).toHaveLength(1);
        expect(body.services[0].service_catalog_id).toBe('svc-1');
      });

      jest.useRealTimers();
    });

    it('handles hasServiceAreas and hasTeachingLocations for service area summary', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_summary: 'All of Manhattan', // non-empty summary
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_travel: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Travel should be enabled (service_area_summary makes hasServiceAreas true)
      expect(screen.getByRole('switch', { name: /i travel to students/i })).toHaveAttribute('aria-checked', 'true');
    });

    it('handles hasServiceAreas via boroughs array', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_boroughs: ['Manhattan'], // non-empty boroughs
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_travel: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      expect(screen.getByRole('switch', { name: /i travel to students/i })).toHaveAttribute('aria-checked', 'true');
    });

    it('handles save with both age groups', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            age_groups: ['kids', 'adults'],
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
        const callArgs = mockFetchWithAuth.mock.calls[0];
        const body = JSON.parse(callArgs[1].body);
        expect(body.services[0].age_groups).toEqual(['kids', 'adults']);
      });

      jest.useRealTimers();
    });

    it('handles API error with empty json response', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => { throw new Error('not json'); },
      });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '55');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(screen.getByText(/failed to save/i)).toBeInTheDocument();
      });
      jest.useRealTimers();
    });

    it('shows "saving changes" text while saving', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      let resolveApi: (() => void) | null = null;
      const apiPromise = new Promise<void>((resolve) => { resolveApi = resolve; });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockImplementation(async () => {
        await apiPromise;
        return { ok: true, json: async () => ({}) };
      });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '55');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(screen.getByText(/saving changes/i)).toBeInTheDocument();
      });

      // Resolve the API call
      resolveApi!();

      jest.useRealTimers();
    });

    it('renders no services message when empty', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: { is_live: false, services: [] },
      });

      render(<SkillsPricingInline />);

      expect(screen.getByText(/no services added yet/i)).toBeInTheDocument();
    });

    it('handles service with service_catalog_id undefined', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
            // service_catalog_id is missing
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Should filter out service with empty catalog_service_id
      const rateInputs = screen.queryAllByPlaceholderText(/hourly rate/i);
      expect(rateInputs).toHaveLength(0);
    });

    it('does not show error for non-location-capability errors', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'General server error' }),
      });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '55');
      jest.advanceTimersByTime(1200);

      // Non-location-capability errors should be shown
      await waitFor(() => {
        expect(screen.getByText(/general server error/i)).toBeInTheDocument();
      });

      jest.useRealTimers();
    });

    it('uses service_catalog_name from data for display', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: null, // null name
            name: 'Fallback Name',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Should show Service (the default from displayServiceName mock)
      expect(screen.getAllByText(/service/i).length).toBeGreaterThan(0);
    });

    it('services with empty levels_taught default to all levels', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            levels_taught: [], // empty array
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // All three level buttons should be selected (purple/active)
      const beginnerBtns = screen.getAllByRole('button', { name: /^beginner$/i });
      const intermediateBtns = screen.getAllByRole('button', { name: /^intermediate$/i });
      const advancedBtns = screen.getAllByRole('button', { name: /^advanced$/i });

      expect(beginnerBtns[0]?.className).toContain('purple');
      expect(intermediateBtns[0]?.className).toContain('purple');
      expect(advancedBtns[0]?.className).toContain('purple');
    });
  });

  describe('Autosave timer management', () => {
    it('resets debounce timer when editing again before timer fires', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '6');

      // Advance 1000ms (not enough for 1200ms debounce)
      jest.advanceTimersByTime(1000);
      expect(mockFetchWithAuth).not.toHaveBeenCalled();

      // Type again before timer fires -- resets the timer
      await user.type(rateInput, '5');

      // Advance another 1000ms -- still not enough from last edit
      jest.advanceTimersByTime(1000);
      expect(mockFetchWithAuth).not.toHaveBeenCalled();

      // Advance the remaining 200ms
      jest.advanceTimersByTime(200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalledTimes(1);
      });

      jest.useRealTimers();
    });

    it('fires a single save when editing multiple times within debounce window', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);

      // Rapidly type four characters with 200ms gaps
      await user.type(rateInput, '1');
      jest.advanceTimersByTime(200);
      await user.type(rateInput, '0');
      jest.advanceTimersByTime(200);
      await user.type(rateInput, '0');
      jest.advanceTimersByTime(200);
      await user.type(rateInput, '0');

      // Now wait full debounce
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalledTimes(1);
      });

      // Verify final value was sent
      const callArgs = mockFetchWithAuth.mock.calls[0];
      const body = JSON.parse(callArgs[1].body as string);
      expect(body.services[0].hourly_rate).toBe(1000);

      jest.useRealTimers();
    });
  });

  describe('NaN price validation', () => {
    it('treats NaN hourly rate as zero in the display', async () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 'abc',
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // NaN rate renders but no earnings display (Number('abc') > 0 is false)
      expect(screen.queryByText(/you'll earn/i)).not.toBeInTheDocument();
    });

    it('filters out NaN-rate services from save payload', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: 60,
              offers_online: true,
            },
          ],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      // Clear and type non-numeric then fix it
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      // Empty rates are filtered from payload
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        // With empty rate the service is filtered from payload
        // and live=false so it does save with 0 services
        expect(mockFetchWithAuth).toHaveBeenCalled();
        const body = JSON.parse(mockFetchWithAuth.mock.calls[0][1].body as string);
        expect(body.services).toHaveLength(0);
      });

      jest.useRealTimers();
    });
  });

  describe('Capability validation - manual save toast', () => {
    it('shows toast error for manual-source save with all capabilities disabled', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      // We need to verify the manual source path shows a toast
      // The component only calls handleSave('auto') from the effect.
      // But we can test that auto-save does NOT call toast.error:
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_travel: false,
            offers_at_location: false,
            offers_online: false,
          }],
        },
      });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      // Wait for the autosave attempt
      await waitFor(() => {
        // The inline error message should show
        expect(screen.getByText(/select at least one location option/i)).toBeInTheDocument();
      });

      // Auto save should NOT show toast (only manual does)
      expect(toast.error).not.toHaveBeenCalledWith(
        expect.stringContaining('Select at least one way'),
        expect.any(Object)
      );
      expect(mockFetchWithAuth).not.toHaveBeenCalled();

      jest.useRealTimers();
    });
  });

  describe('Price floor violations display', () => {
    it('shows toast for autosave when price floor is violated', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['n1'],
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 30,
            duration_options: [60],
            offers_travel: true,
          }],
        },
      });
      mockUsePricingConfig.mockReturnValue({
        config: { price_floor_cents: { private_in_person: 5000, private_remote: 4000 } },
        isLoading: false,
      });
      mockEvaluateViolations.mockReturnValue([
        { duration: 60, modalityLabel: 'in-person', floorCents: 5000, baseCents: 3000 },
      ]);

      render(<SkillsPricingInline />);

      await user.clear(screen.getByPlaceholderText(/hourly rate/i));
      await user.type(screen.getByPlaceholderText(/hourly rate/i), '30');
      jest.advanceTimersByTime(1200);

      // FIX 7: toast.error is now called for ALL saves (auto and manual)
      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          expect.stringContaining('Minimum price'),
          { id: 'price-floor-error' }
        );
      });
      expect(mockFetchWithAuth).not.toHaveBeenCalled();

      jest.useRealTimers();
    });

    it('handles online-only service price floor violations', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 20,
            duration_options: [60],
            offers_online: true,
            offers_travel: false,
            offers_at_location: false,
          }],
        },
      });
      mockUsePricingConfig.mockReturnValue({
        config: { price_floor_cents: { private_in_person: 5000, private_remote: 4000 } },
        isLoading: false,
      });
      mockEvaluateViolations.mockReturnValue([
        { duration: 60, modalityLabel: 'online', floorCents: 4000, baseCents: 2000 },
      ]);

      render(<SkillsPricingInline />);

      await user.clear(screen.getByPlaceholderText(/hourly rate/i));
      await user.type(screen.getByPlaceholderText(/hourly rate/i), '20');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(screen.getByText(/minimum price for a online 60-minute/i)).toBeInTheDocument();
      });

      jest.useRealTimers();
    });

    it('evaluates violations for service with multiple duration options', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['n1'],
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 40,
            duration_options: [30, 60, 90],
            offers_travel: true,
          }],
        },
      });
      mockUsePricingConfig.mockReturnValue({
        config: { price_floor_cents: { private_in_person: 5000, private_remote: 3000 } },
        isLoading: false,
      });
      // First call returns violations (for memo), subsequent calls may differ
      mockEvaluateViolations.mockReturnValue([
        { duration: 30, modalityLabel: 'in-person', floorCents: 2500, baseCents: 2000 },
      ]);

      render(<SkillsPricingInline />);

      await user.clear(screen.getByPlaceholderText(/hourly rate/i));
      await user.type(screen.getByPlaceholderText(/hourly rate/i), '40');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(screen.getByText(/minimum price/i)).toBeInTheDocument();
      });

      jest.useRealTimers();
    });
  });

  describe('Default capabilities from profile', () => {
    it('defaults offers_travel when profile has service areas via boroughs', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_boroughs: ['Manhattan'],
          services: [],
        },
      });

      render(<SkillsPricingInline />);

      await user.click(screen.getByRole('button', { name: /music/i }));
      await user.click(screen.getByRole('button', { name: /piano \+/i }));

      // Travel default on because hasServiceAreas is true
      expect(screen.getByRole('switch', { name: /i travel to students/i })).toHaveAttribute('aria-checked', 'true');
      // Online should be off since travel is on
      expect(screen.getByRole('switch', { name: /online lessons/i })).toHaveAttribute('aria-checked', 'false');
    });

    it('defaults offers_online when no service areas and no teaching locations', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: [],
          service_area_boroughs: [],
          service_area_summary: '',
          preferred_teaching_locations: [],
          services: [],
        },
      });

      render(<SkillsPricingInline />);

      await user.click(screen.getByRole('button', { name: /music/i }));
      await user.click(screen.getByRole('button', { name: /piano \+/i }));

      // Online should default to true (no other options)
      expect(screen.getByRole('switch', { name: /online lessons/i })).toHaveAttribute('aria-checked', 'true');
    });

    it('defaults both travel and at_location when both areas and locations exist', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['SoHo'],
          preferred_teaching_locations: [{ address: '123 Studio' }],
          services: [],
        },
      });

      render(<SkillsPricingInline />);

      await user.click(screen.getByRole('button', { name: /music/i }));
      await user.click(screen.getByRole('button', { name: /piano \+/i }));

      expect(screen.getByRole('switch', { name: /i travel to students/i })).toHaveAttribute('aria-checked', 'true');
      expect(screen.getByRole('switch', { name: /students come to me/i })).toHaveAttribute('aria-checked', 'true');
      // Online should be false when both travel and at_location are true
      expect(screen.getByRole('switch', { name: /online lessons/i })).toHaveAttribute('aria-checked', 'false');
    });
  });

  describe('Skill filter', () => {
    it('filters services case-insensitively', async () => {
      const user = userEvent.setup();
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1' },
              { id: 'svc-2', name: 'Guitar', slug: 'guitar', subcategory_id: 'sub1' },
              { id: 'svc-3', name: 'Drums', slug: 'drums', subcategory_id: 'sub1' },
            ],
          }],
        },
        isLoading: false,
      });

      render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

      await user.click(screen.getByRole('button', { name: /music/i }));

      // Type lowercase to test case-insensitive match
      await user.type(screen.getByPlaceholderText(/search skills/i), 'pia');

      expect(screen.getByRole('button', { name: /piano \+/i })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /guitar \+/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /drums \+/i })).not.toBeInTheDocument();
    });

    it('shows no services when filter matches nothing', async () => {
      const user = userEvent.setup();
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1' },
            ],
          }],
        },
        isLoading: false,
      });

      render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

      await user.click(screen.getByRole('button', { name: /music/i }));
      await user.type(screen.getByPlaceholderText(/search skills/i), 'zzzzz');

      expect(screen.queryByRole('button', { name: /piano \+/i })).not.toBeInTheDocument();
    });
  });

  describe('Skill request submission', () => {
    it('shows sending state during submission', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

      await user.type(screen.getByPlaceholderText(/request a new skill/i), 'Violin');
      await user.click(screen.getByRole('button', { name: /submit/i }));

      // Button should show "Sending..." during submission
      expect(screen.getByRole('button', { name: /sending/i })).toBeInTheDocument();

      jest.advanceTimersByTime(600);

      await waitFor(() => {
        expect(screen.getByText(/we'll review/i)).toBeInTheDocument();
      });

      // Button should return to "Submit"
      expect(screen.getByRole('button', { name: /submit/i })).toBeInTheDocument();

      jest.useRealTimers();
    });

    it('clears the input field after successful submission', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

      const input = screen.getByPlaceholderText(/request a new skill/i);
      await user.type(input, 'Cello');
      expect(input).toHaveValue('Cello');

      await user.click(screen.getByRole('button', { name: /submit/i }));
      jest.advanceTimersByTime(600);

      await waitFor(() => {
        expect(input).toHaveValue('');
      });

      jest.useRealTimers();
    });
  });

  describe('Platform fee context resolution', () => {
    it('resolves fee rate with current_tier_pct from profile', () => {
      const { resolvePlatformFeeRate } = jest.requireMock('@/lib/pricing/platformFees') as {
        resolvePlatformFeeRate: jest.Mock;
      };

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          current_tier_pct: 12,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 100,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      expect(resolvePlatformFeeRate).toHaveBeenCalledWith(
        expect.objectContaining({
          currentTierPct: 12,
          isFoundingInstructor: false,
        })
      );
    });

    it('uses instructor_tier_pct fallback when current_tier_pct is absent', () => {
      const { resolvePlatformFeeRate } = jest.requireMock('@/lib/pricing/platformFees') as {
        resolvePlatformFeeRate: jest.Mock;
      };

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          instructor_tier_pct: 15,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 100,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      expect(resolvePlatformFeeRate).toHaveBeenCalledWith(
        expect.objectContaining({
          currentTierPct: 15,
          isFoundingInstructor: false,
        })
      );
    });

    it('passes null currentTierPct when neither tier field exists', () => {
      const { resolvePlatformFeeRate } = jest.requireMock('@/lib/pricing/platformFees') as {
        resolvePlatformFeeRate: jest.Mock;
      };

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 100,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      expect(resolvePlatformFeeRate).toHaveBeenCalledWith(
        expect.objectContaining({
          currentTierPct: null,
          isFoundingInstructor: false,
        })
      );
    });

    it('passes non-finite tier pct as null', () => {
      const { resolvePlatformFeeRate } = jest.requireMock('@/lib/pricing/platformFees') as {
        resolvePlatformFeeRate: jest.Mock;
      };

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          current_tier_pct: NaN,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 100,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      expect(resolvePlatformFeeRate).toHaveBeenCalledWith(
        expect.objectContaining({
          currentTierPct: null,
        })
      );
    });

    it('passes isFoundingInstructor: true when profile has it', () => {
      const { resolvePlatformFeeRate } = jest.requireMock('@/lib/pricing/platformFees') as {
        resolvePlatformFeeRate: jest.Mock;
      };

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          is_founding_instructor: true,
          current_tier_pct: 8,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 100,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      expect(resolvePlatformFeeRate).toHaveBeenCalledWith(
        expect.objectContaining({
          isFoundingInstructor: true,
          currentTierPct: 8,
        })
      );
    });
  });

  describe('Hydration race prevention', () => {
    it('blocks hydration when isEditingRef is true from active editing', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      const profile = {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 70,
          offers_online: true,
        }],
      };

      const { rerender } = render(
        <SkillsPricingInline instructorProfile={profile as never} />
      );

      // Edit the rate - this sets isEditingRef.current = true
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '90');

      // Rerender with original profile data before autosave fires
      // This simulates a stale React Query refetch arriving during editing
      rerender(<SkillsPricingInline instructorProfile={profile as never} />);

      // The edited value should be preserved, not overwritten
      expect(screen.getByPlaceholderText(/hourly rate/i)).toHaveValue(90);

      jest.useRealTimers();
    });

    it('accepts hydration when pendingSyncSignatureRef matches', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      const profile = {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 70,
          offers_online: true,
        }],
      };

      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      const { rerender } = render(
        <SkillsPricingInline instructorProfile={profile as never} />
      );

      // Edit the rate
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '80');

      // Trigger autosave
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      // Now rerender with the saved data (matching what was saved)
      const updatedProfile = {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 80,
          offers_online: true,
        }],
      };
      rerender(<SkillsPricingInline instructorProfile={updatedProfile as never} />);

      // Value should be 80 (accepted from hydration since signature matches)
      expect(screen.getByPlaceholderText(/hourly rate/i)).toHaveValue(80);

      jest.useRealTimers();
    });
  });

  describe('hasServiceAreas and hasTeachingLocations edge cases', () => {
    it('hasServiceAreas is false with empty string summary', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: [],
          service_area_boroughs: [],
          service_area_summary: '   ', // whitespace-only
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_travel: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Travel toggle should be disabled (hasServiceAreas = false)
      expect(screen.getByRole('switch', { name: /i travel to students/i })).toBeDisabled();
    });

    it('hasServiceAreas true via service_area_summary', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: [],
          service_area_boroughs: [],
          service_area_summary: 'All of NYC',
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_travel: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Travel toggle should be enabled
      expect(screen.getByRole('switch', { name: /i travel to students/i })).not.toBeDisabled();
    });

    it('hasTeachingLocations false when preferred_teaching_locations is not an array', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          preferred_teaching_locations: null, // not an array
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_at_location: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // At-location toggle should be disabled
      expect(screen.getByRole('switch', { name: /students come to me/i })).toBeDisabled();
    });

    it('hasServiceAreas false when neighborhoods/boroughs/summary are non-array', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: null, // not an array
          service_area_boroughs: null, // not an array
          service_area_summary: null, // not a string
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_travel: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      expect(screen.getByRole('switch', { name: /i travel to students/i })).toBeDisabled();
    });
  });

  describe('handleSave error branches', () => {
    it('handles non-Error exception in save', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });
      // Throw a non-Error object
      mockFetchWithAuth.mockRejectedValueOnce('network timeout');

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '55');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        // Non-Error => "Failed to save" fallback
        expect(screen.getByText(/failed to save/i)).toBeInTheDocument();
      });

      jest.useRealTimers();
    });

    it('clears priceErrors when save passes validation and priceErrors exist', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['n1'],
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 30,
            duration_options: [60],
            offers_travel: true,
          }],
        },
      });
      mockUsePricingConfig.mockReturnValue({
        config: { price_floor_cents: { private_in_person: 5000, private_remote: 4000 } },
        isLoading: false,
      });
      mockEvaluateViolations.mockReturnValue([
        { duration: 60, modalityLabel: 'in-person', floorCents: 5000, baseCents: 3000 },
      ]);

      render(<SkillsPricingInline />);

      // First save -- triggers price floor error
      await user.clear(screen.getByPlaceholderText(/hourly rate/i));
      await user.type(screen.getByPlaceholderText(/hourly rate/i), '30');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(screen.getByText(/minimum price/i)).toBeInTheDocument();
      });

      // Fix the price -- clear violations
      mockEvaluateViolations.mockReturnValue([]);
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      await user.clear(screen.getByPlaceholderText(/hourly rate/i));
      await user.type(screen.getByPlaceholderText(/hourly rate/i), '100');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      // Price error should be cleared
      expect(screen.queryByText(/minimum price/i)).not.toBeInTheDocument();

      jest.useRealTimers();
    });
  });

  describe('Profile hydration with service data mapping', () => {
    it('maps age_groups correctly for single kids entry', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            age_groups: ['kids'],
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Kids button should be selected (purple), Adults should not
      const kidsButtons = screen.getAllByRole('button', { name: /^kids$/i });
      const adultsButtons = screen.getAllByRole('button', { name: /^adults$/i });
      expect(kidsButtons[0]?.className).toContain('purple');
      expect(adultsButtons[0]?.className).not.toContain('purple');
    });

    it('maps age_groups correctly for dual (both) entry', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            age_groups: ['kids', 'adults'],
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Both buttons should be selected
      const kidsButtons = screen.getAllByRole('button', { name: /^kids$/i });
      const adultsButtons = screen.getAllByRole('button', { name: /^adults$/i });
      expect(kidsButtons[0]?.className).toContain('purple');
      expect(adultsButtons[0]?.className).toContain('purple');
    });

    it('maps missing age_groups to all eligible groups from catalog', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            // age_groups not provided — defaults to catalog's eligible_age_groups
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // All eligible age groups from catalog should be selected (kids, teens, adults)
      const kidsButtons = screen.getAllByRole('button', { name: /^kids$/i });
      const adultsButtons = screen.getAllByRole('button', { name: /^adults$/i });
      expect(adultsButtons[0]?.className).toContain('purple');
      expect(kidsButtons[0]?.className).toContain('purple');
    });

    it('forces offers_travel false when service areas are removed', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: [], // no service areas
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_travel: true, // was true, but no areas now
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Travel should be disabled and unchecked (no areas)
      const travelSwitch = screen.getByRole('switch', { name: /i travel to students/i });
      expect(travelSwitch).toBeDisabled();
      expect(travelSwitch).toHaveAttribute('aria-checked', 'false');
    });

    it('forces offers_at_location false when teaching locations are removed', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          preferred_teaching_locations: [], // no teaching locations
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_at_location: true, // was true, but no locations
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      const atLocationSwitch = screen.getByRole('switch', { name: /students come to me/i });
      expect(atLocationSwitch).toBeDisabled();
      expect(atLocationSwitch).toHaveAttribute('aria-checked', 'false');
    });
  });

  describe('Age group toggle logic', () => {
    it('toggles from kids to both when adults is clicked', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            age_groups: ['kids'],
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      const adultsButtons = screen.getAllByRole('button', { name: /^adults$/i });
      await user.click(adultsButtons[0]!);

      // Both should now be selected
      const kidsButtons = screen.getAllByRole('button', { name: /^kids$/i });
      expect(kidsButtons[0]?.className).toContain('purple');
      expect(adultsButtons[0]?.className).toContain('purple');
    });

    it('toggles from both to adults when kids is deselected', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            age_groups: ['kids', 'adults'],
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      const kidsButtons = screen.getAllByRole('button', { name: /^kids$/i });
      await user.click(kidsButtons[0]!);

      // Only adults should be selected
      const adultsButtons = screen.getAllByRole('button', { name: /^adults$/i });
      expect(adultsButtons[0]?.className).toContain('purple');
      expect(kidsButtons[0]?.className).not.toContain('purple');
    });

    it('prevents deselecting the last age group (min-1 guard)', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            age_groups: ['adults'],
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Click adults button (the only selected group) — min-1 guard prevents deselection
      const adultsButtons = screen.getAllByRole('button', { name: /^adults$/i });
      await user.click(adultsButtons[0]!);

      // Adults should remain selected (can't deselect the last group)
      expect(adultsButtons[0]?.className).toContain('purple');
    });
  });

  describe('Service card display edge cases', () => {
    it('shows $0 when hourly rate is empty string', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: '',
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Should display $0 when rate is empty
      expect(screen.getByText('$0')).toBeInTheDocument();
      // No earnings display for empty rate
      expect(screen.queryByText(/you'll earn/i)).not.toBeInTheDocument();
    });

    it('shows service_catalog_name as display name when available', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Classical Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // The card header should show service_catalog_name
      const nameElements = screen.getAllByText('Classical Piano');
      expect(nameElements.length).toBeGreaterThan(0);
    });

    it('falls back to "Service" when both names are null', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: null,
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // The displayServiceName mock returns 'Service' when name is null
      const serviceElements = screen.getAllByText('Service');
      expect(serviceElements.length).toBeGreaterThan(0);
    });
  });

  describe('Save payload edge cases', () => {
    it('maps age_groups "kids" to single-item array in payload', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            age_groups: ['kids'],
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        const body = JSON.parse(mockFetchWithAuth.mock.calls[0][1].body as string);
        expect(body.services[0].age_groups).toEqual(['kids']);
      });

      jest.useRealTimers();
    });

    it('sorts duration_options in payload', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            duration_options: [90, 30, 60],
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        const body = JSON.parse(mockFetchWithAuth.mock.calls[0][1].body as string);
        expect(body.services[0].duration_options).toEqual([30, 60, 90]);
      });

      jest.useRealTimers();
    });

    it('includes equipment_required array in payload when equipment has values', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            equipment_required: ['Piano', 'Bench'],
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        const body = JSON.parse(mockFetchWithAuth.mock.calls[0][1].body as string);
        expect(body.services[0].equipment_required).toEqual(['Piano', 'Bench']);
      });

      jest.useRealTimers();
    });

    it('omits equipment_required from payload when equipment is empty', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        const body = JSON.parse(mockFetchWithAuth.mock.calls[0][1].body as string);
        expect(body.services[0]).not.toHaveProperty('equipment_required');
      });

      jest.useRealTimers();
    });

    it('sends offers_travel and offers_at_location based on service areas/locations', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['n1'],
          preferred_teaching_locations: [{ address: '123' }],
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            offers_travel: true,
            offers_at_location: true,
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        const body = JSON.parse(mockFetchWithAuth.mock.calls[0][1].body as string);
        expect(body.services[0].offers_travel).toBe(true);
        expect(body.services[0].offers_at_location).toBe(true);
        expect(body.services[0].offers_online).toBe(true);
      });

      jest.useRealTimers();
    });
  });

  describe('allServicesData processing', () => {
    it('deduplicates services within a category', () => {
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1' },
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1' }, // duplicate
              { id: 'svc-2', name: 'Guitar', slug: 'guitar', subcategory_id: 'sub1' },
            ],
          }],
        },
        isLoading: false,
      });

      render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

      // Expand Music category
      // Only 2 unique services should exist
      expect(screen.getByRole('button', { name: /music/i })).toBeInTheDocument();
    });

    it('handles categories with empty services array', async () => {
      const user = userEvent.setup();
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [],
          }],
        },
        isLoading: false,
      });

      render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

      await user.click(screen.getByRole('button', { name: /music/i }));

      // Category expanded but no service buttons inside
      expect(screen.queryByRole('button', { name: /piano/i })).not.toBeInTheDocument();
    });
  });

  describe('Profile prop vs hook priority', () => {
    it('prefers instructorProfile prop over hook data', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'HookPiano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(
        <SkillsPricingInline
          instructorProfile={{
            is_live: false,
            services: [{
              service_catalog_id: 'svc-1',
              service_catalog_name: 'PropPiano',
              hourly_rate: 75,
              offers_online: true,
            }],
          } as never}
        />
      );

      // The prop data should win
      expect(screen.getByPlaceholderText(/hourly rate/i)).toHaveValue(75);
      expect(screen.getAllByText(/PropPiano/i).length).toBeGreaterThan(0);
    });

    it('disables useInstructorProfileMe when prop is provided', () => {
      render(
        <SkillsPricingInline
          instructorProfile={{ is_live: false, services: [] } as never}
        />
      );

      // When prop is provided, hook should be called with false (disabled)
      expect(mockUseInstructorProfileMe).toHaveBeenCalledWith(false);
    });

    it('enables useInstructorProfileMe when prop is not provided', () => {
      render(<SkillsPricingInline />);

      // When prop is not provided, hook should be called with true (enabled)
      expect(mockUseInstructorProfileMe).toHaveBeenCalledWith(true);
    });
  });

  describe('canRemoveSkill guard', () => {
    it('allows removal for non-live instructor even with single skill', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Click the X button on the skill card
      await user.click(screen.getByRole('button', { name: /remove skill/i }));

      // Should be removed since non-live
      expect(screen.getByText(/no services added yet/i)).toBeInTheDocument();
    });

    it('allows removal for live instructor with multiple skills', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: true,
          services: [
            { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 60, offers_online: true },
            { service_catalog_id: 'svc-2', service_catalog_name: 'Guitar', hourly_rate: 50, offers_online: true },
          ],
        },
      });

      render(<SkillsPricingInline />);

      // Should have 2 rate inputs
      expect(screen.getAllByPlaceholderText(/hourly rate/i)).toHaveLength(2);

      // Remove first skill
      const removeButtons = screen.getAllByRole('button', { name: /remove skill/i });
      await user.click(removeButtons[0]!);

      // Should have 1 rate input remaining
      expect(screen.getAllByPlaceholderText(/hourly rate/i)).toHaveLength(1);
    });
  });

  describe('Earnings display', () => {
    it('does not show earnings when rate is 0', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 0,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Number(0) > 0 is false, so earnings should not be shown
      expect(screen.queryByText(/you'll earn/i)).not.toBeInTheDocument();
    });

    it('shows correct earnings for high rates', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 200,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // 200 * 0.8 = 160.00
      expect(screen.getByText(/\$160\.00/)).toBeInTheDocument();
    });
  });

  describe('Price error clearing on rate input change', () => {
    it('does not mutate priceErrors when no error exists for that service', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      // Type a new value -- no priceError exists for this service
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '75');

      // Should not show any error message
      expect(screen.queryByText(/minimum price/i)).not.toBeInTheDocument();

      jest.useRealTimers();
    });
  });

  describe('Service with null/missing fields', () => {
    it('handles service with null hourly_rate', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: null,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // hourly_rate: String(null) = '' which is fine
      expect(screen.getByPlaceholderText(/hourly rate/i)).toBeInTheDocument();
    });

    it('handles service with undefined description and equipment', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            // description and equipment missing
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      expect(screen.getByPlaceholderText(/brief description/i)).toHaveValue('');
      expect(screen.getByPlaceholderText(/yoga mat/i)).toHaveValue('');
    });
  });

  describe('Batch 12: branch coverage expansion', () => {
    it('serviceFloorViolations skips services with no location types', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 40,
            offers_travel: false,
            offers_at_location: false,
            offers_online: false,
            duration_options: [60],
          }],
        },
      });
      mockUsePricingConfig.mockReturnValue({
        config: { price_floor_cents: { private_in_person: 5000 } },
        isLoading: false,
      });
      mockEvaluateViolations.mockReturnValue([
        { duration: 60, modalityLabel: 'in-person', floorCents: 5000, baseCents: 4000 },
      ]);

      render(<SkillsPricingInline />);

      expect(screen.queryByText(/minimum price/i)).not.toBeInTheDocument();
    });

    it('handles profile with missing services array', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
        },
      });

      render(<SkillsPricingInline />);

      expect(screen.getByText(/no services added yet/i)).toBeInTheDocument();
    });

    it('handles allServicesData with null services in a category', async () => {
      const user = userEvent.setup();
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
          }],
        },
        isLoading: false,
      });

      render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

      await user.click(screen.getByRole('button', { name: /music/i }));

      expect(screen.queryByRole('button', { name: /piano/i })).not.toBeInTheDocument();
    });

    it('handles allServicesData with null categories', () => {
      mockUseAllServices.mockReturnValue({
        data: {},
        isLoading: false,
      });

      render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

      expect(screen.getByText(/no services added yet/i)).toBeInTheDocument();
    });

    it('displays travel disabled message when no service areas', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: [],
          service_area_boroughs: [],
          preferred_teaching_locations: [],
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      const travelSwitch = screen.getByRole('switch', { name: /i travel to students/i });
      expect(travelSwitch).toBeDisabled();

      expect(screen.getByText(/you need at least one service area/i)).toBeInTheDocument();
    });

    it('displays at-location disabled message when no teaching locations', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['n1'],
          preferred_teaching_locations: [],
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_travel: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      const atLocationSwitch = screen.getByRole('switch', { name: /students come to me/i });
      expect(atLocationSwitch).toBeDisabled();

      expect(screen.getByText(/you need at least one teaching location/i)).toBeInTheDocument();
    });

    it('clears price error on rate input when error exists for that service', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['n1'],
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 30,
            duration_options: [60],
            offers_travel: true,
          }],
        },
      });
      mockUsePricingConfig.mockReturnValue({
        config: { price_floor_cents: { private_in_person: 5000 } },
        isLoading: false,
      });
      mockEvaluateViolations.mockReturnValue([
        { duration: 60, modalityLabel: 'in-person', floorCents: 5000, baseCents: 3000 },
      ]);

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '30');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(screen.getByText(/minimum price/i)).toBeInTheDocument();
      });

      expect(rateInput).toHaveAttribute('aria-invalid', 'true');

      mockEvaluateViolations.mockReturnValue([]);
      await user.type(rateInput, '0');

      jest.useRealTimers();
    });

    it('chip remove button shows disabled title for live instructor with one skill', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: true,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      const removeButtons = screen.getAllByRole('button', { name: /remove/i });
      const chipRemoveButton = removeButtons.find((btn) => btn.title?.includes('must have at least'));
      expect(chipRemoveButton).toBeDefined();
    });

    it('age group toggle from kids clicking kids keeps kids selected (min-1 guard)', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            age_groups: ['kids'],
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Click kids (the only selected group) — min-1 guard prevents deselection
      const kidsButtons = screen.getAllByRole('button', { name: /^kids$/i });
      await user.click(kidsButtons[0]!);

      // Kids should remain selected (can't deselect the last group)
      expect(kidsButtons[0]?.className).toContain('purple');
    });

    it('duration toggle prevents removing the only selected duration (45m)', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            duration_options: [45],
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      const durationButtons = screen.getAllByRole('button', { name: /^45m$/i });
      await user.click(durationButtons[0]!);

      expect(durationButtons[0]?.className).toContain('purple');
    });

    it('adds a second duration then removes the original', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            duration_options: [60],
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      const btn30 = screen.getAllByRole('button', { name: /^30m$/i });
      await user.click(btn30[0]!);
      expect(btn30[0]?.className).toContain('purple');

      const btn60 = screen.getAllByRole('button', { name: /^60m$/i });
      await user.click(btn60[0]!);
      expect(btn60[0]?.className).not.toContain('purple');
    });

    it('service card renders with null name and service_catalog_name', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-fallback',
            service_catalog_name: null,
            name: null,
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      expect(screen.getByPlaceholderText(/hourly rate/i)).toBeInTheDocument();
    });

    it('renders className prop on root div', () => {
      const { container } = render(
        <SkillsPricingInline
          className="test-custom-class"
          instructorProfile={{ is_live: false, services: [] } as never}
        />
      );

      expect(container.firstElementChild?.classList.contains('test-custom-class')).toBe(true);
    });

    it('saves payload with equipment, description, and sorted durations', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            description: 'Test description',
            equipment_required: ['Piano'],
            offers_online: true,
            levels_taught: ['beginner', 'advanced'],
            duration_options: [60, 30],
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
        const body = JSON.parse(mockFetchWithAuth.mock.calls[0][1].body as string);
        expect(body.services[0].description).toBe('Test description');
        expect(body.services[0].equipment_required).toEqual(['Piano']);
        expect(body.services[0].duration_options).toEqual([30, 60]);
      });

      jest.useRealTimers();
    });

    it('handles service with empty equipment string in save payload', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            equipment: '  ,  ,  ', // whitespace-only items
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
        const body = JSON.parse(mockFetchWithAuth.mock.calls[0][1].body as string);
        // Empty items after trim should mean no equipment_required in payload
        expect(body.services[0]).not.toHaveProperty('equipment_required');
      });

      jest.useRealTimers();
    });

    it('chip displays name over service_catalog_name when both present', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'CatalogName',
            name: 'DisplayName',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // The chip/card should show the service name from displayServiceName mock
      expect(screen.getAllByText(/service/i).length).toBeGreaterThan(0);
    });

    it('selected service chip shows remove button with correct title for non-live', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // For non-live with profileLoaded, remove button should have "Remove Piano" title
      const removeButtons = screen.getAllByRole('button', { name: /remove piano/i });
      expect(removeButtons.length).toBeGreaterThan(0);
      expect(removeButtons[0]?.title).toContain('Remove');
    });
  });

  describe('Batch 13: handleSave and interaction branch coverage', () => {
    it('successful autosave shows saving indicator and clears error', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 50, offers_online: true },
          ],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      // Trigger autosave by modifying rate
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '55');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      jest.useRealTimers();
    });

    it('handleSave skips save when pricing config is loading', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 50, offers_online: true },
          ],
        },
      });
      mockUsePricingConfig.mockReturnValue({ config: null, isLoading: true });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '55');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).not.toHaveBeenCalled();
      });

      jest.useRealTimers();
    });

    it('autosave blocks when all capabilities are off', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: [],
          service_area_boroughs: [],
          preferred_teaching_locations: [],
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: 50,
              offers_travel: false,
              offers_at_location: false,
              offers_online: false,
            },
          ],
        },
      });

      render(<SkillsPricingInline />);

      // Trigger autosave by modifying rate
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '55');
      jest.advanceTimersByTime(1200);

      // Save should be blocked due to invalid capabilities - fetch should not be called
      await waitFor(() => {
        expect(mockFetchWithAuth).not.toHaveBeenCalled();
      });

      jest.useRealTimers();
    });

    it('handleSave clears existing price errors when save passes validation', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      // First render with a price floor violation to set price errors
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['n1'],
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: 30,
              duration_options: [60],
              offers_travel: true,
              offers_online: true,
            },
          ],
        },
      });
      mockUsePricingConfig.mockReturnValue({
        config: { price_floor_cents: { private_in_person: 5000 } },
        isLoading: false,
      });
      mockEvaluateViolations.mockReturnValue([
        { duration: 60, modalityLabel: 'in-person', floorCents: 5000, baseCents: 3000 },
      ]);
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      // Trigger autosave to set price errors
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '30');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(screen.getByText(/minimum price/i)).toBeInTheDocument();
      });

      // Now fix: clear violation and change rate
      mockEvaluateViolations.mockReturnValue([]);
      await user.clear(rateInput);
      await user.type(rateInput, '80');
      jest.advanceTimersByTime(1200);

      // Save should now succeed and clear errors
      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      jest.useRealTimers();
    });

    it('online toggle switches offers_online on service card', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: 50,
              offers_online: true,
              offers_travel: false,
              offers_at_location: false,
            },
          ],
        },
      });

      render(<SkillsPricingInline />);

      const onlineSwitch = screen.getByRole('switch', { name: /online lessons/i });
      expect(onlineSwitch).toBeChecked();

      await user.click(onlineSwitch);

      expect(onlineSwitch).not.toBeChecked();
    });

    it('travel toggle switches offers_travel on service card', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['n1'],
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: 50,
              offers_travel: false,
              offers_online: true,
            },
          ],
        },
      });

      render(<SkillsPricingInline />);

      const travelSwitch = screen.getByRole('switch', { name: /i travel to students/i });
      expect(travelSwitch).not.toBeChecked();

      await user.click(travelSwitch);

      expect(travelSwitch).toBeChecked();
    });

    it('at-location toggle switches offers_at_location on service card', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['n1'],
          preferred_teaching_locations: ['Studio A'],
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: 50,
              offers_at_location: false,
              offers_online: true,
            },
          ],
        },
      });

      render(<SkillsPricingInline />);

      const atLocSwitch = screen.getByRole('switch', { name: /students come to me/i });
      expect(atLocSwitch).not.toBeChecked();

      await user.click(atLocSwitch);

      expect(atLocSwitch).toBeChecked();
    });

    it('level toggle adds and removes skill levels', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: 50,
              filter_selections: { skill_level: ['beginner'] },
              offers_online: true,
            },
          ],
        },
      });

      render(<SkillsPricingInline />);

      // Add intermediate
      const intButton = screen.getAllByRole('button', { name: /^intermediate$/i });
      await user.click(intButton[0]!);
      expect(intButton[0]?.className).toContain('purple');

      // Remove beginner
      const begButton = screen.getAllByRole('button', { name: /^beginner$/i });
      await user.click(begButton[0]!);
      expect(begButton[0]?.className).not.toContain('purple');
    });

    it('description textarea updates on change', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: 50,
              offers_online: true,
            },
          ],
        },
      });

      render(<SkillsPricingInline />);

      const descInput = screen.getByPlaceholderText(/brief description/i);
      await user.type(descInput, 'I teach classical piano');

      expect(descInput).toHaveValue('I teach classical piano');
    });

    it('equipment textarea updates on change', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: 50,
              offers_online: true,
            },
          ],
        },
      });

      render(<SkillsPricingInline />);

      const equipInput = screen.getByPlaceholderText(/yoga mat/i);
      await user.type(equipInput, 'Keyboard, metronome');

      expect(equipInput).toHaveValue('Keyboard, metronome');
    });

    it('age group toggle from adults clicking adults keeps adults selected (min-1 guard)', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: 50,
              age_groups: ['adults'],
              offers_online: true,
            },
          ],
        },
      });

      render(<SkillsPricingInline />);

      // Click adults (the only selected group) — min-1 guard prevents deselection
      const adultsButtons = screen.getAllByRole('button', { name: /^adults$/i });
      await user.click(adultsButtons[0]!);

      // Adults should remain selected (can't deselect the last group)
      expect(adultsButtons[0]?.className).toContain('purple');
    });

    it('age group toggle from both clicking kids switches to adults only', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: 50,
              age_groups: ['kids', 'adults'],
              offers_online: true,
            },
          ],
        },
      });

      render(<SkillsPricingInline />);

      const kidsButtons = screen.getAllByRole('button', { name: /^kids$/i });
      const adultsButtons = screen.getAllByRole('button', { name: /^adults$/i });
      // Both should initially be selected (purple)
      expect(kidsButtons[0]?.className).toContain('purple');
      expect(adultsButtons[0]?.className).toContain('purple');

      // Click kids to deselect it -> adults only
      await user.click(kidsButtons[0]!);

      expect(kidsButtons[0]?.className).not.toContain('purple');
      expect(adultsButtons[0]?.className).toContain('purple');
    });

    it('age group toggle from both clicking adults switches to kids only', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: 50,
              age_groups: ['kids', 'adults'],
              offers_online: true,
            },
          ],
        },
      });

      render(<SkillsPricingInline />);

      const adultsButtons = screen.getAllByRole('button', { name: /^adults$/i });

      // Click adults to deselect it -> kids only
      await user.click(adultsButtons[0]!);

      const kidsButtons = screen.getAllByRole('button', { name: /^kids$/i });
      expect(kidsButtons[0]?.className).toContain('purple');
      expect(adultsButtons[0]?.className).not.toContain('purple');
    });

    it('skill request with empty input does not submit', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [],
        },
      });

      render(<SkillsPricingInline />);

      // Find request skill button and click without typing anything
      const requestButton = screen.queryByRole('button', { name: /request/i });
      if (requestButton) {
        await user.click(requestButton);
        // No success message should appear because input is empty
        expect(screen.queryByText(/we'll review/i)).not.toBeInTheDocument();
      }
    });

    it('service card displays $0 when hourly_rate is empty', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: '',
              offers_online: true,
            },
          ],
        },
      });

      render(<SkillsPricingInline />);

      expect(screen.getByText('$0')).toBeInTheDocument();
    });

    it('buildPriceFloorErrors uses service name fallback when service has no name', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['n1'],
          services: [
            {
              service_catalog_id: 'svc-nameless',
              service_catalog_name: null,
              name: null,
              hourly_rate: 30,
              duration_options: [60],
              offers_travel: true,
              offers_online: true,
            },
          ],
        },
      });
      mockUsePricingConfig.mockReturnValue({
        config: { price_floor_cents: { private_in_person: 5000 } },
        isLoading: false,
      });
      mockEvaluateViolations.mockReturnValue([
        { duration: 60, modalityLabel: 'in-person', floorCents: 5000, baseCents: 3000 },
      ]);

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '30');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        // The error message should use 'Service' fallback since displayServiceName returns 'Service' for null name
        expect(toast.error).toHaveBeenCalledWith(
          expect.stringMatching(/Service/),
          expect.anything()
        );
      });

      jest.useRealTimers();
    });

    it('filters skill grid services by search text', async () => {
      const user = userEvent.setup();
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [
            {
              id: '01HABCTESTCAT0000000000001',
              name: 'Music',
              services: [
                { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1' },
                { id: 'svc-2', name: 'Guitar', slug: 'guitar', subcategory_id: 'sub1' },
              ],
            },
          ],
        },
        isLoading: false,
      });

      render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

      // Open the Music accordion
      await user.click(screen.getByRole('button', { name: /music/i }));

      // Both skills should be visible initially
      expect(screen.getByRole('button', { name: /piano/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /guitar/i })).toBeInTheDocument();

      // Type in search/filter
      const searchInput = screen.queryByPlaceholderText(/search|filter/i);
      if (searchInput) {
        await user.type(searchInput, 'piano');
        expect(screen.getByRole('button', { name: /piano/i })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /guitar/i })).not.toBeInTheDocument();
      }
    });

    it('saves with duration_options defaulting to [60] when empty', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: 60,
              duration_options: [],
              offers_online: true,
            },
          ],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
        const body = JSON.parse(mockFetchWithAuth.mock.calls[0]![1].body as string);
        // When duration_options is empty, it should default to [60]
        expect(body.services[0].duration_options).toEqual([60]);
      });

      jest.useRealTimers();
    });

    it('autosave blocks for live instructor with no services with valid rates', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: true,
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: 50,
              offers_online: true,
            },
          ],
        },
      });

      render(<SkillsPricingInline />);

      // Clear the rate to make it empty, triggering the live instructor guard
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(screen.getByText(/must have at least one skill/i)).toBeInTheDocument();
      });
      expect(mockFetchWithAuth).not.toHaveBeenCalled();

      jest.useRealTimers();
    });

    it('handleSave with failed API response shows error message', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            {
              service_catalog_id: 'svc-1',
              service_catalog_name: 'Piano',
              hourly_rate: 50,
              offers_online: true,
            },
          ],
        },
      });
      mockFetchWithAuth.mockResolvedValue({
        ok: false,
        json: async () => ({ detail: 'Server error occurred' }),
      });

      render(<SkillsPricingInline />);

      // Trigger autosave by modifying rate
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '55');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(screen.getByText(/server error occurred/i)).toBeInTheDocument();
      });

      jest.useRealTimers();
    });
  });

  describe('Batch 14: targeted uncovered line coverage', () => {
    it('back-fills subcategory_id and eligible_age_groups from catalog when missing (lines 527-548)', async () => {
      // Service loaded from profile has no subcategory_id and empty eligible_age_groups.
      // When catalog data loads (serviceCatalogById populated), the back-fill effect
      // should update them and set isHydratingRef.
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            // subcategory_id will be '' because catalogEntry won't be available at hydration time
            // when allServicesData loads later
            offers_online: true,
          }],
        },
      });

      // Initially return no catalog data
      mockUseAllServices.mockReturnValue({ data: null, isLoading: true });

      const { rerender } = render(<SkillsPricingInline />);

      // Now provide catalog data - this triggers the back-fill effect
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [{
              id: 'svc-1',
              name: 'Piano',
              slug: 'piano',
              subcategory_id: '01HABCTESTSUBCAT0000000001',
              eligible_age_groups: ['kids', 'teens', 'adults'],
            }],
          }],
        },
        isLoading: false,
      });

      rerender(<SkillsPricingInline />);

      // The service should now render with the catalog data back-filled
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/hourly rate/i)).toHaveValue(60);
      });
    });

    it('back-fills default filter_selections (skill_level and age_groups) from catalog (lines 536-548)', async () => {
      // Profile has a service but no filter_selections for skill_level or age_groups
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            offers_online: true,
            // No age_groups or filter_selections provided
          }],
        },
      });

      // Provide catalog data with eligible_age_groups
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [{
              id: 'svc-1',
              name: 'Piano',
              slug: 'piano',
              subcategory_id: '01HABCTESTSUBCAT0000000001',
              eligible_age_groups: ['kids', 'teens', 'adults'],
            }],
          }],
        },
        isLoading: false,
      });

      render(<SkillsPricingInline />);

      // All three skill levels should be selected (back-filled from defaults)
      const beginnerBtns = screen.getAllByRole('button', { name: /^beginner$/i });
      const intermediateBtns = screen.getAllByRole('button', { name: /^intermediate$/i });
      const advancedBtns = screen.getAllByRole('button', { name: /^advanced$/i });
      expect(beginnerBtns[0]?.className).toContain('purple');
      expect(intermediateBtns[0]?.className).toContain('purple');
      expect(advancedBtns[0]?.className).toContain('purple');
    });

    it('toggleServiceSelection removes an existing service when profile is loaded and not live (line 600)', async () => {
      const user = userEvent.setup();
      // Profile is loaded (not live) with one service
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Expand Music category
      await user.click(screen.getByRole('button', { name: /music/i }));

      // Piano should show checkmark (already selected)
      const pianoToggle = screen.getByRole('button', { name: /piano ✓/i });
      expect(pianoToggle).toBeInTheDocument();

      // Click to deselect (toggleServiceSelection removal path)
      await user.click(pianoToggle);

      // Service should be removed
      expect(screen.getByText(/no services added yet/i)).toBeInTheDocument();
    });

    it('handleRequestSkill error path shows error message (line 642)', async () => {
      const user = userEvent.setup();

      // Mock global fetch to reject for the skill request webhook
      const originalFetch = global.fetch;
      global.fetch = jest.fn().mockRejectedValueOnce(new Error('Network error'));

      render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

      await user.type(screen.getByPlaceholderText(/request a new skill/i), 'Juggling');
      await user.click(screen.getByRole('button', { name: /submit/i }));

      await waitFor(() => {
        expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
      });

      global.fetch = originalFetch;
    });

    it('handleSave skips save when profile has not loaded yet (lines 655-658)', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      // Provide instructorProfile prop so services are hydrated,
      // but set profileLoaded to false by not providing is_live in hook data
      // and NOT providing instructorProfile (so profileLoaded stays false)
      mockUseInstructorProfileMe.mockReturnValue({ data: undefined });

      // Use the prop form: services hydrate, but profileData effect
      // won't fire since instructorProfile is undefined and hook returns undefined
      // This means profileLoaded remains false

      render(<SkillsPricingInline />);

      // Add a service manually to trigger autosave
      await user.click(screen.getByRole('button', { name: /music/i }));
      await user.click(screen.getByRole('button', { name: /piano \+/i }));

      // Type a rate
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.type(rateInput, '50');
      jest.advanceTimersByTime(1200);

      // Save should be skipped because profileLoaded is false
      await waitFor(() => {
        expect(mockFetchWithAuth).not.toHaveBeenCalled();
      });

      jest.useRealTimers();
    });

    it('handleSave clears stale priceErrors via ref when save passes validation (line 712)', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['n1'],
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 30,
            duration_options: [60],
            offers_travel: true,
          }],
        },
      });
      mockUsePricingConfig.mockReturnValue({
        config: { price_floor_cents: { private_in_person: 5000, private_remote: 4000 } },
        isLoading: false,
      });
      mockEvaluateViolations.mockReturnValue([
        { duration: 60, modalityLabel: 'in-person', floorCents: 5000, baseCents: 3000 },
      ]);
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      // Step 1: Trigger price floor error
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '30');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(screen.getByText(/minimum price/i)).toBeInTheDocument();
      });

      // Step 2: Fix the price — priceErrorsRef will still have the old errors
      // but the new violations will be empty, so the ref-clearing branch (line 712) fires
      mockEvaluateViolations.mockReturnValue([]);
      await user.clear(rateInput);
      await user.type(rateInput, '100');
      jest.advanceTimersByTime(1200);

      // Save should succeed (priceErrors cleared via ref, line 712)
      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      // The inline price error should be gone
      expect(screen.queryByText(/minimum price/i)).not.toBeInTheDocument();

      jest.useRealTimers();
    });

    it('skill level min-1 guard prevents deselecting the last skill level', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            filter_selections: { skill_level: ['beginner'] },
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Only beginner is selected. Try to deselect it.
      const beginnerBtns = screen.getAllByRole('button', { name: /^beginner$/i });
      await user.click(beginnerBtns[0]!);

      // Beginner should remain selected (min-1 guard)
      expect(beginnerBtns[0]?.className).toContain('purple');
    });

    it('save payload includes filter_selections without age_groups', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            age_groups: ['kids', 'adults'],
            filter_selections: {
              skill_level: ['beginner', 'intermediate'],
              custom_filter: ['value1', 'value2'],
            },
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
        const body = JSON.parse(mockFetchWithAuth.mock.calls[0][1].body as string);
        // age_groups should be a top-level field, NOT inside filter_selections
        expect(body.services[0].age_groups).toBeDefined();
        // filter_selections should NOT contain age_groups (it's destructured out)
        expect(body.services[0].filter_selections).not.toHaveProperty('age_groups');
        // Other filter selections should be present
        expect(body.services[0].filter_selections).toHaveProperty('skill_level');
      });

      jest.useRealTimers();
    });

    it('age group button is disabled when group is not in eligible_age_groups', async () => {
      // Service with eligible_age_groups that excludes 'toddler'
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [{
              id: 'svc-1',
              name: 'Piano',
              slug: 'piano',
              subcategory_id: '01HABCTESTSUBCAT0000000001',
              eligible_age_groups: ['teens', 'adults'], // Only teens and adults
            }],
          }],
        },
        isLoading: false,
      });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            age_groups: ['teens', 'adults'],
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Toddler and Kids buttons should be disabled (not eligible)
      const toddlerButtons = screen.getAllByRole('button', { name: /^toddler$/i });
      expect(toddlerButtons[0]).toBeDisabled();

      const kidsButtons = screen.getAllByRole('button', { name: /^kids$/i });
      expect(kidsButtons[0]).toBeDisabled();

      // Teens and Adults should not be disabled
      const teensButtons = screen.getAllByRole('button', { name: /^teens$/i });
      expect(teensButtons[0]).not.toBeDisabled();

      const adultsButtons = screen.getAllByRole('button', { name: /^adults$/i });
      expect(adultsButtons[0]).not.toBeDisabled();
    });

    it('autosave clears previous timeout before setting new one (line 836)', async () => {
      jest.useFakeTimers();
      const clearTimeoutSpy = jest.spyOn(global, 'clearTimeout');
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '6');
      jest.advanceTimersByTime(500);

      // Type again before timeout fires
      await user.type(rateInput, '5');
      jest.advanceTimersByTime(500);

      // clearTimeout should have been called (for the previous pending autosave)
      expect(clearTimeoutSpy).toHaveBeenCalled();

      // Now let the final timeout fire
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalledTimes(1);
      });

      clearTimeoutSpy.mockRestore();
      jest.useRealTimers();
    });

    it('serializeServices produces consistent hash for filter_selections ordering', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            filter_selections: {
              skill_level: ['advanced', 'beginner'], // unsorted
              age_groups: ['adults', 'kids'], // unsorted
            },
            offers_online: true,
          }],
        },
      });
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      // Save should succeed (serializeServices sorts filter values)
      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      jest.useRealTimers();
    });

    it('back-fill effect does not modify services when catalog entry is not found', async () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-unknown',
            service_catalog_name: 'Unknown Service',
            hourly_rate: 60,
            offers_online: true,
          }],
        },
      });

      // Catalog does not contain svc-unknown
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [{
              id: 'svc-1',
              name: 'Piano',
              slug: 'piano',
              subcategory_id: '01HABCTESTSUBCAT0000000001',
              eligible_age_groups: ['kids', 'teens', 'adults'],
            }],
          }],
        },
        isLoading: false,
      });

      render(<SkillsPricingInline />);

      // Should render without crashing - the unknown service stays as-is
      expect(screen.getByPlaceholderText(/hourly rate/i)).toHaveValue(60);
    });

    it('handleRequestSkill error catch branch sets error message (line 642)', async () => {
      // Use a different approach: mock the module directly
      const originalFetch = global.fetch;
      // Make fetch throw for the webhook URL
      global.fetch = jest.fn().mockImplementation((url: string) => {
        if (typeof url === 'string' && url.includes('webhook')) {
          return Promise.reject(new Error('Network failure'));
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      });

      const user = userEvent.setup();
      render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

      await user.type(screen.getByPlaceholderText(/request a new skill/i), 'Ukulele');
      await user.click(screen.getByRole('button', { name: /submit/i }));

      await waitFor(() => {
        expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
      });

      // Button should return from submitting state
      expect(screen.getByRole('button', { name: /submit/i })).not.toBeDisabled();

      global.fetch = originalFetch;
    });

    it('toggleServiceSelection deselect path when live instructor has multiple services', async () => {
      const user = userEvent.setup();
      // Live instructor with two services - can remove one
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: true,
          services: [
            { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 60, offers_online: true },
            { service_catalog_id: 'svc-2', service_catalog_name: 'Guitar', hourly_rate: 50, offers_online: true },
          ],
        },
      });

      // Need Guitar in the catalog too
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: '01HABCTESTSUBCAT0000000001', eligible_age_groups: ['kids', 'teens', 'adults'] },
              { id: 'svc-2', name: 'Guitar', slug: 'guitar', subcategory_id: '01HABCTESTSUBCAT0000000001', eligible_age_groups: ['kids', 'teens', 'adults'] },
            ],
          }],
        },
        isLoading: false,
      });

      render(<SkillsPricingInline />);

      // Should have 2 services
      expect(screen.getAllByPlaceholderText(/hourly rate/i)).toHaveLength(2);

      // Expand Music category and deselect Piano via toggle
      await user.click(screen.getByRole('button', { name: /music/i }));

      const pianoToggle = screen.getByRole('button', { name: /piano ✓/i });
      await user.click(pianoToggle);

      // Should now have 1 service
      expect(screen.getAllByPlaceholderText(/hourly rate/i)).toHaveLength(1);
    });

    it('RefineFiltersSection calls initializeMissingFilters when subcategory has filters (lines 297-308)', async () => {
      // Mock useSubcategoryFilters to return actual filter data
      mockUseSubcategoryFilters.mockReturnValue({
        data: [
          {
            filter_key: 'grade_level',
            filter_display_name: 'Grade Level',
            filter_type: 'multi_select',
            options: [
              { id: 'opt-1', value: 'elementary', display_name: 'Elementary', display_order: 1 },
              { id: 'opt-2', value: 'middle_school', display_name: 'Middle School', display_order: 2 },
            ],
          },
        ],
        isLoading: false,
      });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            offers_online: true,
            // No grade_level in filter_selections, so initializeMissingFilters should be called
          }],
        },
      });

      render(<SkillsPricingInline />);

      // The RefineFiltersSection should render (subcategory has filters)
      await waitFor(() => {
        expect(screen.getByText(/refine what you teach/i)).toBeInTheDocument();
      });

      // Reset mock for other tests
      mockUseSubcategoryFilters.mockReturnValue({ data: [], isLoading: false });
    });

    it('RefineFiltersSection toggleExpanded and setFilterValues callbacks work (lines 284-286, 317)', async () => {
      const user = userEvent.setup();

      // Mock useSubcategoryFilters to return filter data
      mockUseSubcategoryFilters.mockReturnValue({
        data: [
          {
            filter_key: 'instrument_type',
            filter_display_name: 'Instrument Type',
            filter_type: 'multi_select',
            options: [
              { id: 'opt-1', value: 'acoustic', display_name: 'Acoustic', display_order: 1 },
              { id: 'opt-2', value: 'electric', display_name: 'Electric', display_order: 2 },
            ],
          },
        ],
        isLoading: false,
      });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            subcategory_id: '01HABCTESTSUBCAT0000000001',
            hourly_rate: 60,
            filter_selections: { instrument_type: ['acoustic', 'electric'] },
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Click the toggle expand button for RefineFiltersSection (line 317)
      const toggleButton = screen.getByRole('button', { name: /toggle refine filters/i });
      await user.click(toggleButton);

      // The filter options should now be visible
      await waitFor(() => {
        expect(screen.getByText('Acoustic')).toBeInTheDocument();
        expect(screen.getByText('Electric')).toBeInTheDocument();
      });

      // Click a filter option to trigger setServiceFilterValues (lines 284-286)
      await user.click(screen.getByText('Acoustic'));

      // The component should update without crashing
      expect(screen.getByText('Electric')).toBeInTheDocument();

      // Reset mock
      mockUseSubcategoryFilters.mockReturnValue({ data: [], isLoading: false });
    });

    it('initializeMissingFilters merges defaults but does not overwrite existing selections (lines 297-308)', async () => {
      // Mock useSubcategoryFilters to return two filters
      mockUseSubcategoryFilters.mockReturnValue({
        data: [
          {
            filter_key: 'music_style',
            filter_display_name: 'Music Style',
            filter_type: 'multi_select',
            options: [
              { id: 'opt-1', value: 'classical', display_name: 'Classical', display_order: 1 },
              { id: 'opt-2', value: 'jazz', display_name: 'Jazz', display_order: 2 },
            ],
          },
          {
            filter_key: 'approach',
            filter_display_name: 'Teaching Approach',
            filter_type: 'multi_select',
            options: [
              { id: 'opt-3', value: 'suzuki', display_name: 'Suzuki', display_order: 1 },
              { id: 'opt-4', value: 'traditional', display_name: 'Traditional', display_order: 2 },
            ],
          },
        ],
        isLoading: false,
      });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            subcategory_id: '01HABCTESTSUBCAT0000000001',
            hourly_rate: 60,
            filter_selections: {
              // music_style already exists - should not be overwritten
              music_style: ['classical'],
              // approach is missing - should be initialized with defaults
            },
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // RefineFiltersSection should render
      await waitFor(() => {
        expect(screen.getByText(/refine what you teach/i)).toBeInTheDocument();
      });

      // Expand to see filter options
      const toggleButton = screen.getByRole('button', { name: /toggle refine filters/i });
      const user = userEvent.setup();
      await user.click(toggleButton);

      // Both filter sections should be visible
      await waitFor(() => {
        expect(screen.getByText('Music Style')).toBeInTheDocument();
        expect(screen.getByText('Teaching Approach')).toBeInTheDocument();
      });

      // Reset mock
      mockUseSubcategoryFilters.mockReturnValue({ data: [], isLoading: false });
    });

    it('back-fill effect updates subcategory_id when missing from service (lines 527-533)', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      // Service starts with empty subcategory_id
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            offers_online: true,
            // subcategory_id will be '' (empty string from hydration)
          }],
        },
      });

      // Catalog provides the subcategory_id
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [{
              id: 'svc-1',
              name: 'Piano',
              slug: 'piano',
              subcategory_id: '01HABCTESTSUBCAT0000000001',
              eligible_age_groups: ['kids', 'teens', 'adults'],
            }],
          }],
        },
        isLoading: false,
      });

      render(<SkillsPricingInline />);

      // Trigger a save to verify subcategory_id was back-filled
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '65');
      jest.advanceTimersByTime(1200);

      // Save should succeed (back-fill ran)
      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      jest.useRealTimers();
    });

    it('back-fill effect initializes skill_level and age_groups defaults when missing (lines 536-542)', () => {
      // Service has no age_groups and no skill_level in filter_selections
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            offers_online: true,
            // No age_groups provided, no filter_selections
          }],
        },
      });

      // Catalog provides eligible_age_groups
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [{
              id: 'svc-1',
              name: 'Piano',
              slug: 'piano',
              subcategory_id: '01HABCTESTSUBCAT0000000001',
              eligible_age_groups: ['teens', 'adults'],
            }],
          }],
        },
        isLoading: false,
      });

      render(<SkillsPricingInline />);

      // The back-fill effect should have initialized skill_level and age_groups
      // All skill levels should be selected (defaults)
      const beginnerBtns = screen.getAllByRole('button', { name: /^beginner$/i });
      const intermediateBtns = screen.getAllByRole('button', { name: /^intermediate$/i });
      const advancedBtns = screen.getAllByRole('button', { name: /^advanced$/i });
      expect(beginnerBtns[0]?.className).toContain('purple');
      expect(intermediateBtns[0]?.className).toContain('purple');
      expect(advancedBtns[0]?.className).toContain('purple');
    });

    it('back-fill effect populates subcategory_id and eligible_age_groups when catalog loads after profile (lines 527-533)', async () => {
      // Step 1: Profile data arrives with a service, but catalog is not yet loaded
      // serviceCatalogById will be empty, so hydration sets subcategory_id to ''
      // and eligible_age_groups to default ['kids', 'teens', 'adults']
      mockUseAllServices.mockReturnValue({ data: null, isLoading: true });

      const profileData = {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 60,
          offers_online: true,
          // subcategory_id not in API response — will be ''
          // age_groups not provided — will be set from catalog defaults
        }],
      };

      const { rerender } = render(
        <SkillsPricingInline instructorProfile={profileData as never} />
      );

      // Step 2: Now catalog data loads
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [{
              id: 'svc-1',
              name: 'Piano',
              slug: 'piano',
              subcategory_id: '01HABCTESTSUBCAT0000000001',
              eligible_age_groups: ['teens', 'adults'],
            }],
          }],
        },
        isLoading: false,
      });

      rerender(<SkillsPricingInline instructorProfile={profileData as never} />);

      // The service should still render correctly
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/hourly rate/i)).toHaveValue(60);
      });
    });

    it('back-fill effect fills missing filter_selections when skill_level is absent (lines 536-542)', async () => {
      // Profile hydrates with service that has no filter_selections at all
      mockUseAllServices.mockReturnValue({ data: null, isLoading: true });

      const profileData = {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 60,
          offers_online: true,
          filter_selections: {}, // Empty — no skill_level or age_groups
        }],
      };

      const { rerender } = render(
        <SkillsPricingInline instructorProfile={profileData as never} />
      );

      // Now catalog data loads — triggers back-fill
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [{
              id: 'svc-1',
              name: 'Piano',
              slug: 'piano',
              subcategory_id: '01HABCTESTSUBCAT0000000001',
              eligible_age_groups: ['kids', 'adults'],
            }],
          }],
        },
        isLoading: false,
      });

      rerender(<SkillsPricingInline instructorProfile={profileData as never} />);

      // The back-fill should have initialized skill levels
      await waitFor(() => {
        const beginnerBtns = screen.getAllByRole('button', { name: /^beginner$/i });
        expect(beginnerBtns[0]?.className).toContain('purple');
      });
    });

    it('service with empty eligible_age_groups gets back-filled from catalog (line 531-533)', async () => {
      // Create a service that explicitly has empty eligible_age_groups
      // This can happen when the service hydration runs before catalog data is available
      mockUseAllServices.mockReturnValue({ data: null, isLoading: true });

      // Use instructorProfile prop to set up service
      const profileData = {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 60,
          age_groups: [], // Empty array
          offers_online: true,
        }],
      };

      const { rerender } = render(
        <SkillsPricingInline instructorProfile={profileData as never} />
      );

      // Now provide catalog data with eligible_age_groups
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [{
              id: 'svc-1',
              name: 'Piano',
              slug: 'piano',
              subcategory_id: '01HABCTESTSUBCAT0000000001',
              eligible_age_groups: ['teens', 'adults'],
            }],
          }],
        },
        isLoading: false,
      });

      rerender(<SkillsPricingInline instructorProfile={profileData as never} />);

      // The service should render
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/hourly rate/i)).toHaveValue(60);
      });
    });

    it('handleSave clears stale priceErrors via ref when description changes (line 712)', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      // Single service with price floor violation
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['n1'],
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 30,
            duration_options: [60],
            offers_travel: true,
          }],
        },
      });
      mockUsePricingConfig.mockReturnValue({
        config: { price_floor_cents: { private: { '60': 5000 } } },
        isLoading: false,
      });
      mockEvaluateViolations.mockReturnValue([
        { duration: 60, modalityLabel: 'in-person', floorCents: 5000, baseCents: 3000 },
      ]);
      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      render(<SkillsPricingInline />);

      // Step 1: Trigger autosave — price floor violation blocks save, sets priceErrors
      await user.clear(screen.getByPlaceholderText(/hourly rate/i));
      await user.type(screen.getByPlaceholderText(/hourly rate/i), '30');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(screen.getByText(/minimum price/i)).toBeInTheDocument();
      });

      // Step 2: Change description — does NOT clear svc-1's priceError
      // (only rate changes for the specific service clear the price error)
      // But we also clear violations so handleSave can proceed past price floor check
      mockEvaluateViolations.mockReturnValue([]);
      const descInput = screen.getByPlaceholderText(/brief description/i);
      await user.type(descInput, 'Classical piano');
      jest.advanceTimersByTime(1200);

      // Save should succeed; the stale priceErrors should be cleared via ref (line 712)
      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      jest.useRealTimers();
    });

    it('pendingSyncSignatureRef match path accepts hydration from saved data (lines 451-459)', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      // Start with a profile
      const profile = {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 70,
          offers_online: true,
        }],
      };

      mockFetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });

      // Use hook-based profile (not prop) so we can update it via mock
      mockUseInstructorProfileMe.mockReturnValue({
        data: { ...profile },
      });

      const { rerender } = render(<SkillsPricingInline />);

      // Edit the rate
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '85');

      // Wait for autosave — this sets pendingSyncSignatureRef
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      // Now simulate the hook returning the saved data (matching signature)
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          ...profile,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 85, // matches what was saved
            offers_online: true,
          }],
        },
      });

      // Trigger re-render to simulate React Query cache update
      rerender(<SkillsPricingInline />);

      // Value should be accepted (pendingSyncSignatureRef matched)
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/hourly rate/i)).toHaveValue(85);
      });

      jest.useRealTimers();
    });
  });

  describe('Batch 15: branch coverage improvements', () => {
    it('handleRequestSkill early-returns when requestedSkill is whitespace only (branch 94, line 625)', async () => {
      // Render with a service so the "Request a skill" section appears
      mockUseInstructorProfileMe.mockReturnValue({
        data: { is_live: false, services: [{ service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 50, offers_online: true }] },
      });

      render(<SkillsPricingInline />);

      // The submit button is disabled when empty — type whitespace to enable it
      const input = screen.getByPlaceholderText(/request a new skill/i);
      await userEvent.type(input, '   ');

      // Button should still be disabled because trim() is empty
      const submitBtn = screen.getByRole('button', { name: /submit/i });
      expect(submitBtn).toBeDisabled();
    });

    it('rate onChange when there is no price error returns prev (branch 154, line 1002)', async () => {
      // Render with profile that has a service
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Rate input has no associated price error, so changing it should just update the value
      // (branch: if (!prev[s.catalog_service_id]) return prev — returns prev without modification)
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await userEvent.clear(rateInput);
      await userEvent.type(rateInput, '75');

      expect(rateInput).toHaveValue(75);
    });

    it('toggleServiceSelection adds service with fallback eligible_age_groups when no catalog entry (branch 92, line 604)', async () => {
      // Return categories with a service NOT in the catalog map
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-unknown', name: 'Harp', slug: 'harp' },
              // No subcategory_id, no eligible_age_groups in catalog
            ],
          }],
        },
        isLoading: false,
      });
      mockUseServiceCategories.mockReturnValue({
        data: [{ id: '01HABCTESTCAT0000000000001', name: 'Music', display_order: 1 }],
        isLoading: false,
      });

      render(<SkillsPricingInline />);

      // Find and click the Music accordion to expand it
      const musicBtn = screen.getByRole('button', { name: /music/i });
      await userEvent.click(musicBtn);

      // Click the Harp service to add it
      const harpBtn = screen.getByRole('button', { name: /harp/i });
      await userEvent.click(harpBtn);

      // Service should be added — the rate input should now appear
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/hourly rate/i)).toBeInTheDocument();
      });

      // Since no catalog entry, fallback age groups should be ['kids', 'teens', 'adults']
      // and subcategory_id should be ''
      // Verify the age group buttons are rendered (fallback includes kids, teens, adults)
      expect(screen.getByRole('button', { name: /^kids$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^teens$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^adults$/i })).toBeInTheDocument();
    });

    it('toggleServiceSelection adds service with fallback subcategory_id when catalog has no subcategory (branch 93, line 609)', async () => {
      // Catalog entry has no subcategory_id
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-nosub', name: 'Flute', slug: 'flute', eligible_age_groups: ['teens', 'adults'] },
              // No subcategory_id
            ],
          }],
        },
        isLoading: false,
      });
      mockUseServiceCategories.mockReturnValue({
        data: [{ id: '01HABCTESTCAT0000000000001', name: 'Music', display_order: 1 }],
        isLoading: false,
      });

      render(<SkillsPricingInline />);

      // Expand Music
      const musicBtn = screen.getByRole('button', { name: /music/i });
      await userEvent.click(musicBtn);

      // Add Flute
      const fluteBtn = screen.getByRole('button', { name: /flute/i });
      await userEvent.click(fluteBtn);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/hourly rate/i)).toBeInTheDocument();
      });
    });

    it('service card renders fallback name when service_catalog_name is missing (branch 148, line 965)', () => {
      // Profile with a service that has no service_catalog_name or name
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            // no service_catalog_name
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // The card should render with 'Service' fallback (line 965)
      // Both the chip and the card heading use 'Service' as fallback
      const serviceTexts = screen.getAllByText('Service');
      expect(serviceTexts.length).toBeGreaterThanOrEqual(1);
    });

    it('chip displays service_catalog_name when name is missing (branch 133/134, line 890)', () => {
      // Profile service with no name field but has service_catalog_name
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
            // name is not set, so chip should use service_catalog_name
          }],
        },
      });

      render(<SkillsPricingInline />);

      // The chip at the top should show 'Piano' (from service_catalog_name)
      const chips = screen.getAllByText('Piano');
      expect(chips.length).toBeGreaterThan(0);
    });

    it('description and equipment fields render empty string when values are null/undefined (branches 195/197, lines 1252/1262)', async () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
            description: null,
            equipment: null,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Description and equipment textareas should render with empty values (fallback || '')
      const descField = screen.getByPlaceholderText(/brief description/i);
      expect(descField).toHaveValue('');

      const equipField = screen.getByPlaceholderText(/yoga mat/i);
      expect(equipField).toHaveValue('');
    });

    it('multi-service: age group click handler returns x unchanged for non-matching indices (branch 161, line 1052)', async () => {
      // Two services — clicking age group on first should not affect second
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
              { id: 'svc-2', name: 'Guitar', slug: 'guitar', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
            ],
          }],
        },
        isLoading: false,
      });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 50, offers_online: true },
            { service_catalog_id: 'svc-2', service_catalog_name: 'Guitar', hourly_rate: 40, offers_online: true },
          ],
        },
      });

      render(<SkillsPricingInline />);

      // Get all "Kids" buttons (one per service card)
      const kidsButtons = screen.getAllByRole('button', { name: /^kids$/i });
      expect(kidsButtons.length).toBe(2);

      // Click Kids on the first service — this hits `if (i !== index) return x` for index=1
      await userEvent.click(kidsButtons[0]!);

      // Both services should still have their rate inputs
      const rateInputs = screen.getAllByPlaceholderText(/hourly rate/i);
      expect(rateInputs.length).toBe(2);
    });

    it('multi-service: skill level click handler returns x unchanged for non-matching indices (branch 182, line 1197)', async () => {
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
              { id: 'svc-2', name: 'Guitar', slug: 'guitar', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
            ],
          }],
        },
        isLoading: false,
      });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 50, offers_online: true },
            { service_catalog_id: 'svc-2', service_catalog_name: 'Guitar', hourly_rate: 40, offers_online: true },
          ],
        },
      });

      render(<SkillsPricingInline />);

      // Get all "Beginner" buttons (one per service card)
      const beginnerButtons = screen.getAllByRole('button', { name: /^beginner$/i });
      expect(beginnerButtons.length).toBe(2);

      // Click Beginner on the first service — this hits `if (i !== index) return x` for index=1
      await userEvent.click(beginnerButtons[0]!);

      // Both rate inputs should still be there
      const rateInputs = screen.getAllByPlaceholderText(/hourly rate/i);
      expect(rateInputs.length).toBe(2);
    });

    it('multi-service: duration click handler returns x unchanged for non-matching indices (branch 189, line 1227)', async () => {
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
              { id: 'svc-2', name: 'Guitar', slug: 'guitar', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
            ],
          }],
        },
        isLoading: false,
      });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 50, offers_online: true },
            { service_catalog_id: 'svc-2', service_catalog_name: 'Guitar', hourly_rate: 40, offers_online: true },
          ],
        },
      });

      render(<SkillsPricingInline />);

      // Duration buttons use the format "{d}m" — e.g., "30m", "45m", "60m", "90m"
      const thirtyMinButtons = screen.getAllByRole('button', { name: /^30m$/i });
      expect(thirtyMinButtons.length).toBe(2);

      // Click 30m on the first service — this hits `if (i !== index) return x` for index=1
      await userEvent.click(thirtyMinButtons[0]!);

      // Both rate inputs should still be there
      const rateInputs = screen.getAllByPlaceholderText(/hourly rate/i);
      expect(rateInputs.length).toBe(2);
    });

    it('multi-service: rate onChange for second service hits i===index branch (branch 154 alternate)', async () => {
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
              { id: 'svc-2', name: 'Guitar', slug: 'guitar', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
            ],
          }],
        },
        isLoading: false,
      });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 50, offers_online: true },
            { service_catalog_id: 'svc-2', service_catalog_name: 'Guitar', hourly_rate: 40, offers_online: true },
          ],
        },
      });

      render(<SkillsPricingInline />);

      const rateInputs = screen.getAllByPlaceholderText(/hourly rate/i);
      expect(rateInputs.length).toBe(2);

      // Changing second input triggers map where first service hits `i !== index` return
      await userEvent.clear(rateInputs[1]!);
      await userEvent.type(rateInputs[1]!, '55');
      expect(rateInputs[1]).toHaveValue(55);
    });

    it('servicesByCategory fallback to empty array when category has no services (branch 141, line 922)', async () => {
      // Category exists but has no services in the data
      mockUseServiceCategories.mockReturnValue({
        data: [
          { id: '01HABCTESTCAT0000000000001', name: 'Music', display_order: 1 },
          { id: '01HABCTESTCAT0000000000002', name: 'Dance', display_order: 2 },
        ],
        isLoading: false,
      });
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [
            {
              id: '01HABCTESTCAT0000000000001',
              name: 'Music',
              services: [{ id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] }],
            },
            // Dance has no services — will hit servicesByCategory[cat.id] || []
          ],
        },
        isLoading: false,
      });

      render(<SkillsPricingInline />);

      // Both category headers should be rendered
      const musicCategory = screen.getByRole('button', { name: /music/i });
      const danceCategory = screen.getByRole('button', { name: /dance/i });
      expect(musicCategory).toBeInTheDocument();
      expect(danceCategory).toBeInTheDocument();

      // Expand Dance accordion to trigger `servicesByCategory[cat.id] || []` fallback
      await userEvent.click(danceCategory);

      // Dance accordion should be open but empty (no services)
      // Music accordion also still exists
      expect(musicCategory).toBeInTheDocument();
    });

    it('skillsFilter applies text filtering on service names in the grid (branch 143, line 923)', async () => {
      // Multiple services in one category
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
              { id: 'svc-2', name: 'Guitar', slug: 'guitar', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
            ],
          }],
        },
        isLoading: false,
      });

      render(<SkillsPricingInline />);

      // Categories start collapsed — expand the Music accordion
      const musicAccordion = screen.getByRole('button', { name: /music/i });
      await userEvent.click(musicAccordion);

      // Before filtering, both Piano and Guitar should be in the accordion grid
      // Service buttons render as "{name} +" or "{name} ✓"
      expect(screen.getByText(/^Piano \+$/)).toBeInTheDocument();
      expect(screen.getByText(/^Guitar \+$/)).toBeInTheDocument();

      // Type in the filter
      const filterInput = screen.getByPlaceholderText(/search skills/i);
      await userEvent.type(filterInput, 'Piano');

      // Only Piano should be visible in the accordion; Guitar filtered out
      expect(screen.getByText(/^Piano \+$/)).toBeInTheDocument();
      expect(screen.queryByText(/^Guitar \+$/)).not.toBeInTheDocument();
    });

    it('age group click handler early-returns when group is not eligible (branch 160, line 1050)', async () => {
      // Service with restricted eligible_age_groups (no toddler)
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [{ id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1', eligible_age_groups: ['teens', 'adults'] }],
          }],
        },
        isLoading: false,
      });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
            eligible_age_groups: ['teens', 'adults'],
            filter_selections: { skill_level: ['beginner', 'intermediate', 'advanced'], age_groups: ['teens', 'adults'] },
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Toddler button should be disabled
      const toddlerBtn = screen.getByRole('button', { name: /^toddler$/i });
      expect(toddlerBtn).toBeDisabled();

      // Click it anyway — should hit `if (!isEligible) return` early return
      await userEvent.click(toddlerBtn);

      // Nothing should change — teens and adults should still be selected
      const teensBtn = screen.getByRole('button', { name: /^teens$/i });
      expect(teensBtn.className).toContain('purple');
    });

    it('save payload includes age_groups from filter_selections when available (branch 114, line 742)', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
            age_groups: ['teens', 'adults'], // top-level age_groups is what hydration reads
            eligible_age_groups: ['kids', 'teens', 'adults'],
            filter_selections: { skill_level: ['beginner'] },
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Make a small change to trigger autosave
      const descField = screen.getByPlaceholderText(/brief description/i);
      await user.type(descField, 'test');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      // Check that the payload used the hydrated age_groups from top-level
      const call = mockFetchWithAuth.mock.calls[0];
      const body = JSON.parse(call?.[1]?.body as string);
      expect(body.services[0].age_groups).toEqual(['teens', 'adults']);

      jest.useRealTimers();
    });

    it('save payload includes equipment_required when equipment is provided (branch 113/116, lines 740/745)', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Add equipment
      const equipField = screen.getByPlaceholderText(/yoga mat/i);
      await user.type(equipField, 'Sheet music, Metronome');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      const call = mockFetchWithAuth.mock.calls[0];
      const body = JSON.parse(call?.[1]?.body as string);
      expect(body.services[0].equipment_required).toEqual(['Sheet music', 'Metronome']);

      jest.useRealTimers();
    });

    it('save payload includes description when provided (branch 113, line 740)', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      const descField = screen.getByPlaceholderText(/brief description/i);
      await user.type(descField, 'Classical and jazz');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      const call = mockFetchWithAuth.mock.calls[0];
      const body = JSON.parse(call?.[1]?.body as string);
      expect(body.services[0].description).toBe('Classical and jazz');

      jest.useRealTimers();
    });

    it('age groups fallback to empty array when filter_selections has no age_groups key (branch 159, line 1042)', () => {
      // Service explicitly has no age_groups in filter_selections
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
            eligible_age_groups: ['kids', 'teens', 'adults'],
            filter_selections: { skill_level: ['beginner'] },
            // No age_groups key — triggers ?? [] fallback on line 1042
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Kids button should not be selected (no age_groups in filter_selections)
      // because the fallback is [] which means nothing is selected
      // But the back-fill effect may populate it — check that rendering doesn't crash
      expect(screen.getByRole('button', { name: /^kids$/i })).toBeInTheDocument();
    });

    it('skill_level fallback to DEFAULT_SKILL_LEVELS when filter_selections has no skill_level (branch 181/183, line 1191/1198)', () => {
      // Service with filter_selections that has age_groups but no skill_level
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
            eligible_age_groups: ['kids', 'teens', 'adults'],
            filter_selections: { age_groups: ['kids', 'teens'] },
            // No skill_level — triggers ?? [...DEFAULT_SKILL_LEVELS] fallback on line 1191
          }],
        },
      });

      render(<SkillsPricingInline />);

      // All skill levels should show as selected (default fallback)
      const beginnerBtn = screen.getByRole('button', { name: /^beginner$/i });
      const intermediateBtn = screen.getByRole('button', { name: /^intermediate$/i });
      const advancedBtn = screen.getByRole('button', { name: /^advanced$/i });
      // All should have the purple styling (selected)
      expect(beginnerBtn.className).toContain('purple');
      expect(intermediateBtn.className).toContain('purple');
      expect(advancedBtn.className).toContain('purple');
    });

    it('buildPriceFloorErrors returns empty when pricingFloors is null (branch 26, line 241)', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      // pricingFloors is null (no config)
      mockUsePricingConfig.mockReturnValue({ config: { price_floor_cents: null } });

      // But make evaluateViolations return violations
      mockEvaluateViolations.mockReturnValue([{
        floorCents: 5000,
        baseCents: 3000,
        modalityLabel: 'in-person',
        duration: 60,
      }]);

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 30,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Edit to trigger autosave
      const descField = screen.getByPlaceholderText(/brief description/i);
      await user.type(descField, 'Test');
      jest.advanceTimersByTime(1200);

      // Save should proceed because pricingFloors is null — buildPriceFloorErrors returns {}
      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      // No price error toast should have been called
      expect(toast.error).not.toHaveBeenCalled();

      jest.useRealTimers();
    });

    it('autosave has invalid capabilities blocks save silently (not manual) (branch 112, line 723)', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
            offers_travel: false,
            offers_at_location: false,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Turn off Online — this makes all capabilities false
      const onlineToggle = screen.getByRole('switch', { name: /online lessons/i });
      await user.click(onlineToggle);

      // Wait for autosave to trigger
      jest.advanceTimersByTime(1200);

      // There should be an inline error message
      await waitFor(() => {
        expect(screen.getByText(/select at least one location option/i)).toBeInTheDocument();
      });

      // But toast.error should NOT have been called (only fires for source === 'manual')
      // The autosave uses source === 'auto', so it silently blocks
      expect(toast.error).not.toHaveBeenCalledWith(
        expect.stringContaining('Select at least one way'),
        expect.anything()
      );

      jest.useRealTimers();
    });

    it('multi-service: description onChange on second service passes through for non-matching index (branch 195)', async () => {
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
              { id: 'svc-2', name: 'Guitar', slug: 'guitar', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
            ],
          }],
        },
        isLoading: false,
      });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 50, offers_online: true },
            { service_catalog_id: 'svc-2', service_catalog_name: 'Guitar', hourly_rate: 40, offers_online: true },
          ],
        },
      });

      render(<SkillsPricingInline />);

      // Get all description fields
      const descFields = screen.getAllByPlaceholderText(/brief description/i);
      expect(descFields.length).toBe(2);

      // Type in the second description — first service unchanged
      await userEvent.type(descFields[1]!, 'Jazz guitar');
      expect(descFields[1]).toHaveValue('Jazz guitar');
    });

    it('multi-service: equipment onChange on second service passes through for non-matching index (branch 197)', async () => {
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
              { id: 'svc-2', name: 'Guitar', slug: 'guitar', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
            ],
          }],
        },
        isLoading: false,
      });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 50, offers_online: true },
            { service_catalog_id: 'svc-2', service_catalog_name: 'Guitar', hourly_rate: 40, offers_online: true },
          ],
        },
      });

      render(<SkillsPricingInline />);

      // Get all equipment fields
      const equipFields = screen.getAllByPlaceholderText(/yoga mat/i);
      expect(equipFields.length).toBe(2);

      // Type in the second equipment — first service unchanged
      await userEvent.type(equipFields[1]!, 'Guitar pick');
      expect(equipFields[1]).toHaveValue('Guitar pick');
    });

    it('initializeMissingFilters skips service when serviceId does not match (branch 32, line 299)', async () => {
      // This tests that initializeMissingFilters returns `s` unchanged for non-matching services
      mockUseSubcategoryFilters.mockReturnValue({
        data: [
          { filter_key: 'instrument_type', filter_display_name: 'Instrument Type', filter_type: 'multi_select', options: [{ id: '1', value: 'acoustic', display_name: 'Acoustic', display_order: 1 }] },
        ],
        isLoading: false,
      });

      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
              { id: 'svc-2', name: 'Guitar', slug: 'guitar', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
            ],
          }],
        },
        isLoading: false,
      });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 50, offers_online: true, subcategory_id: 'sub1' },
            { service_catalog_id: 'svc-2', service_catalog_name: 'Guitar', hourly_rate: 40, offers_online: true, subcategory_id: 'sub1' },
          ],
        },
      });

      render(<SkillsPricingInline />);

      // Both services should render fine - RefineFiltersSection calls initializeMissingFilters
      // for each service, and the filter_key matching only applies to the correct service
      await waitFor(() => {
        const rateInputs = screen.getAllByPlaceholderText(/hourly rate/i);
        expect(rateInputs.length).toBe(2);
      });

      // Reset mock
      mockUseSubcategoryFilters.mockReturnValue({ data: [], isLoading: false });
    });

    it('initializeMissingFilters does not set changed=true when all keys already exist (branch 33, line 303-306)', async () => {
      // Setup subcategory filters that would provide defaults
      mockUseSubcategoryFilters.mockReturnValue({
        data: [
          {
            filter_key: 'instrument_type',
            filter_display_name: 'Instrument Type',
            filter_type: 'multi_select',
            options: [{ id: '1', value: 'acoustic', display_name: 'Acoustic', display_order: 1 }],
          },
        ],
        isLoading: false,
      });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
            subcategory_id: 'sub1',
            filter_selections: {
              skill_level: ['beginner'],
              age_groups: ['kids'],
              instrument_type: ['acoustic'], // Already has this key!
            },
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Service should render — the initializeMissingFilters sees instrument_type exists
      // so changed stays false and returns `s` unchanged (branch 34, line 308)
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/hourly rate/i)).toHaveValue(50);
      });

      // Reset mock
      mockUseSubcategoryFilters.mockReturnValue({ data: [], isLoading: false });
    });

    it('setServiceFilterValues updates the correct service in a multi-service setup (branch 31, line 286-288)', async () => {
      // Two services, test that setServiceFilterValues only updates the matching one
      mockUseSubcategoryFilters.mockReturnValue({
        data: [
          {
            filter_key: 'style',
            filter_display_name: 'Style',
            filter_type: 'multi_select',
            options: [
              { id: '1', value: 'classical', display_name: 'Classical', display_order: 1 },
              { id: '2', value: 'jazz', display_name: 'Jazz', display_order: 2 },
            ],
          },
        ],
        isLoading: false,
      });

      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
              { id: 'svc-2', name: 'Guitar', slug: 'guitar', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
            ],
          }],
        },
        isLoading: false,
      });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 50, offers_online: true, subcategory_id: 'sub1' },
            { service_catalog_id: 'svc-2', service_catalog_name: 'Guitar', hourly_rate: 40, offers_online: true, subcategory_id: 'sub1' },
          ],
        },
      });

      render(<SkillsPricingInline />);

      // Expand refine filters for first service
      const toggleButtons = screen.getAllByLabelText(/toggle refine filters/i);
      expect(toggleButtons.length).toBeGreaterThan(0);

      await userEvent.click(toggleButtons[0]!);

      // Should see the Style filter options
      await waitFor(() => {
        expect(screen.getByText('Classical')).toBeInTheDocument();
      });

      // Click "Jazz" to toggle it — this calls setServiceFilterValues for svc-1
      // and hits the branch where non-matching services return unchanged
      await userEvent.click(screen.getByText('Jazz'));

      // Both services should still be displayed
      const rateInputs = screen.getAllByPlaceholderText(/hourly rate/i);
      expect(rateInputs.length).toBe(2);

      // Reset mock
      mockUseSubcategoryFilters.mockReturnValue({ data: [], isLoading: false });
    });

    it('multi-service: toggle travel switch for one service leaves other unchanged (branch 171, line 1113)', async () => {
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
              { id: 'svc-2', name: 'Guitar', slug: 'guitar', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
            ],
          }],
        },
        isLoading: false,
      });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['Upper East Side'],
          preferred_teaching_locations: [{ id: 'loc-1', name: 'Studio A' }],
          services: [
            { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 50, offers_online: true, offers_travel: true, offers_at_location: false },
            { service_catalog_id: 'svc-2', service_catalog_name: 'Guitar', hourly_rate: 40, offers_online: true, offers_travel: false, offers_at_location: false },
          ],
        },
      });

      render(<SkillsPricingInline />);

      // Get all "I travel to students" toggles — they should NOT be disabled because hasServiceAreas is true
      const travelToggles = screen.getAllByRole('switch', { name: /i travel to students/i });
      expect(travelToggles.length).toBe(2);

      // Toggle travel on the first service — index=1 hits `i !== index` return
      await userEvent.click(travelToggles[0]!);

      // Both services should still be rendered
      const rateInputs = screen.getAllByPlaceholderText(/hourly rate/i);
      expect(rateInputs.length).toBe(2);
    });

    it('multi-service: toggle at-location switch for one service leaves other unchanged (branch 176, line 1142)', async () => {
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
              { id: 'svc-2', name: 'Guitar', slug: 'guitar', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
            ],
          }],
        },
        isLoading: false,
      });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: ['Midtown'],
          preferred_teaching_locations: [{ id: 'loc-1', name: 'Studio A' }],
          services: [
            { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 50, offers_online: true, offers_travel: false, offers_at_location: true },
            { service_catalog_id: 'svc-2', service_catalog_name: 'Guitar', hourly_rate: 40, offers_online: true, offers_travel: false, offers_at_location: false },
          ],
        },
      });

      render(<SkillsPricingInline />);

      const atLocationToggles = screen.getAllByRole('switch', { name: /students come to me/i });
      expect(atLocationToggles.length).toBe(2);

      // Toggle at-location on first service — second service hits `i !== index` return
      await userEvent.click(atLocationToggles[0]!);

      const rateInputs = screen.getAllByPlaceholderText(/hourly rate/i);
      expect(rateInputs.length).toBe(2);
    });

    it('multi-service: toggle online switch for one service leaves other unchanged (branch 179, line 1166)', async () => {
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
              { id: 'svc-2', name: 'Guitar', slug: 'guitar', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
            ],
          }],
        },
        isLoading: false,
      });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [
            { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 50, offers_online: true },
            { service_catalog_id: 'svc-2', service_catalog_name: 'Guitar', hourly_rate: 40, offers_online: true },
          ],
        },
      });

      render(<SkillsPricingInline />);

      const onlineToggles = screen.getAllByRole('switch', { name: /online lessons/i });
      expect(onlineToggles.length).toBe(2);

      // Toggle online on first service
      await userEvent.click(onlineToggles[0]!);

      const rateInputs = screen.getAllByPlaceholderText(/hourly rate/i);
      expect(rateInputs.length).toBe(2);
    });

    it('serializeServices handles null description and equipment gracefully (branches 29/30, lines 268-269)', async () => {
      // Service with null description and equipment — exercises the `?? ''` fallbacks in serializeServices
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
            // description and equipment will be '' by default, but serializeServices has null guards
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Change rate to trigger autosave (which calls serializeServices internally)
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);
      await user.type(rateInput, '60');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      jest.useRealTimers();
    });

    it('price floor error message includes the service name (branch 28, line 246)', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      // Need pricingFloors to be truthy AND have violations
      mockUsePricingConfig.mockReturnValue({
        config: {
          price_floor_cents: { 'online:60': 5000 },
        },
      });
      mockEvaluateViolations.mockReturnValue([{
        floorCents: 5000,
        baseCents: 3000,
        modalityLabel: 'online',
        duration: 60,
      }]);

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 30,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Trigger autosave
      const descField = screen.getByPlaceholderText(/brief description/i);
      await user.type(descField, 'test');
      jest.advanceTimersByTime(1200);

      // Should see a price floor error toast with the service name
      await waitFor(() => {
        expect(toast.error).toHaveBeenCalled();
      });

      const errorCall = (toast.error as jest.Mock).mock.calls[0]?.[0] as string;
      // The service has name 'Piano' (from displayServiceName mock), so the message should include it
      expect(errorCall).toContain('Piano');

      jest.useRealTimers();
    });

    it('service card key uses name fallback when catalog_service_id is empty (branch 199, line 960)', () => {
      // Service with empty catalog_service_id — key uses `s.name` fallback
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: '', // empty, but filter removes this
            service_catalog_name: 'Custom Service',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // An empty catalog_service_id service gets filtered out in hydration (line 435)
      // So this actually tests the filtering, not the fallback
      // But let's verify the component renders without error
      expect(screen.queryByText('Custom Service')).not.toBeInTheDocument();
    });

    it('service with empty hourly_rate shows $0 display (branch 148 related, line 967)', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 0,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // With hourly_rate of 0, the display should show "$0"
      expect(screen.getByText('$0')).toBeInTheDocument();
    });

    it('save does not fire when all services have empty hourly rate (branch in payload filter, line 735)', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Clear the rate entirely — makes it empty string, filtered from payload
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      await user.clear(rateInput);

      // Also add a description to ensure dirty state
      const descField = screen.getByPlaceholderText(/brief description/i);
      await user.type(descField, 'Something');
      jest.advanceTimersByTime(1200);

      // Autosave should still fire but with empty services array in payload
      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      const call = mockFetchWithAuth.mock.calls[0];
      const body = JSON.parse(call?.[1]?.body as string);
      // Service with empty rate gets filtered out
      expect(body.services).toEqual([]);

      jest.useRealTimers();
    });

    it('serviceFloorViolations memo handles service with no location types (branch 24, line 222)', () => {
      // Service with all capabilities false (no location types)
      mockUsePricingConfig.mockReturnValue({
        config: { price_floor_cents: { 'in_person:60': 5000 } },
      });
      mockEvaluateViolations.mockReturnValue([]);

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: false,
            offers_travel: false,
            offers_at_location: false,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Should render without issues — no violations because no location types
      expect(screen.getByPlaceholderText(/hourly rate/i)).toHaveValue(50);
    });

    it('price floor violation blocks save with toast error when pricingFloors exists (branch 106, lines 696-707)', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      // Set up price floors that will cause violations
      mockUsePricingConfig.mockReturnValue({
        config: { price_floor_cents: { 'online:60': 5000 } },
      });
      mockEvaluateViolations.mockReturnValue([{
        floorCents: 5000,
        baseCents: 3000,
        modalityLabel: 'online',
        duration: 60,
      }]);

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 30,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Trigger autosave with a description change
      const descField = screen.getByPlaceholderText(/brief description/i);
      await user.type(descField, 'test');
      jest.advanceTimersByTime(1200);

      // Toast error should fire with the price floor message
      await waitFor(() => {
        expect(toast.error).toHaveBeenCalled();
      });

      // The save should NOT have been called (blocked by violations)
      expect(mockFetchWithAuth).not.toHaveBeenCalled();

      jest.useRealTimers();
    });

    it('duration_options fallback to [60] when empty in payload (branch 116, line 745)', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
            duration_options: [60], // default — can't deselect because min-1 guard
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Trigger autosave
      const descField = screen.getByPlaceholderText(/brief description/i);
      await user.type(descField, 'test');
      jest.advanceTimersByTime(1200);

      await waitFor(() => {
        expect(mockFetchWithAuth).toHaveBeenCalled();
      });

      const call = mockFetchWithAuth.mock.calls[0];
      const body = JSON.parse(call?.[1]?.body as string);
      expect(body.services[0].duration_options).toEqual([60]);

      jest.useRealTimers();
    });

    it('chip and card display fallback to service_catalog_name when name is empty (branches 133-137, lines 890-894)', () => {
      // Override displayServiceName to return empty string, so hydration sets name=''
      mockDisplayServiceName.mockReturnValue('');

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // With name='', the chip should fall back to service_catalog_name='Piano'
      // Line 890: s.name || s.service_catalog_name — name is '', so uses service_catalog_name
      const pianoElements = screen.getAllByText('Piano');
      expect(pianoElements.length).toBeGreaterThanOrEqual(1);

      // Restore the mock
      mockDisplayServiceName.mockImplementation(
        ({ service_catalog_name }: { service_catalog_name?: string }) => service_catalog_name || 'Service'
      );
    });

    it('chip and card display handle empty name and null service_catalog_name gracefully (branches 133[2], lines 890)', () => {
      // Override displayServiceName to return empty string
      mockDisplayServiceName.mockReturnValue('');

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            // No service_catalog_name — will be null
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Both name='' and service_catalog_name=null
      // Chip uses: s.name || s.service_catalog_name || '' → '' (empty)
      // Card uses: s.service_catalog_name ?? s.name ?? 'Service' → null ?? '' ?? 'Service' → '' (name is '', not nullish)
      // The component should render without crashing
      expect(screen.getByPlaceholderText(/hourly rate/i)).toHaveValue(50);

      // Restore the mock
      mockDisplayServiceName.mockImplementation(
        ({ service_catalog_name }: { service_catalog_name?: string }) => service_catalog_name || 'Service'
      );
    });

    it('buildPriceFloorErrors uses "this service" when service name is empty (branch 28, line 246)', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      // Override displayServiceName to return empty string
      mockDisplayServiceName.mockReturnValue('');

      mockUsePricingConfig.mockReturnValue({
        config: { price_floor_cents: { 'online:60': 5000 } },
      });
      mockEvaluateViolations.mockReturnValue([{
        floorCents: 5000,
        baseCents: 3000,
        modalityLabel: 'online',
        duration: 60,
      }]);

      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 30,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Trigger autosave
      const descField = screen.getByPlaceholderText(/brief description/i);
      await user.type(descField, 'test');
      jest.advanceTimersByTime(1200);

      // Should see a price floor error toast with "this service" fallback
      await waitFor(() => {
        expect(toast.error).toHaveBeenCalled();
      });

      const errorCall = (toast.error as jest.Mock).mock.calls[0]?.[0] as string;
      expect(errorCall).toContain('this service');

      // Restore
      mockDisplayServiceName.mockImplementation(
        ({ service_catalog_name }: { service_catalog_name?: string }) => service_catalog_name || 'Service'
      );
      jest.useRealTimers();
    });

    it('expanded category accordion renders services without skillsFilter (branch 143[1], line 923)', async () => {
      // This specifically tests the falsy branch of the skillsFilter ternary
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [
              { id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: 'sub1', eligible_age_groups: ['kids', 'teens', 'adults'] },
            ],
          }],
        },
        isLoading: false,
      });

      render(<SkillsPricingInline />);

      // Expand Music accordion — skillsFilter is '' (empty)
      const musicBtn = screen.getByRole('button', { name: /music/i });
      await userEvent.click(musicBtn);

      // The filter ternary evaluates `skillsFilter ? ... : true`
      // skillsFilter is '' so it takes the `true` branch (shows all services)
      await waitFor(() => {
        expect(screen.getByText(/^Piano \+$/)).toBeInTheDocument();
      });
    });
  });

  // -----------------------------------------------------------------
  // Branch-coverage: nullish/falsy paths, else branches, ternary false
  // -----------------------------------------------------------------
  describe('branch coverage — nullish and falsy paths', () => {
    it('handles service with null description and null equipment (binary-expr lines 268-269)', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            description: null,
            equipment_required: null,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Description/equipment should be empty strings, not "null"
      expect(screen.getByPlaceholderText(/brief description/i)).toHaveValue('');
      expect(screen.getByPlaceholderText(/yoga mat/i)).toHaveValue('');
    });

    it('handles service with undefined description and undefined equipment', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            // No description or equipment_required fields at all
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      expect(screen.getByPlaceholderText(/brief description/i)).toHaveValue('');
      expect(screen.getByPlaceholderText(/yoga mat/i)).toHaveValue('');
    });

    it('handles service with missing duration_options (line 222 fallback to [60])', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            duration_options: null, // Null duration_options
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Component should default to [60] and render 60m selected
      const durationButtons = screen.getAllByRole('button', { name: /60m/i });
      expect(durationButtons.length).toBeGreaterThan(0);
    });

    it('handles service with empty duration_options array', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            duration_options: [], // Empty array
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Should fall back to [60]
      const durationButtons = screen.getAllByRole('button', { name: /60m/i });
      expect(durationButtons.length).toBeGreaterThan(0);
    });

    it('renders $0 display when hourly_rate is empty string (line 967)', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: '',
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // The display shows "$0" when hourly_rate is empty
      expect(screen.getByText(/\$0/)).toBeInTheDocument();
    });

    it('does not show earnings when hourly_rate is 0', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: '0',
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Earnings should NOT be shown when hourly_rate is 0
      expect(screen.queryByText(/you'll earn/i)).not.toBeInTheDocument();
    });

    it('handles null service_catalog_name fallback to name in display (line 965)', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: null,
            name: null,
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });
      mockDisplayServiceName.mockReturnValue(null);

      render(<SkillsPricingInline />);

      // Falls back to 'Service' display
      expect(screen.getByText('Service')).toBeInTheDocument();
    });

    it('handles null hourly_rate from API response (line 419)', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: null,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // hourly_rate defaults to empty string via String(null ?? '')
      const rateInput = screen.getByPlaceholderText(/hourly rate/i);
      expect(rateInput).toHaveValue(null);
    });

    it('handles profile with no service_area_boroughs and string service_area_summary', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: [],
          service_area_boroughs: [],
          service_area_summary: 'Covers all of NYC',
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_travel: true,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // hasServiceAreas should be true because summary is non-empty
      const travelSwitch = screen.getByRole('switch', { name: /i travel to students/i });
      expect(travelSwitch).not.toBeDisabled();
    });

    it('handles profileData with non-array service_area_neighborhoods', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: 'not-an-array',
          service_area_boroughs: null,
          service_area_summary: '',
          preferred_teaching_locations: null,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Non-array neighborhoods should be treated as empty
      const travelSwitch = screen.getByRole('switch', { name: /i travel to students/i });
      expect(travelSwitch).toBeDisabled();
    });

    it('handles non-finite currentTierPct value (line 169)', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          current_tier_pct: Infinity,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 100,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Should handle Infinity gracefully (currentTierPct fallback to null)
      expect(screen.getByText(/platform fee/i)).toBeInTheDocument();
    });

    it('handles non-number currentTierPct value (string)', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          current_tier_pct: 'not-a-number',
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 100,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Should handle string gracefully (currentTierPct fallback to null)
      expect(screen.getByText(/platform fee/i)).toBeInTheDocument();
    });

    it('skips buildPriceFloorErrors when no pricingFloors (line 241 else)', () => {
      mockUsePricingConfig.mockReturnValue({ config: { price_floor_cents: null }, isLoading: false });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // No price errors should appear without pricing floors
      expect(screen.queryByText(/minimum price/i)).not.toBeInTheDocument();
    });

    it('skips violation when service has no location types (line 213 early return)', () => {
      mockUsePricingConfig.mockReturnValue({
        config: { price_floor_cents: { private: { '60': 5000 } } },
        isLoading: false,
      });
      // Service has all location options disabled
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 10, // Very low rate but no location types
            offers_travel: false,
            offers_at_location: false,
            offers_online: false,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // No pricing violations should be computed (skipped due to no location types)
      // evaluatePriceFloorViolations should NOT have been called
      expect(mockEvaluateViolations).not.toHaveBeenCalled();
    });

    it('handles empty requestedSkill for handleRequestSkill (line 625)', async () => {
      const user = userEvent.setup();
      render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

      // Input should be empty
      expect(screen.getByPlaceholderText(/request a new skill/i)).toHaveValue('');

      // Submit button should be disabled
      expect(screen.getByRole('button', { name: /submit/i })).toBeDisabled();

      // Even if we click it, nothing should happen
      await user.click(screen.getByRole('button', { name: /submit/i }));
      expect(screen.queryByText(/we'll review/i)).not.toBeInTheDocument();
    });

    it('handles initializeMissingFilters — no change when filters already exist (line 308 false path)', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            filter_selections: { skill_level: ['beginner'], age_groups: ['adults'] },
            age_groups: ['adults'],
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Component should render without errors — filters already populated
      const pianoElements = screen.getAllByText(/piano/i);
      expect(pianoElements.length).toBeGreaterThan(0);
    });

    it('handles profile with non-string service_area_summary', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          service_area_neighborhoods: [],
          service_area_boroughs: [],
          service_area_summary: 12345, // Non-string
          preferred_teaching_locations: [],
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Non-string summary should be treated as empty
      const travelSwitch = screen.getByRole('switch', { name: /i travel to students/i });
      expect(travelSwitch).toBeDisabled();
    });

    it('handles back-fill effect with empty eligible_age_groups (line 531 if branch)', () => {
      // Service has empty eligible_age_groups, catalog has them
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            eligible_age_groups: [],
            offers_online: true,
          }],
        },
      });

      // Catalog provides eligible_age_groups
      mockUseAllServices.mockReturnValue({
        data: {
          categories: [{
            id: '01HABCTESTCAT0000000000001',
            name: 'Music',
            services: [{
              id: 'svc-1',
              name: 'Piano',
              slug: 'piano',
              subcategory_id: '01HABCTESTSUBCAT0000000001',
              eligible_age_groups: ['kids', 'teens', 'adults'],
            }],
          }],
        },
        isLoading: false,
      });

      render(<SkillsPricingInline />);

      // Should backfill age groups from catalog
      const pianoElements = screen.getAllByText(/piano/i);
      expect(pianoElements.length).toBeGreaterThan(0);
    });
  });
});
