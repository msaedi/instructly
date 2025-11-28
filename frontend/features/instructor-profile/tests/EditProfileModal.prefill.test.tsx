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

jest.mock('@/lib/instructorServices', () => ({
  normalizeInstructorServices: jest.fn(async () => []),
  hydrateCatalogNameById: jest.fn(),
  displayServiceName: jest.fn(),
}));

jest.mock('@/lib/profileServiceAreas', () => ({
  getServiceAreaBoroughs: jest.fn(() => []),
}));

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingConfig: () => ({
    config: { price_floor_cents: { private_in_person: 8500, private_remote: 6500 } },
    isLoading: false,
    error: null,
  }),
  PRICING_CONFIG_QUERY_KEY: ['config', 'pricing'],
}));

jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(async (url: string) => {
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
        user: { first_name: 'Test', last_initial: 'T' },
        services: [],
        service_area_boroughs: [],
        service_area_neighborhoods: [],
      }),
    } as unknown as Response;
  }),
  API_ENDPOINTS: {
    INSTRUCTOR_PROFILE: '/instructors/me',
    ME: '/me',
    NYC_ZIP_CHECK: '/zip-check',
  },
  getConnectStatus: jest.fn(),
  createStripeIdentitySession: jest.fn(),
  createSignedUpload: jest.fn(),
}));

import { render, screen, waitFor } from '@testing-library/react';
import EditProfileModal from '@/components/modals/EditProfileModal';

describe('EditProfileModal preferred locations prefill', () => {
  it('prefills teaching and public locations from props when opened', async () => {
    render(
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
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('Home1')).toBeInTheDocument();
    });

    expect(await screen.findByText(/Central Park Zoo/)).toBeInTheDocument();
  });
});
