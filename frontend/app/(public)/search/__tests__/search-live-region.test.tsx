import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import SearchResultsPage from '../page';

jest.mock('next/dynamic', () => () => {
  const MockCoverageMap = () => <div data-testid="coverage-map" />;
  MockCoverageMap.displayName = 'MockCoverageMap';
  return MockCoverageMap;
});

jest.mock('next/navigation', () => ({
  useSearchParams: jest.fn(() => new URLSearchParams('q=piano lessons')),
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
  const MockInstructorCard = () => <div data-testid="instructor-card" />;
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

const createResolvedSearchResponse = () => ({
  data: {
    results: [
      {
        instructor_id: 'inst-1',
        relevance_score: 0.9,
        instructor: {
          first_name: 'Ava',
          last_initial: 'L',
          bio_snippet: '',
          profile_picture_url: '',
          verified: false,
          is_founding_instructor: false,
          years_experience: 4,
          teaching_locations: [],
        },
        rating: { average: 4.7, count: 12 },
        coverage_areas: [],
        best_match: {
          service_id: 'svc-1',
          service_catalog_id: 'cat-1',
          name: 'Piano Lessons',
          description: '',
          price_per_hour: 60,
          offers_at_location: false,
        },
        other_matches: [],
      },
    ],
    meta: { total_results: 1 },
  },
  status: 200,
});

describe('Search live region announcements', () => {
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
          addListener: jest.fn(),
          removeListener: jest.fn(),
          dispatchEvent: jest.fn(),
        })),
      });
    }

    if (!('IntersectionObserver' in window)) {
      class MockIntersectionObserver implements IntersectionObserver {
        readonly root: Element | Document | null = null;
        readonly rootMargin = '0px';
        readonly thresholds = [0];

        disconnect = jest.fn();
        observe = jest.fn();
        takeRecords = jest.fn(() => []);
        unobserve = jest.fn();
      }

      Object.defineProperty(window, 'IntersectionObserver', {
        writable: true,
        value: MockIntersectionObserver,
      });
      Object.defineProperty(globalThis, 'IntersectionObserver', {
        writable: true,
        value: MockIntersectionObserver,
      });
    }
  });

  beforeEach(() => {
    jest.clearAllMocks();
    mockPublicApi.getInstructorAvailability.mockResolvedValue({
      data: { availability_by_date: {} },
      status: 200,
    });
    mockPublicApi.getAllServicesWithInstructors.mockResolvedValue({
      data: {
        categories: [],
        metadata: { updated_at: new Date().toISOString(), cached_for_seconds: 0, total_categories: 0 },
      },
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

  it('announces loading state and final result count', async () => {
    let resolveSearch!: (value: ReturnType<typeof createResolvedSearchResponse>) => void;
    const pendingSearch = new Promise<ReturnType<typeof createResolvedSearchResponse>>((resolve) => {
      resolveSearch = resolve;
    });
    mockPublicApi.searchWithNaturalLanguage.mockImplementationOnce(
      () => pendingSearch
    );

    const queryClient = createTestQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <SearchResultsPage />
      </QueryClientProvider>
    );

    const liveRegion = screen.getByTestId('search-results-live-region');
    expect(liveRegion).toHaveAttribute('aria-live', 'polite');
    expect(liveRegion).toHaveAttribute('aria-atomic', 'true');

    await waitFor(() => {
      expect(liveRegion).toHaveTextContent('Loading instructors...');
    });

    resolveSearch(createResolvedSearchResponse());

    await waitFor(() => {
      expect(liveRegion).toHaveTextContent('1 instructor found');
    });
  });
});
