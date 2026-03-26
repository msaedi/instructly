import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Step3SkillsPricing from '@/app/(auth)/instructor/onboarding/skill-selection/page';
import { useOnboardingStepStatus } from '@/features/instructor-onboarding/useOnboardingStepStatus';
import { fetchWithAuth } from '@/lib/api';
import { toast } from 'sonner';
import { useServiceCategories, useCatalogBrowse } from '@/hooks/queries/useServices';
import { useCategoriesWithSubcategories, useSubcategoryFilters } from '@/hooks/queries/useTaxonomy';
import { useUserAddresses } from '@/hooks/queries/useUserAddresses';

const searchParamsProxy = {
  get: (_key: string) => null,
  toString: () => '',
};

jest.mock('next/navigation', () => ({
  useSearchParams: () => searchParamsProxy,
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 'user-1', roles: ['instructor'] },
    isAuthenticated: true,
  }),
}));

jest.mock('@/lib/api', () => ({
  API_ENDPOINTS: {
    INSTRUCTOR_PROFILE: '/api/v1/instructors/me',
    NYC_ZIP_CHECK: '/api/v1/addresses/nyc-zip-check',
  },
  fetchWithAuth: jest.fn(),
}));

jest.mock('sonner', () => ({
  toast: {
    error: jest.fn(),
    success: jest.fn(),
  },
}));

jest.mock('@/features/instructor-onboarding/OnboardingProgressHeader', () => ({
  OnboardingProgressHeader: () => <div data-testid="onboarding-progress-header" />,
}));

jest.mock('@/features/instructor-onboarding/useOnboardingStepStatus', () => ({
  useOnboardingStepStatus: jest.fn(),
}));

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingConfig: () => ({ config: null }),
}));

jest.mock('@/hooks/usePlatformConfig', () => ({
  usePlatformFees: () => ({
    fees: {
      tier_1: 0.3,
      founding_instructor: 0.15,
    },
  }),
}));

jest.mock('@/hooks/queries/useServices', () => ({
  useServiceCategories: jest.fn(),
  useCatalogBrowse: jest.fn(),
}));

jest.mock('@/hooks/queries/useTaxonomy', () => ({
  useCategoriesWithSubcategories: jest.fn(),
  useSubcategoryFilters: jest.fn(),
}));

jest.mock('@/hooks/queries/useUserAddresses', () => ({
  useUserAddresses: jest.fn(),
}));

jest.mock('@/lib/apiBase', () => ({
  withApiBase: (url: string) => url,
}));

jest.mock('@/lib/auth/sessionRefresh', () => ({
  fetchWithSessionRefresh: jest.fn(async () => ({
    ok: true,
    json: async () => ({ is_nyc: true }),
  })),
}));

jest.mock('@/components/ui/ToggleSwitch', () => ({
  ToggleSwitch: ({
    checked,
    onChange,
    ariaLabel,
    disabled,
  }: {
    checked: boolean;
    onChange: () => void;
    ariaLabel: string;
    disabled?: boolean;
  }) => (
    <button
      type="button"
      aria-label={ariaLabel}
      aria-pressed={checked}
      disabled={disabled}
      onClick={onChange}
    />
  ),
}));

const useOnboardingStepStatusMock = useOnboardingStepStatus as jest.Mock;
const useServiceCategoriesMock = useServiceCategories as jest.Mock;
const useCatalogBrowseMock = useCatalogBrowse as jest.Mock;
const useCategoriesWithSubcategoriesMock = useCategoriesWithSubcategories as jest.Mock;
const useSubcategoryFiltersMock = useSubcategoryFilters as jest.Mock;
const useUserAddressesMock = useUserAddresses as jest.Mock;
const fetchWithAuthMock = fetchWithAuth as jest.MockedFunction<typeof fetchWithAuth>;
const toastErrorMock = toast.error as jest.MockedFunction<typeof toast.error>;

const CATEGORY_DATA = [
  {
    id: 'cat-1',
    name: 'Music',
    display_order: 1,
    description: null,
    icon_name: null,
    subtitle: null,
  },
];

const CATALOG_BROWSE_RESPONSE = {
  categories: [
    {
      id: 'cat-1',
      name: 'Music',
      services: [
        {
          id: 'svc-1',
          name: 'Piano',
          subcategory_id: 'sub-1',
          eligible_age_groups: ['kids', 'teens', 'adults'],
          description: null,
          display_order: 1,
        },
      ],
    },
  ],
};

const CATEGORIES_WITH_SUBCATEGORIES = [
  {
    id: 'cat-1',
    name: 'Music',
    display_order: 1,
    description: null,
    icon_name: null,
    subtitle: null,
    subcategories: [
      {
        id: 'sub-1',
        name: 'Piano',
        service_count: 1,
      },
    ],
  },
];

const SUBCATEGORY_FILTERS = [
  {
    filter_key: 'skill_level',
    filter_display_name: 'Skill Level',
    filter_type: 'multi_select',
    options: [
      { id: 'sl-1', value: 'beginner', display_name: 'Beginner', display_order: 0 },
      {
        id: 'sl-2',
        value: 'intermediate',
        display_name: 'Intermediate',
        display_order: 1,
      },
      { id: 'sl-3', value: 'advanced', display_name: 'Advanced', display_order: 2 },
    ],
  },
  {
    filter_key: 'goal',
    filter_display_name: 'Goal',
    filter_type: 'multi_select',
    options: [
      { id: 'goal-1', value: 'hobby', display_name: 'Hobby', display_order: 0 },
      {
        id: 'goal-2',
        value: 'performance',
        display_name: 'Performance',
        display_order: 1,
      },
    ],
  },
];

const renderWithClient = (ui: ReactNode) => {
  const queryClient = new QueryClient();
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
};

describe('Skill selection page refine header', () => {
  beforeEach(() => {
    useOnboardingStepStatusMock.mockReturnValue({
      stepStatus: {
        'account-setup': 'done',
        'skill-selection': 'pending',
        'verify-identity': 'pending',
        'payment-setup': 'pending',
      },
      rawData: {
        profile: {
          is_live: false,
          is_founding_instructor: false,
          services: [],
          service_area_neighborhoods: [],
          service_area_boroughs: [],
          service_area_summary: '',
          preferred_teaching_locations: [],
          current_tier_pct: null,
        },
      },
    });

    useServiceCategoriesMock.mockReturnValue({
      data: CATEGORY_DATA,
      isLoading: false,
      error: null,
    });

    useCatalogBrowseMock.mockReturnValue({
      data: CATALOG_BROWSE_RESPONSE,
      isLoading: false,
      error: null,
    });

    useCategoriesWithSubcategoriesMock.mockReturnValue({
      data: CATEGORIES_WITH_SUBCATEGORIES,
      isLoading: false,
      error: null,
    });

    useSubcategoryFiltersMock.mockImplementation((subcategoryId: string) => ({
      data: subcategoryId === 'sub-1' ? SUBCATEGORY_FILTERS : [],
      isLoading: false,
      error: null,
    }));

    useUserAddressesMock.mockReturnValue({
      data: { items: [] },
      isLoading: false,
    });

    fetchWithAuthMock.mockImplementation(async (url: string, options?: RequestInit) => {
      if (url === '/api/v1/addresses/service-areas/me' && options?.method === undefined) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ items: [] }),
        } as Response;
      }

      return {
        ok: true,
        status: 200,
        json: async () => ({}),
      } as Response;
    });
  });

  it('renders skeleton loading state while catalog browse data is loading', () => {
    useCatalogBrowseMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    });

    const { container } = renderWithClient(<Step3SkillsPricing />);

    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument();
  });

  it('renders refine label as selectable text and toggles via chevron button only', async () => {
    renderWithClient(<Step3SkillsPricing />);

    fireEvent.click(screen.getByRole('button', { name: /music/i }));
    fireEvent.click(await screen.findByRole('button', { name: /toggle subcategory piano/i }));
    fireEvent.click(await screen.findByRole('button', { name: /add service piano/i }));

    const refineLabel = await screen.findByText('Refine what you teach (optional)');
    expect(refineLabel).toBeInTheDocument();
    expect(refineLabel).toHaveClass('text-gray-900');
    expect(refineLabel).toHaveClass('select-text');

    expect(
      screen.queryByRole('button', { name: /refine what you teach \(optional\)/i })
    ).not.toBeInTheDocument();

    const toggleButton = screen.getByRole('button', {
      name: /toggle refine filters for piano/i,
    });
    expect(toggleButton).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Goal')).not.toBeInTheDocument();

    fireEvent.click(toggleButton);

    await waitFor(() => {
      expect(toggleButton).toHaveAttribute('aria-expanded', 'true');
    });
    expect(screen.getByText('Goal')).toBeInTheDocument();

    expect(screen.getByText('Age groups')).toBeInTheDocument();
    expect(screen.getByText('Skill level')).toBeInTheDocument();
  });

  it('supports expanding and collapsing subcategories inside an expanded category', async () => {
    renderWithClient(<Step3SkillsPricing />);

    fireEvent.click(screen.getByRole('button', { name: /music/i }));

    const subcategoryToggle = screen.getByRole('button', {
      name: /toggle subcategory piano/i,
    });

    expect(subcategoryToggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('button', { name: /add service piano/i })).not.toBeInTheDocument();

    fireEvent.click(subcategoryToggle);
    expect(subcategoryToggle).toHaveAttribute('aria-expanded', 'true');
    expect(await screen.findByRole('button', { name: /add service piano/i })).toBeInTheDocument();

    fireEvent.click(subcategoryToggle);
    expect(subcategoryToggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('button', { name: /add service piano/i })).not.toBeInTheDocument();
  });

  it('shows the max hourly rate error at $1,001', async () => {
    renderWithClient(<Step3SkillsPricing />);

    fireEvent.click(screen.getByRole('button', { name: /music/i }));
    fireEvent.click(await screen.findByRole('button', { name: /toggle subcategory piano/i }));
    fireEvent.click(await screen.findByRole('button', { name: /add service piano/i }));

    const rateInput = screen
      .getAllByRole('spinbutton')
      .find((element) => !(element as HTMLInputElement).disabled);

    expect(rateInput).toBeTruthy();
    fireEvent.change(rateInput as HTMLElement, { target: { value: '1001' } });

    expect(await screen.findByText('Maximum hourly rate is $1,000')).toBeInTheDocument();
  });

  it('does not redirect away when the backend rejects the save', async () => {
    const startingHref = window.location.href;
    fetchWithAuthMock.mockImplementation(async (url: string, options?: RequestInit) => {
      if (url === '/api/v1/addresses/service-areas/me' && options?.method === undefined) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ items: [] }),
        } as Response;
      }

      if (url === '/api/v1/instructors/me') {
        return {
          ok: false,
          status: 422,
          json: async () => ({ detail: 'Validation failed' }),
        } as Response;
      }

      return {
        ok: true,
        status: 200,
        json: async () => ({}),
      } as Response;
    });

    renderWithClient(<Step3SkillsPricing />);

    fireEvent.click(screen.getByRole('button', { name: /music/i }));
    fireEvent.click(await screen.findByRole('button', { name: /toggle subcategory piano/i }));
    fireEvent.click(await screen.findByRole('button', { name: /add service piano/i }));

    const rateInput = screen
      .getAllByRole('spinbutton')
      .find((element) => !(element as HTMLInputElement).disabled);

    expect(rateInput).toBeTruthy();
    fireEvent.change(rateInput as HTMLElement, { target: { value: '1000' } });
    fireEvent.click(screen.getByRole('button', { name: /save & continue/i }));

    expect(await screen.findByText('Validation failed')).toBeInTheDocument();
    expect(toastErrorMock).toHaveBeenCalledWith('Validation failed');
    expect(window.location.href).toBe(startingHref);
  });
});
