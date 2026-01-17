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
});
