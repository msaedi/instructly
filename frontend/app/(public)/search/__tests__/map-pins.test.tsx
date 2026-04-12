import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import SearchResultsPage from '../page';

let mockSearchParamsValue = 'q=piano lessons';

jest.mock('next/dynamic', () => () => {
  const MockCoverageMap = ({
    locationPins,
    onAreaClick,
    onBoundsChange,
    showSearchAreaButton,
    onSearchArea,
  }: {
    locationPins?: unknown[];
    onAreaClick?: (areaName: string, instructorIds: string[]) => void;
    onBoundsChange?: (bounds: unknown) => void;
    showSearchAreaButton?: boolean;
    onSearchArea?: () => void;
  }) => (
    <div data-testid="coverage-map" data-pins={JSON.stringify(locationPins ?? [])}>
      <button
        type="button"
        data-testid="coverage-bounds-les"
        onClick={() =>
          onBoundsChange?.({
            _southWest: { lat: 40.7, lng: -74.01 },
            _northEast: { lat: 40.72, lng: -73.99 },
          })
        }
      >
        Tight bounds
      </button>
      {showSearchAreaButton ? (
        <button type="button" data-testid="coverage-search-area" onClick={() => onSearchArea?.()}>
          Search this area
        </button>
      ) : null}
      <button
        type="button"
        data-testid="coverage-area-uws"
        onClick={() => onAreaClick?.('Upper West Side', ['inst-2', 'inst-1'])}
      >
        Upper West Side
      </button>
      <button
        type="button"
        data-testid="coverage-area-chelsea"
        onClick={() => onAreaClick?.('Chelsea', ['inst-2'])}
      >
        Chelsea
      </button>
    </div>
  );
  MockCoverageMap.displayName = 'MockCoverageMap';
  return MockCoverageMap;
});

jest.mock('next/navigation', () => ({
  useSearchParams: jest.fn(() => new URLSearchParams(mockSearchParamsValue)),
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
  })),
  usePathname: jest.fn(() => '/search'),
}));

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    searchWithNaturalLanguage: jest.fn(),
    searchInstructors: jest.fn(),
    getInstructorAvailability: jest.fn(),
    getAllServicesWithInstructors: jest.fn(),
    getCategoriesWithSubcategories: jest.fn(),
    getSubcategoryFilters: jest.fn(),
  },
}));

jest.mock('@/lib/searchTracking', () => ({
  recordSearch: jest.fn(),
}));

jest.mock('@/lib/config/backgroundProvider', () => ({
  useBackgroundConfig: jest.fn(() => ({ setActivity: jest.fn() })),
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(() => ({ isAuthenticated: false })),
}));

jest.mock('@/components/InstructorCard', () => {
  const MockInstructorCard = ({ instructor }: { instructor?: { user_id?: string } }) => (
    <div data-testid="instructor-card">{instructor?.user_id ?? 'unknown-instructor'}</div>
  );
  MockInstructorCard.displayName = 'MockInstructorCard';
  return { __esModule: true, default: MockInstructorCard };
});

jest.mock('@/components/UserProfileDropdown', () => {
  const MockUserProfileDropdown = () => <div data-testid="user-profile-dropdown" />;
  MockUserProfileDropdown.displayName = 'MockUserProfileDropdown';
  return { __esModule: true, default: MockUserProfileDropdown };
});

jest.mock('@/features/student/booking/components/TimeSelectionModal', () => {
  const MockTimeSelectionModal = () => <div data-testid="time-selection-modal" />;
  MockTimeSelectionModal.displayName = 'MockTimeSelectionModal';
  return { __esModule: true, default: MockTimeSelectionModal };
});

const mockPublicApi = jest.requireMock('@/features/shared/api/client').publicApi as {
  searchWithNaturalLanguage: jest.Mock;
  searchInstructors: jest.Mock;
  getInstructorAvailability: jest.Mock;
  getAllServicesWithInstructors: jest.Mock;
  getCategoriesWithSubcategories: jest.Mock;
  getSubcategoryFilters: jest.Mock;
};

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

describe('Search results map pins', () => {
  beforeAll(() => {
    if (!global.fetch) {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ type: 'FeatureCollection', features: [] }),
      }) as unknown as typeof fetch;
    }

    if (!window.matchMedia) {
      Object.defineProperty(window, 'matchMedia', {
        writable: true,
        value: jest.fn().mockImplementation((query: string) => ({
          matches: false,
          media: query,
          onchange: null,
          addEventListener: jest.fn(),
          removeEventListener: jest.fn(),
          addListener: jest.fn(), // deprecated
          removeListener: jest.fn(), // deprecated
          dispatchEvent: jest.fn(),
        })),
      });
    }

    if (!('IntersectionObserver' in window)) {
      class MockIntersectionObserver {
        observe = jest.fn();
        unobserve = jest.fn();
        disconnect = jest.fn();
      }
      Object.defineProperty(window, 'IntersectionObserver', {
        writable: true,
        configurable: true,
        value: MockIntersectionObserver,
      });
    }

    if (!Element.prototype.scrollIntoView) {
      Element.prototype.scrollIntoView = jest.fn();
    }
  });

  beforeEach(() => {
    mockSearchParamsValue = 'q=piano lessons';
    mockPublicApi.searchWithNaturalLanguage.mockResolvedValue({
      data: {
        results: [
          {
            instructor_id: 'inst-1',
            relevance_score: 0.9,
            instructor: {
              first_name: 'Ava',
              last_initial: 'L.',
              bio_snippet: '',
              profile_picture_url: 'https://cdn.example.com/ava.jpg',
              verified: false,
              is_founding_instructor: false,
              years_experience: 4,
              teaching_locations: [
                {
                  approx_lat: 40.7128,
                  approx_lng: -74.006,
                  neighborhood: 'Lower East Side',
                },
              ],
            },
            rating: { average: 4.7, count: 12 },
            coverage_areas: ['Lower East Side'],
            best_match: {
              service_id: 'svc-1',
              service_catalog_id: 'cat-1',
              name: 'Piano Lessons',
              description: '',
              min_hourly_rate: 60,
              format_prices: [
                { format: 'instructor_location', hourly_rate: 60 },
              ],
            },
            other_matches: [],
          },
        ],
        meta: { total_results: 1 },
      },
      status: 200,
    });
    mockPublicApi.searchInstructors.mockResolvedValue({
      data: {
        items: [],
        total: 0,
        page: 1,
        per_page: 20,
        has_next: false,
        has_prev: false,
      },
      status: 200,
    });

    mockPublicApi.getInstructorAvailability.mockResolvedValue({
      data: { availability_by_date: {} },
      status: 200,
    });
    mockPublicApi.getAllServicesWithInstructors.mockResolvedValue({
      data: { categories: [], metadata: { updated_at: new Date().toISOString(), cached_for_seconds: 0, total_categories: 0 } },
      status: 200,
    });
    mockPublicApi.getCategoriesWithSubcategories.mockResolvedValue({
      data: [],
      status: 200,
    });
    mockPublicApi.getSubcategoryFilters.mockResolvedValue({
      data: [],
      status: 200,
    });
  });

  it('passes teaching location pins to the map', async () => {
    const queryClient = createTestQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <SearchResultsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(mockPublicApi.searchWithNaturalLanguage).toHaveBeenCalled();
    });

    await waitFor(() => {
      const pinsRaw = screen.getByTestId('coverage-map').getAttribute('data-pins') ?? '[]';
      const pins = JSON.parse(pinsRaw) as Array<{
        lat: number;
        lng: number;
        label?: string;
        instructorId?: string;
      }>;
      expect(pins.length).toBe(1);
      expect(pins[0]).toMatchObject({
        lat: 40.7128,
        lng: -74.006,
        label: 'Lower East Side',
        instructorId: 'inst-1',
        displayName: 'Ava L.',
        profilePictureUrl: 'https://cdn.example.com/ava.jpg',
      });
    });
  });

  it('passes profile picture URLs to map pins for catalog search results', async () => {
    mockSearchParamsValue = 'service_catalog_id=cat-1&service_name=Piano';
    mockPublicApi.searchInstructors.mockResolvedValue({
      data: {
        items: [
          {
            id: 'profile-1',
            user_id: 'inst-1',
            bio: 'Catalog search instructor bio',
            years_experience: 7,
            created_at: new Date('2026-01-01T00:00:00.000Z').toISOString(),
            profile_picture_url: 'https://cdn.example.com/catalog-ava.jpg',
            user: {
              id: 'inst-1',
              first_name: 'Ava',
              last_initial: 'L.',
            },
            services: [
              {
                id: 'svc-1',
                service_catalog_id: 'cat-1',
                hourly_rate: 60,
                min_hourly_rate: 60,
                name: 'Piano Lessons',
                format_prices: [{ format: 'instructor_location', hourly_rate: 60 }],
                offers_travel: false,
                offers_at_location: true,
                offers_online: false,
                duration_options: [60],
                is_active: true,
              },
            ],
            preferred_teaching_locations: [
              {
                approx_lat: 40.7128,
                approx_lng: -74.006,
                neighborhood: 'Lower East Side',
              },
            ],
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
        has_next: false,
        has_prev: false,
      },
      status: 200,
    });

    const queryClient = createTestQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <SearchResultsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(mockPublicApi.searchInstructors).toHaveBeenCalled();
    });

    await waitFor(() => {
      const pinsRaw = screen.getByTestId('coverage-map').getAttribute('data-pins') ?? '[]';
      const pins = JSON.parse(pinsRaw) as Array<{
        lat: number;
        lng: number;
        label?: string;
        instructorId?: string;
        profilePictureUrl?: string | null;
      }>;
      expect(pins.length).toBe(1);
      expect(pins[0]).toMatchObject({
        lat: 40.7128,
        lng: -74.006,
        label: 'Lower East Side',
        instructorId: 'inst-1',
        displayName: 'Ava L.',
        profilePictureUrl: 'https://cdn.example.com/catalog-ava.jpg',
      });
    });
  });

  it('falls back to id when catalog results are missing user_id', async () => {
    mockSearchParamsValue = 'service_catalog_id=cat-1&service_name=Piano';
    mockPublicApi.searchInstructors.mockResolvedValue({
      data: {
        items: [
          {
            id: 'inst-legacy',
            user_id: '',
            bio: 'Catalog search instructor bio',
            years_experience: 7,
            created_at: new Date('2026-01-01T00:00:00.000Z').toISOString(),
            profile_picture_url: 'https://cdn.example.com/catalog-legacy.jpg',
            user: {
              id: 'inst-legacy',
              first_name: 'Ava',
              last_initial: 'L.',
            },
            services: [
              {
                id: 'svc-1',
                service_catalog_id: 'cat-1',
                hourly_rate: 60,
                min_hourly_rate: 60,
                name: 'Piano Lessons',
                format_prices: [{ format: 'instructor_location', hourly_rate: 60 }],
                offers_travel: false,
                offers_at_location: true,
                offers_online: false,
                duration_options: [60],
                is_active: true,
              },
            ],
            preferred_teaching_locations: [
              {
                approx_lat: 40.7128,
                approx_lng: -74.006,
                neighborhood: 'Lower East Side',
              },
            ],
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
        has_next: false,
        has_prev: false,
      },
      status: 200,
    });

    const queryClient = createTestQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <SearchResultsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(mockPublicApi.searchInstructors).toHaveBeenCalled();
    });

    await waitFor(() => {
      const pinsRaw = screen.getByTestId('coverage-map').getAttribute('data-pins') ?? '[]';
      const pins = JSON.parse(pinsRaw) as Array<{
        instructorId?: string;
      }>;
      expect(pins).toHaveLength(1);
      expect(pins[0]).toMatchObject({ instructorId: 'inst-legacy' });
      expect(document.getElementById('instructor-card-inst-legacy')).toBeInTheDocument();
    });
  });

  it('keeps map pins stable when map bounds filter narrows the sidebar results', async () => {
    mockPublicApi.searchWithNaturalLanguage.mockResolvedValue({
      data: {
        results: [
          {
            instructor_id: 'inst-1',
            relevance_score: 0.95,
            instructor: {
              first_name: 'Ava',
              last_initial: 'L.',
              bio_snippet: '',
              profile_picture_url: 'https://cdn.example.com/ava.jpg',
              verified: false,
              is_founding_instructor: false,
              years_experience: 4,
              teaching_locations: [
                {
                  approx_lat: 40.7128,
                  approx_lng: -74.006,
                  neighborhood: 'Lower East Side',
                },
              ],
            },
            rating: { average: 4.7, count: 12 },
            coverage_areas: ['Lower East Side'],
            best_match: {
              service_id: 'svc-1',
              service_catalog_id: 'cat-1',
              name: 'Piano Lessons',
              description: '',
              min_hourly_rate: 60,
              format_prices: [{ format: 'instructor_location', hourly_rate: 60 }],
            },
            other_matches: [],
          },
          {
            instructor_id: 'inst-2',
            relevance_score: 0.9,
            instructor: {
              first_name: 'James',
              last_initial: 'W.',
              bio_snippet: '',
              profile_picture_url: 'https://cdn.example.com/james.jpg',
              verified: false,
              is_founding_instructor: false,
              years_experience: 6,
              teaching_locations: [
                {
                  approx_lat: 40.78,
                  approx_lng: -73.97,
                  neighborhood: 'Upper West Side',
                },
              ],
            },
            rating: { average: 4.6, count: 9 },
            coverage_areas: ['Upper West Side'],
            best_match: {
              service_id: 'svc-2',
              service_catalog_id: 'cat-1',
              name: 'Piano Lessons',
              description: '',
              min_hourly_rate: 75,
              format_prices: [{ format: 'instructor_location', hourly_rate: 75 }],
            },
            other_matches: [],
          },
        ],
        meta: { total_results: 2 },
      },
      status: 200,
    });

    const queryClient = createTestQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <SearchResultsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(mockPublicApi.searchWithNaturalLanguage).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getAllByTestId('instructor-card')).toHaveLength(2);
    });

    fireEvent.click(screen.getByTestId('coverage-bounds-les'));

    const searchAreaButton = await screen.findByTestId('coverage-search-area');
    fireEvent.click(searchAreaButton);

    await waitFor(() => {
      expect(screen.getAllByTestId('instructor-card')).toHaveLength(1);
    });

    const pinsRaw = screen.getByTestId('coverage-map').getAttribute('data-pins') ?? '[]';
    const pins = JSON.parse(pinsRaw) as Array<{
      instructorId?: string;
    }>;
    expect(pins).toHaveLength(2);
    expect(pins.map((pin) => pin.instructorId)).toEqual(['inst-1', 'inst-2']);
  });

  it('cycles through visible instructors when the same coverage area is clicked repeatedly', async () => {
    mockPublicApi.searchWithNaturalLanguage.mockResolvedValue({
      data: {
        results: [
          {
            instructor_id: 'inst-1',
            relevance_score: 0.95,
            instructor: {
              first_name: 'Sarah',
              last_initial: 'C.',
              bio_snippet: '',
              profile_picture_url: '',
              verified: false,
              is_founding_instructor: false,
              years_experience: 12,
              teaching_locations: [],
            },
            rating: { average: 4.8, count: 22 },
            coverage_areas: ['Upper West Side'],
            best_match: {
              service_id: 'svc-1',
              service_catalog_id: 'cat-1',
              name: 'Piano Lessons',
              description: '',
              min_hourly_rate: 90,
              format_prices: [{ format: 'student_location', hourly_rate: 90 }],
            },
            other_matches: [],
          },
          {
            instructor_id: 'inst-2',
            relevance_score: 0.9,
            instructor: {
              first_name: 'James',
              last_initial: 'W.',
              bio_snippet: '',
              profile_picture_url: '',
              verified: false,
              is_founding_instructor: false,
              years_experience: 8,
              teaching_locations: [],
            },
            rating: { average: 4.7, count: 15 },
            coverage_areas: ['Upper West Side', 'Chelsea'],
            best_match: {
              service_id: 'svc-2',
              service_catalog_id: 'cat-1',
              name: 'Piano Lessons',
              description: '',
              min_hourly_rate: 120,
              format_prices: [{ format: 'student_location', hourly_rate: 120 }],
            },
            other_matches: [],
          },
        ],
        meta: { total_results: 2 },
      },
      status: 200,
    });

    const scrolledIds: string[] = [];
    const scrollSpy = jest
      .spyOn(Element.prototype, 'scrollIntoView')
      .mockImplementation(function mockScrollIntoView(this: Element) {
        scrolledIds.push((this as HTMLElement).id);
      });

    const queryClient = createTestQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <SearchResultsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(mockPublicApi.searchWithNaturalLanguage).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(document.getElementById('instructor-card-inst-1')).toBeInTheDocument();
      expect(document.getElementById('instructor-card-inst-2')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('coverage-area-uws'));
    expect(scrolledIds.at(-1)).toBe('instructor-card-inst-1');

    fireEvent.click(screen.getByTestId('coverage-area-uws'));
    expect(scrolledIds.at(-1)).toBe('instructor-card-inst-2');

    fireEvent.click(screen.getByTestId('coverage-area-chelsea'));
    expect(scrolledIds.at(-1)).toBe('instructor-card-inst-2');

    scrollSpy.mockRestore();
  });

  it('supports listbox semantics and keyboard interaction for sort options', async () => {
    const queryClient = createTestQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <SearchResultsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(mockPublicApi.searchWithNaturalLanguage).toHaveBeenCalled();
    });

    const trigger = screen.getByRole('button', { name: /recommended/i });
    expect(trigger).toHaveAttribute('aria-haspopup', 'listbox');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    const listboxId = trigger.getAttribute('aria-controls');
    expect(listboxId).toBeTruthy();

    trigger.focus();
    fireEvent.keyDown(trigger, { key: 'ArrowDown' });

    const listbox = await screen.findByRole('listbox', { name: 'Sort results' });
    expect(listbox).toHaveAttribute('id', listboxId);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(within(listbox).getAllByRole('option')).toHaveLength(4);
    within(listbox).getAllByRole('option').forEach((option) => {
      expect(option).toHaveAttribute('tabindex');
    });

    fireEvent.keyDown(listbox, { key: 'Enter' });
    await waitFor(() => {
      expect(trigger).toHaveTextContent('Price: Low');
      expect(trigger).toHaveAttribute('aria-expanded', 'false');
    });

    fireEvent.click(trigger);
    const reopenedListbox = await screen.findByRole('listbox', { name: 'Sort results' });
    fireEvent.keyDown(reopenedListbox, { key: 'Escape' });
    await waitFor(() => {
      expect(screen.queryByRole('listbox', { name: 'Sort results' })).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(trigger).toHaveFocus();
    });

    fireEvent.click(trigger);
    const tabListbox = await screen.findByRole('listbox', { name: 'Sort results' });
    fireEvent.keyDown(tabListbox, { key: 'Tab' });
    await waitFor(() => {
      expect(screen.queryByRole('listbox', { name: 'Sort results' })).not.toBeInTheDocument();
    });
  });

  it('renders the rate limit banner as an alert for 429 responses', async () => {
    mockPublicApi.searchWithNaturalLanguage.mockResolvedValueOnce({
      status: 429,
      error: 'Our hamsters are sprinting. Please try again shortly.',
      retryAfterSeconds: 12,
    });

    const queryClient = createTestQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <SearchResultsPage />
      </QueryClientProvider>
    );

    const banner = await screen.findByTestId('rate-limit-banner');
    expect(banner).toHaveAttribute('role', 'alert');
    expect(banner).toHaveTextContent('Give them 12s');
  });
});
