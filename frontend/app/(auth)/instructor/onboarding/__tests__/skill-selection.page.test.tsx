import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Step3SkillsPricing from '@/app/(auth)/instructor/onboarding/skill-selection/page';
import { useOnboardingStepStatus } from '@/features/instructor-onboarding/useOnboardingStepStatus';
import { fetchWithAuth } from '@/lib/api';
import { toast } from 'sonner';
import { useServiceCategories, useCatalogBrowse } from '@/hooks/queries/useServices';
import { useCategoriesWithSubcategories, useSubcategoryFilters } from '@/hooks/queries/useTaxonomy';
import { useInstructorServiceAreas } from '@/hooks/queries/useInstructorServiceAreas';
import { useUserAddresses } from '@/hooks/queries/useUserAddresses';
import { TEACHING_ADDRESS_REQUIRED_MESSAGE } from '@/lib/teachingLocations';

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

jest.mock('@/hooks/queries/useInstructorServiceAreas', () => ({
  useInstructorServiceAreas: jest.fn(),
}));

jest.mock('@/components/neighborhoods/NeighborhoodSelector', () => ({
  NeighborhoodSelector: ({
    value,
    onSelectionChange,
  }: {
    value?: string[];
    onSelectionChange?: (
      keys: string[],
      items: Array<{ display_key: string; display_name: string }>
    ) => void;
  }) => (
    <div data-testid="service-areas-card">
      <div data-testid="service-areas-count">{value?.length ?? 0}</div>
      <div data-testid="service-areas-value">{(value ?? []).join(',')}</div>
      <button
        type="button"
        onClick={() =>
          onSelectionChange?.(['n1'], [{ display_key: 'n1', display_name: 'Upper East Side' }])
        }
      >
        Select Neighborhood
      </button>
      <button type="button" onClick={() => onSelectionChange?.([], [])}>
        Clear Neighborhoods
      </button>
    </div>
  ),
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

jest.mock('@/components/forms/PlacesAutocompleteInput', () => ({
  PlacesAutocompleteInput: ({
    'data-testid': dataTestId,
    value,
    onValueChange,
    onSelectSuggestion,
    placeholder,
    disabled,
  }: {
    'data-testid'?: string;
    value?: string;
    onValueChange?: (value: string) => void;
    onSelectSuggestion?: (suggestion: {
      place_id: string;
      description: string;
      text: string;
      provider: string;
      types: string[];
    }) => void;
    placeholder?: string;
    disabled?: boolean;
  }) => (
    <div>
      <input
        data-testid={dataTestId ?? 'places-autocomplete'}
        value={value ?? ''}
        onChange={(event) => onValueChange?.(event.target.value)}
        placeholder={placeholder}
        disabled={disabled}
      />
      <button
        type="button"
        data-testid={`${dataTestId ?? 'places-autocomplete'}-select-suggestion`}
        disabled={disabled || !onSelectSuggestion}
        onClick={() => {
          const suggestionText =
            typeof value === 'string' && value.trim().length > 0
              ? value.trim()
              : '123 Studio Lane, New York, NY';
          const suggestionId =
            typeof value === 'string' && value.trim().length > 0
              ? value.trim().toLowerCase().replace(/\s+/g, '_')
              : 'place_1';
          onSelectSuggestion?.({
            place_id: suggestionId,
            description: suggestionText,
            text: suggestionText,
            provider: 'google',
            types: ['street_address'],
          });
        }}
      >
        Select suggestion
      </button>
    </div>
  ),
}));

const useOnboardingStepStatusMock = useOnboardingStepStatus as jest.Mock;
const useServiceCategoriesMock = useServiceCategories as jest.Mock;
const useCatalogBrowseMock = useCatalogBrowse as jest.Mock;
const useCategoriesWithSubcategoriesMock = useCategoriesWithSubcategories as jest.Mock;
const useSubcategoryFiltersMock = useSubcategoryFilters as jest.Mock;
const useUserAddressesMock = useUserAddresses as jest.Mock;
const useInstructorServiceAreasMock = useInstructorServiceAreas as jest.Mock;
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

function createDeferredResponse() {
  let resolve!: (response: Response) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<Response>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

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
      isFetched: true,
    });

    useInstructorServiceAreasMock.mockReturnValue({
      data: { items: [] },
      isLoading: false,
      isFetched: true,
      isError: false,
    });

    fetchWithAuthMock.mockImplementation(async (_url: string, _options?: RequestInit) => {
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
    fetchWithAuthMock.mockImplementation(async (url: string, _options?: RequestInit) => {
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

    expect(await screen.findByRole('button', { name: /music/i })).toBeInTheDocument();

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

  it('removes the optional label and shows a teaching-address validation message for instructor-location services', async () => {
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
          services: [
            {
              id: 'svc-1',
              service_catalog_id: 'svc-1',
              format_prices: [{ format: 'instructor_location', hourly_rate: 95 }],
              duration_options: [60],
              filter_selections: {},
              age_groups: ['adults'],
            },
          ],
          service_area_neighborhoods: [],
          service_area_boroughs: [],
          service_area_summary: '',
          preferred_teaching_locations: [],
          current_tier_pct: null,
        },
      },
    });
    fetchWithAuthMock.mockImplementation(async (url: string, _options?: RequestInit) => {
      if (url.startsWith('/api/v1/addresses/places/details?')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            formatted_address: '123 Studio Lane, New York, NY',
            latitude: 40.775,
            longitude: -73.955,
            provider_id: 'google:place_1',
          }),
        } as Response;
      }

      if (url === '/api/v1/addresses/validate-service-area') {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            in_service_area: true,
            neighborhood_display_name: 'Upper East Side',
          }),
        } as Response;
      }

      return {
        ok: true,
        status: 200,
        json: async () => ({}),
      } as Response;
    });

    renderWithClient(<Step3SkillsPricing />);

    await waitFor(() => {
      expect(screen.getAllByTestId('preferred-places-card').length).toBeGreaterThan(0);
    });

    expect(
      screen.getByText((_, element) => element?.textContent?.trim() === 'Where You Teach')
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        (_, element) => element?.textContent?.trim() === 'Where You Teach (Optional)'
      )
    ).not.toBeInTheDocument();
    expect(screen.getByText(TEACHING_ADDRESS_REQUIRED_MESSAGE)).toBeInTheDocument();

    const addButton = screen.getByRole('button', { name: /add address/i });
    expect(addButton).toBeDisabled();
    fireEvent.click(screen.getByTestId('ptl-input-select-suggestion'));
    await waitFor(() => {
      expect(addButton).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole('button', { name: /add address/i }));

    await waitFor(() => {
      expect(screen.queryByText(TEACHING_ADDRESS_REQUIRED_MESSAGE)).not.toBeInTheDocument();
    });
  });

  it('does not issue raw address or service-area GET requests on mount', async () => {
    renderWithClient(<Step3SkillsPricing />);

    await waitFor(() => {
      expect(useInstructorServiceAreasMock).toHaveBeenCalled();
    });

    expect(fetchWithAuthMock).not.toHaveBeenCalledWith('/api/v1/addresses/me');
    expect(fetchWithAuthMock).not.toHaveBeenCalledWith('/api/v1/addresses/service-areas/me');
  });

  it('prefers saved service areas over onboarding address lookup', async () => {
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
          services: [
            {
              id: 'svc-1',
              service_catalog_id: 'svc-1',
              format_prices: [{ format: 'student_location', hourly_rate: 95 }],
              duration_options: [60],
              filter_selections: {},
              age_groups: ['adults'],
            },
          ],
          service_area_neighborhoods: [],
          service_area_boroughs: [],
          service_area_summary: '',
          preferred_teaching_locations: [],
          current_tier_pct: null,
        },
      },
    });
    useInstructorServiceAreasMock.mockReturnValue({
      data: {
        items: [
          {
            display_key: 'nyc-manhattan-upper-east-side',
            display_name: 'Upper East Side',
            borough: 'Manhattan',
          },
        ],
      },
      isLoading: false,
      isFetched: true,
      isError: false,
    });
    useUserAddressesMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'addr-1',
            street_line1: '123 Main St',
            locality: 'New York',
            administrative_area: 'NY',
            postal_code: '10021',
            country_code: 'US',
            latitude: 40.775,
            longitude: -73.955,
            is_default: true,
            is_active: true,
          },
        ],
      },
      isLoading: false,
      isFetched: true,
    });

    renderWithClient(<Step3SkillsPricing />);

    await waitFor(() => {
      expect(screen.getByTestId('service-areas-count')).toHaveTextContent('1');
    });

    const serviceAreasCard = screen.getByTestId('service-areas-card');
    expect(serviceAreasCard.parentElement).toHaveClass(
      'insta-surface-card',
      'mt-0',
      'sm:mt-8',
      'p-4',
      'sm:p-6'
    );

    expect(fetchWithAuthMock).not.toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/addresses/neighborhoods/lookup'),
    );
  });

  it('prefills one neighborhood from the default address lookup when saved service areas are empty', async () => {
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
          services: [
            {
              id: 'svc-1',
              service_catalog_id: 'svc-1',
              format_prices: [{ format: 'student_location', hourly_rate: 95 }],
              duration_options: [60],
              filter_selections: {},
              age_groups: ['adults'],
            },
          ],
          service_area_neighborhoods: [],
          service_area_boroughs: [],
          service_area_summary: '',
          preferred_teaching_locations: [],
          current_tier_pct: null,
        },
      },
    });
    useUserAddressesMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'addr-1',
            street_line1: '123 Main St',
            locality: 'New York',
            administrative_area: 'NY',
            postal_code: '10021',
            country_code: 'US',
            latitude: 40.775,
            longitude: -73.955,
            is_default: true,
            is_active: true,
          },
        ],
      },
      isLoading: false,
      isFetched: true,
    });
    fetchWithAuthMock.mockImplementation(async (url: string, _options?: RequestInit) => {
      if (url.startsWith('/api/v1/addresses/neighborhoods/lookup?')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            display_key: 'nyc-manhattan-upper-east-side',
            display_name: 'Upper East Side',
            borough: 'Manhattan',
          }),
        } as Response;
      }

      return {
        ok: true,
        status: 200,
        json: async () => ({}),
      } as Response;
    });

    renderWithClient(<Step3SkillsPricing />);

    await waitFor(() => {
      expect(screen.getByTestId('service-areas-count')).toHaveTextContent('1');
    });
    expect(fetchWithAuthMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/addresses/neighborhoods/lookup?'),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it('leaves onboarding service areas empty when the default address lookup returns null', async () => {
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
          services: [
            {
              id: 'svc-1',
              service_catalog_id: 'svc-1',
              format_prices: [{ format: 'student_location', hourly_rate: 95 }],
              duration_options: [60],
              filter_selections: {},
              age_groups: ['adults'],
            },
          ],
          service_area_neighborhoods: [],
          service_area_boroughs: [],
          service_area_summary: '',
          preferred_teaching_locations: [],
          current_tier_pct: null,
        },
      },
    });
    useUserAddressesMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'addr-1',
            street_line1: '123 Main St',
            locality: 'New York',
            administrative_area: 'NY',
            postal_code: '10021',
            country_code: 'US',
            latitude: 40.775,
            longitude: -73.955,
            is_default: true,
            is_active: true,
          },
        ],
      },
      isLoading: false,
      isFetched: true,
    });
    fetchWithAuthMock.mockImplementation(async (url: string, _options?: RequestInit) => {
      if (url.startsWith('/api/v1/addresses/neighborhoods/lookup?')) {
        return {
          ok: true,
          status: 200,
          json: async () => null,
        } as Response;
      }

      return {
        ok: true,
        status: 200,
        json: async () => ({}),
      } as Response;
    });

    renderWithClient(<Step3SkillsPricing />);

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/addresses/neighborhoods/lookup?'),
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      );
    });
    expect(screen.getByTestId('service-areas-count')).toHaveTextContent('0');
  });

  it('does not let the lookup overwrite a manual service-area selection and aborts the request', async () => {
    const deferredLookup = createDeferredResponse();

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
          services: [
            {
              id: 'svc-1',
              service_catalog_id: 'svc-1',
              format_prices: [{ format: 'student_location', hourly_rate: 95 }],
              duration_options: [60],
              filter_selections: {},
              age_groups: ['adults'],
            },
          ],
          service_area_neighborhoods: [],
          service_area_boroughs: [],
          service_area_summary: '',
          preferred_teaching_locations: [],
          current_tier_pct: null,
        },
      },
    });
    useUserAddressesMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'addr-1',
            street_line1: '123 Main St',
            locality: 'New York',
            administrative_area: 'NY',
            postal_code: '10021',
            country_code: 'US',
            latitude: 40.775,
            longitude: -73.955,
            is_default: true,
            is_active: true,
          },
        ],
      },
      isLoading: false,
      isFetched: true,
    });
    fetchWithAuthMock.mockImplementation(async (url: string, _options?: RequestInit) => {
      if (url.startsWith('/api/v1/addresses/neighborhoods/lookup?')) {
        return deferredLookup.promise;
      }

      return {
        ok: true,
        status: 200,
        json: async () => ({}),
      } as Response;
    });

    renderWithClient(<Step3SkillsPricing />);

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/addresses/neighborhoods/lookup?'),
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      );
    });

    fireEvent.click(screen.getByRole('button', { name: 'Select Neighborhood' }));

    const [, lookupOptions] = fetchWithAuthMock.mock.calls.find(([url]) =>
      url.startsWith('/api/v1/addresses/neighborhoods/lookup?')
    ) as [string, RequestInit];
    expect(lookupOptions.signal).toBeInstanceOf(AbortSignal);
    expect(lookupOptions.signal?.aborted).toBe(true);
    expect(screen.getByTestId('service-areas-value')).toHaveTextContent('n1');

    deferredLookup.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        display_key: 'nyc-manhattan-upper-east-side',
        display_name: 'Upper East Side',
        borough: 'Manhattan',
      }),
    } as Response);

    await waitFor(() => {
      expect(screen.getByTestId('service-areas-value')).toHaveTextContent('n1');
    });
  });

  it('blocks save, shows the inline error, and scrolls to the first empty-rate offender', async () => {
    useInstructorServiceAreasMock.mockReturnValue({
      data: {
        items: [
          {
            display_key: 'n1',
            display_name: 'Upper East Side',
            borough: 'Manhattan',
          },
        ],
      },
      isLoading: false,
      isFetched: true,
      isError: false,
    });

    const rafSpy = jest
      .spyOn(window, 'requestAnimationFrame')
      .mockImplementation((callback: FrameRequestCallback) => {
        callback(0);
        return 1;
      });

    renderWithClient(<Step3SkillsPricing />);

    expect(await screen.findByRole('button', { name: /music/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /music/i }));
    fireEvent.click(await screen.findByRole('button', { name: /toggle subcategory piano/i }));
    fireEvent.click(await screen.findByRole('button', { name: /add service piano/i }));

    const studentCard = screen.getByTestId('format-card-student_location');
    const studentInput = within(studentCard).getByRole('spinbutton');
    const studentScrollMock = jest.fn();
    const studentFocusMock = jest.fn();
    Object.defineProperty(studentCard, 'scrollIntoView', {
      value: studentScrollMock,
      configurable: true,
    });
    Object.defineProperty(studentInput, 'focus', {
      value: studentFocusMock,
      configurable: true,
    });

    fireEvent.click(
      within(screen.getByTestId('format-card-online')).getByRole('button', {
        name: /online/i,
      })
    );
    fireEvent.change(within(screen.getByTestId('format-card-online')).getByRole('spinbutton'), {
      target: { value: '75' },
    });

    fireEvent.click(screen.getByRole('button', { name: /save & continue/i }));

    await waitFor(() => {
      expect(
        within(studentCard).getByText('Enter a rate to activate this lesson type.')
      ).toBeInTheDocument();
    });
    expect(
      within(screen.getByTestId('format-card-online')).queryByText(
        'Enter a rate to activate this lesson type.'
      )
    ).not.toBeInTheDocument();
    expect(fetchWithAuthMock).not.toHaveBeenCalledWith(
      '/api/v1/instructors/me',
      expect.anything()
    );
    expect(studentScrollMock).toHaveBeenCalledWith({
      behavior: 'smooth',
      block: 'center',
    });
    expect(studentFocusMock).toHaveBeenCalled();

    rafSpy.mockRestore();
  });

  it('shows empty-rate errors on every offending service card and scrolls to the first one', async () => {
    useCatalogBrowseMock.mockReturnValue({
      data: {
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
              {
                id: 'svc-2',
                name: 'Guitar',
                subcategory_id: 'sub-1',
                eligible_age_groups: ['kids', 'teens', 'adults'],
                description: null,
                display_order: 2,
              },
            ],
          },
        ],
      },
      isLoading: false,
      error: null,
    });
    useInstructorServiceAreasMock.mockReturnValue({
      data: {
        items: [
          {
            display_key: 'n1',
            display_name: 'Upper East Side',
            borough: 'Manhattan',
          },
        ],
      },
      isLoading: false,
      isFetched: true,
      isError: false,
    });

    const rafSpy = jest
      .spyOn(window, 'requestAnimationFrame')
      .mockImplementation((callback: FrameRequestCallback) => {
        callback(0);
        return 1;
      });

    renderWithClient(<Step3SkillsPricing />);

    fireEvent.click(screen.getByRole('button', { name: /music/i }));
    fireEvent.click(await screen.findByRole('button', { name: /toggle subcategory piano/i }));
    fireEvent.click(await screen.findByRole('button', { name: /add service piano/i }));
    fireEvent.click(await screen.findByRole('button', { name: /add service guitar/i }));

    const studentCards = screen.getAllByTestId('format-card-student_location');
    const firstScrollMock = jest.fn();
    Object.defineProperty(studentCards[0] as Element, 'scrollIntoView', {
      value: firstScrollMock,
      configurable: true,
    });

    fireEvent.click(screen.getByRole('button', { name: /save & continue/i }));

    await waitFor(() => {
      expect(
        screen.getAllByText('Enter a rate to activate this lesson type.')
      ).toHaveLength(2);
    });
    expect(firstScrollMock).toHaveBeenCalled();
    rafSpy.mockRestore();
  });

  it('rejects an out-of-service-area teaching address and blocks save', async () => {
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
          services: [
            {
              id: 'svc-1',
              service_catalog_id: 'svc-1',
              format_prices: [{ format: 'instructor_location', hourly_rate: 95 }],
              duration_options: [60],
              filter_selections: {},
              age_groups: ['adults'],
            },
          ],
          service_area_neighborhoods: [],
          service_area_boroughs: [],
          service_area_summary: '',
          preferred_teaching_locations: [],
          current_tier_pct: null,
        },
      },
    });
    fetchWithAuthMock.mockImplementation(async (url: string, _options?: RequestInit) => {
      if (url.startsWith('/api/v1/addresses/places/details?')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            formatted_address: '1 Newark St, Hoboken, NJ',
            latitude: 40.744,
            longitude: -74.032,
            provider_id: 'google:hoboken_nj',
          }),
        } as Response;
      }

      if (url === '/api/v1/addresses/validate-service-area') {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            in_service_area: false,
            neighborhood_display_name: null,
          }),
        } as Response;
      }

      return {
        ok: true,
        status: 200,
        json: async () => ({}),
      } as Response;
    });

    renderWithClient(<Step3SkillsPricing />);

    fireEvent.change(screen.getByPlaceholderText('Type address...'), {
      target: { value: 'Hoboken NJ' },
    });
    fireEvent.click(screen.getByTestId('ptl-input-select-suggestion'));

    await waitFor(() => {
      expect(
        screen.getByText('This address is outside our current service area.')
      ).toBeInTheDocument();
    });
    expect(screen.queryByTestId('ptl-chip-0')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /save & continue/i }));

    expect(fetchWithAuthMock).not.toHaveBeenCalledWith(
      '/api/v1/instructors/me',
      expect.anything()
    );
  });

  it('shows the verification error when service-area validation fails', async () => {
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
          services: [
            {
              id: 'svc-1',
              service_catalog_id: 'svc-1',
              format_prices: [{ format: 'instructor_location', hourly_rate: 95 }],
              duration_options: [60],
              filter_selections: {},
              age_groups: ['adults'],
            },
          ],
          service_area_neighborhoods: [],
          service_area_boroughs: [],
          service_area_summary: '',
          preferred_teaching_locations: [],
          current_tier_pct: null,
        },
      },
    });
    fetchWithAuthMock.mockImplementation(async (url: string, _options?: RequestInit) => {
      if (url.startsWith('/api/v1/addresses/places/details?')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            formatted_address: '123 Studio Lane, New York, NY',
            latitude: 40.775,
            longitude: -73.955,
            provider_id: 'google:place_1',
          }),
        } as Response;
      }

      if (url === '/api/v1/addresses/validate-service-area') {
        return {
          ok: false,
          status: 500,
          json: async () => ({ detail: 'boom' }),
        } as Response;
      }

      return {
        ok: true,
        status: 200,
        json: async () => ({}),
      } as Response;
    });

    renderWithClient(<Step3SkillsPricing />);

    fireEvent.click(screen.getByTestId('ptl-input-select-suggestion'));

    await waitFor(() => {
      expect(
        screen.getByText(
          "We couldn't verify this address. Please select an address from the dropdown suggestions."
        )
      ).toBeInTheDocument();
    });
  });

  it('keeps the first teaching address and rejects an invalid second one', async () => {
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
          services: [
            {
              id: 'svc-1',
              service_catalog_id: 'svc-1',
              format_prices: [{ format: 'instructor_location', hourly_rate: 95 }],
              duration_options: [60],
              filter_selections: {},
              age_groups: ['adults'],
            },
          ],
          service_area_neighborhoods: [],
          service_area_boroughs: [],
          service_area_summary: '',
          preferred_teaching_locations: [],
          current_tier_pct: null,
        },
      },
    });
    fetchWithAuthMock.mockImplementation(async (url: string, _options?: RequestInit) => {
      if (url.includes('place_id=place_1')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            formatted_address: '123 Studio Lane, New York, NY',
            latitude: 40.775,
            longitude: -73.955,
            provider_id: 'google:place_1',
          }),
        } as Response;
      }

      if (url.includes('place_id=hoboken_nj')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            formatted_address: '1 Newark St, Hoboken, NJ',
            latitude: 40.744,
            longitude: -74.032,
            provider_id: 'google:hoboken_nj',
          }),
        } as Response;
      }

      if (url === '/api/v1/addresses/validate-service-area') {
        const body = JSON.parse(String(_options?.body ?? '{}')) as {
          latitude?: number;
          longitude?: number;
        };
        if (body.latitude === 40.775 && body.longitude === -73.955) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              in_service_area: true,
              neighborhood_display_name: 'Upper East Side',
            }),
          } as Response;
        }

        return {
          ok: true,
          status: 200,
          json: async () => ({
            in_service_area: false,
            neighborhood_display_name: null,
          }),
        } as Response;
      }

      return {
        ok: true,
        status: 200,
        json: async () => ({}),
      } as Response;
    });

    renderWithClient(<Step3SkillsPricing />);

    fireEvent.click(screen.getByTestId('ptl-input-select-suggestion'));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add address/i })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole('button', { name: /add address/i }));

    await waitFor(() => {
      expect(screen.getByTestId('ptl-chip-0')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText('Type address...'), {
      target: { value: 'Hoboken NJ' },
    });
    fireEvent.click(screen.getByTestId('ptl-input-select-suggestion'));

    await waitFor(() => {
      expect(
        screen.getByText('This address is outside our current service area.')
      ).toBeInTheDocument();
    });
    expect(screen.getByTestId('ptl-chip-0')).toHaveTextContent(
      '123 Studio Lane, New York, NY'
    );
    expect(screen.queryByTestId('ptl-chip-1')).not.toBeInTheDocument();
  });
});
