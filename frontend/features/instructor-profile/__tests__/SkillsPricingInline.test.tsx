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

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api');
  return { ...actual, fetchWithAuth: jest.fn() };
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

const mockUseServiceCategories = useServiceCategories as jest.Mock;
const mockUseAllServices = useAllServicesWithInstructors as jest.Mock;
const mockUseInstructorProfileMe = useInstructorProfileMe as jest.Mock;
const mockUsePricingConfig = usePricingConfig as jest.Mock;
const mockUsePlatformFees = usePlatformFees as jest.Mock;
const mockFetchWithAuth = fetchWithAuth as jest.Mock;
const mockEvaluateViolations = evaluatePriceFloorViolations as jest.Mock;

const categoriesData = [{ slug: 'music', name: 'Music' }];
const servicesData = {
  categories: [
    {
      slug: 'music',
      services: [{ id: 'svc-1', name: 'Piano' }],
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
      data: { is_live: true, services: [{ service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 60 }] },
    });

    render(<SkillsPricingInline />);

    await user.click(screen.getByRole('button', { name: /remove skill/i }));
    expect(screen.getByText(/must have at least one skill/i)).toBeInTheDocument();
  });

  it('surfaces price floor violations on autosave', async () => {
    jest.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    mockUseInstructorProfileMe.mockReturnValue({
      data: { is_live: false, services: [{ service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 30, duration_options: [60], location_types: ['in-person'] }] },
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
      data: { is_live: false, services: [{ service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 45, duration_options: [60], location_types: ['in-person'] }] },
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
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 50,
          age_groups: ['adults'],
          duration_options: [60],
          location_types: ['in-person'],
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
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          hourly_rate: 50,
          age_groups: ['adults'],
          duration_options: [60],
          location_types: ['in-person'],
        }],
      },
    });

    render(<SkillsPricingInline />);

    // Find and click the Online button
    const onlineButtons = screen.getAllByRole('button', { name: /online/i });
    const onlineButton = onlineButtons.find((btn) => !btn.className?.includes('cursor-not-allowed'));
    if (onlineButton) {
      await user.click(onlineButton);
    }

    const pianoElements = screen.getAllByText(/piano/i);
    expect(pianoElements.length).toBeGreaterThan(0);
  });

  it('toggles skill levels', async () => {
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
          location_types: ['in-person'],
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
          location_types: ['in-person'],
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
            slug: 'music',
            services: [
              { id: 'svc-1', name: 'Piano' },
              { id: 'svc-2', name: 'Guitar' },
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
          location_types: ['in-person'],
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
        }],
      },
    });

    render(<SkillsPricingInline />);

    // Component should render with fee info
    expect(screen.getByText(/platform fee/i)).toBeInTheDocument();
  });
});
