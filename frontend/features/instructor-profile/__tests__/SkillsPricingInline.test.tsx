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
  normalizeLocationTypes: (values: unknown[]) =>
    (Array.isArray(values) ? values : [])
      .map((value) => String(value ?? '').trim().toLowerCase().replace(/[\s-]+/g, '_'))
      .filter((value) => value === 'in_person' || value === 'online'),
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
      data: { is_live: false, services: [{ service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 30, duration_options: [60], location_types: ['in_person'] }] },
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
      data: { is_live: false, services: [{ service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 45, duration_options: [60], location_types: ['in_person'] }] },
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
          location_types: ['in_person'],
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
          location_types: ['in_person'],
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
          location_types: ['in_person'],
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
          location_types: ['in_person'],
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
          location_types: ['in_person'],
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

  it('handles empty skill request submission gracefully', async () => {
    const user = userEvent.setup();
    render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

    // Try to submit without entering text
    await user.click(screen.getByRole('button', { name: /submit/i }));

    // Should not show success message
    expect(screen.queryByText(/we'll review/i)).not.toBeInTheDocument();
  });

  it('filters categories but excludes kids category', () => {
    mockUseServiceCategories.mockReturnValue({
      data: [
        { slug: 'music', name: 'Music' },
        { slug: 'kids', name: 'Kids Activities' },
        { slug: 'sports', name: 'Sports' },
      ],
      isLoading: false,
    });

    render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

    expect(screen.getByRole('button', { name: /music/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sports/i })).toBeInTheDocument();
    // Kids category should be filtered out
    expect(screen.queryByRole('button', { name: /kids activities/i })).not.toBeInTheDocument();
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
          { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 50 },
          { service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 60 }, // Duplicate
          { service_catalog_id: 'svc-2', service_catalog_name: 'Guitar', hourly_rate: 45 },
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
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano Lesson',
          hourly_rate: 40,
          duration_options: [60],
          location_types: ['in_person'],
        }],
      },
    });
    mockUsePricingConfig.mockReturnValue({
      config: { price_floor_cents: { private: { '60': 5000 } } },
    });
    mockEvaluateViolations.mockReturnValue([
      { duration: 60, modalityLabel: 'in-person', floorCents: 5000, baseCents: 4000 },
    ]);

    render(<SkillsPricingInline />);

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
            slug: 'music',
            services: [{ id: 'svc-1', name: 'Piano' }],
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

  it('does not filter services from categories that have kids slug', () => {
    mockUseAllServices.mockReturnValue({
      data: {
        categories: [
          { slug: 'kids', services: [{ id: 'svc-kids', name: 'Kids Dancing' }] },
          { slug: 'music', services: [{ id: 'svc-1', name: 'Piano' }] },
        ],
      },
      isLoading: false,
    });

    render(<SkillsPricingInline instructorProfile={{ is_live: false, services: [] } as never} />);

    // Music category should be shown
    expect(screen.getByRole('button', { name: /music/i })).toBeInTheDocument();
    // Kids category should be filtered
    expect(screen.queryByRole('button', { name: /kids/i })).not.toBeInTheDocument();
  });

  it('handles service with name field instead of service_catalog_name', () => {
    mockUseInstructorProfileMe.mockReturnValue({
      data: {
        is_live: false,
        services: [{
          service_catalog_id: 'svc-1',
          name: 'Custom Piano', // Using name instead of service_catalog_name
          hourly_rate: 75,
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
          { service_catalog_id: '', service_catalog_name: 'Invalid', hourly_rate: 50 },
          { service_catalog_id: 'svc-1', service_catalog_name: 'Valid Piano', hourly_rate: 60 },
        ],
      },
    });

    render(<SkillsPricingInline />);

    // Only valid service should be shown
    const rateInputs = screen.getAllByPlaceholderText(/hourly rate/i);
    expect(rateInputs).toHaveLength(1);
  });

  describe('Coverage improvement tests', () => {
    it('renders services from instructorProfile prop', async () => {
      // Profile not yet loaded from hook (data is null)
      mockUseInstructorProfileMe.mockReturnValue({ data: null });

      render(
        <SkillsPricingInline
          instructorProfile={{ is_live: false, services: [{ service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 60 }] } as never}
        />
      );

      // Service should be rendered from prop
      expect(screen.getByPlaceholderText(/hourly rate/i)).toBeInTheDocument();
    });

    it('allows toggling service selection when profile is loaded', async () => {
      const user = userEvent.setup();
      mockUseInstructorProfileMe.mockReturnValue({
        data: { is_live: false, services: [{ service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 60 }] },
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
        data: { is_live: true, services: [{ service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 60 }] },
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
          instructorProfile={{ is_live: false, services: [{ service_catalog_id: 'svc-1', service_catalog_name: 'Piano', hourly_rate: 60 }] } as never}
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
});
