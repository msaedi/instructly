jest.mock('@/components/forms/PlacesAutocompleteInput', () => ({
  PlacesAutocompleteInput: ({ value, onValueChange, inputClassName, placeholder }: {
    value: string;
    onValueChange: (val: string) => void;
    inputClassName?: string;
    placeholder?: string;
  }) => (
    <input
      data-testid="places-autocomplete"
      value={value}
      onChange={(event) => onValueChange(event.target.value)}
      className={inputClassName}
      placeholder={placeholder}
    />
  ),
}));

jest.mock('@/components/neighborhoods/NeighborhoodSelector', () => ({
  NeighborhoodSelector: ({
    value,
  }: {
    value?: string[];
  }) => <div data-testid="service-areas-count">{value?.length ?? 0}</div>,
}));

jest.mock('@/lib/instructorServices', () => {
  // type-coverage:ignore-next-line -- jest.Mock inherits Function which contains any
  const normalizeInstructorServices = jest.fn<Promise<never[]>, [unknown]>(async () => []);
  // type-coverage:ignore-next-line -- jest.Mock inherits Function which contains any
  const hydrateCatalogNameById = jest.fn<string | undefined, [string]>();
  // type-coverage:ignore-next-line -- jest.Mock inherits Function which contains any
  const displayServiceName = jest.fn<string, [Record<string, unknown>, (id: string) => string | undefined]>();
  // type-coverage:ignore-next-line -- jest.Mock inherits Function which contains any
  return { normalizeInstructorServices, hydrateCatalogNameById, displayServiceName };
});

jest.mock('@/lib/profileServiceAreas', () => {
  // type-coverage:ignore-next-line -- jest.Mock inherits Function which contains any
  const getServiceAreaBoroughs = jest.fn<never[], []>(() => []);
  // type-coverage:ignore-next-line -- jest.Mock inherits Function which contains any
  return { getServiceAreaBoroughs };
});

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingConfig: () => ({
    config: { price_floor_cents: { private_in_person: 8500, private_remote: 6500 } },
    isLoading: false,
    error: null,
  }),
  PRICING_CONFIG_QUERY_KEY: ['config', 'pricing'],
}));

jest.mock('@/lib/api', () => {
  // type-coverage:ignore-next-line -- jest.Mock inherits Function which contains any
  const fetchWithAuth = jest.fn<Promise<Response>, [string]>(async (url: string) => {
    if (url === '/api/v1/addresses/service-areas/me') {
      return {
        ok: true,
        status: 200,
        json: async () => ({ items: [] }),
      } as unknown as Response;
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({
        user: { first_name: 'Test', last_initial: 'T.' },
        services: [],
        service_area_boroughs: [],
        service_area_neighborhoods: [],
      }),
    } as unknown as Response;
  });
  // type-coverage:ignore-next-line -- jest.Mock inherits Function which contains any
  const getConnectStatus = jest.fn<void, []>();
  // type-coverage:ignore-next-line -- jest.Mock inherits Function which contains any
  const createStripeIdentitySession = jest.fn<void, []>();
  // type-coverage:ignore-next-line -- jest.Mock inherits Function which contains any
  const createSignedUpload = jest.fn<void, []>();
  return {
    // type-coverage:ignore-next-line
    fetchWithAuth,
    API_ENDPOINTS: {
      INSTRUCTOR_PROFILE: '/instructors/me',
      ME: '/me',
      NYC_ZIP_CHECK: '/zip-check',
    },
    // type-coverage:ignore-next-line
    getConnectStatus,
    // type-coverage:ignore-next-line
    createStripeIdentitySession,
    // type-coverage:ignore-next-line
    createSignedUpload,
  };
});

import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import EditProfileModal from '@/components/modals/EditProfileModal';

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

describe('EditProfileModal preferred locations prefill', () => {
  it('prefills teaching and public locations from props when opened', async () => {
    const queryClient = createTestQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <EditProfileModal
          isOpen
          onClose={() => {}}
          onSuccess={() => {}}
          variant="areas"
          selectedServiceAreas={[]}
          preferredTeaching={[{ address: '225 Cherry Street, NYC', label: 'Home1' }]}
          preferredPublic={[{ address: 'Central Park Zoo' }]}
          onSave={jest.fn()}
        />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('Home1')).toBeInTheDocument();
    });

    expect(await screen.findByText(/Central Park Zoo/)).toBeInTheDocument();
  });
});
