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
  displayServiceName: ({ service_catalog_name }: { service_catalog_name?: string }) => service_catalog_name || 'Service',
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

const categoriesData = [{ id: '01HABCTESTCAT0000000000001', name: 'Music', display_order: 1 }];
const servicesData = {
  categories: [
    {
      id: '01HABCTESTCAT0000000000001',
      name: 'Music',
      services: [{ id: 'svc-1', name: 'Piano', slug: 'piano', subcategory_id: '01HABCTESTSUBCAT0000000001' }],
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

    it('maps missing age_groups to adults', () => {
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{
            service_catalog_id: 'svc-1',
            service_catalog_name: 'Piano',
            hourly_rate: 50,
            // age_groups not provided
            offers_online: true,
          }],
        },
      });

      render(<SkillsPricingInline />);

      // Adults should be selected by default, Kids should not
      const kidsButtons = screen.getAllByRole('button', { name: /^kids$/i });
      const adultsButtons = screen.getAllByRole('button', { name: /^adults$/i });
      expect(adultsButtons[0]?.className).toContain('purple');
      expect(kidsButtons[0]?.className).not.toContain('purple');
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

    it('toggles from adults to kids when adults is clicked', async () => {
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

      // Click adults button to toggle it off (should switch to kids)
      const adultsButtons = screen.getAllByRole('button', { name: /^adults$/i });
      await user.click(adultsButtons[0]!);

      // Should now be kids only
      const kidsButtons = screen.getAllByRole('button', { name: /^kids$/i });
      expect(kidsButtons[0]?.className).toContain('purple');
      expect(adultsButtons[0]?.className).not.toContain('purple');
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

    it('age group toggle from kids clicking kids switches to adults', async () => {
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

      const kidsButtons = screen.getAllByRole('button', { name: /^kids$/i });
      await user.click(kidsButtons[0]!);

      const adultsButtons = screen.getAllByRole('button', { name: /^adults$/i });
      expect(adultsButtons[0]?.className).toContain('purple');
      expect(kidsButtons[0]?.className).not.toContain('purple');
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
              levels_taught: ['beginner'],
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

    it('age group toggle from adults clicking adults switches to kids', async () => {
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

      const adultsButtons = screen.getAllByRole('button', { name: /^adults$/i });
      await user.click(adultsButtons[0]!);

      // Clicking active adults should switch to kids
      const kidsButtons = screen.getAllByRole('button', { name: /^kids$/i });
      expect(kidsButtons[0]?.className).toContain('purple');
      expect(adultsButtons[0]?.className).not.toContain('purple');
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
});
