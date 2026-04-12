import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import SearchResultsPage from '../page';

jest.mock('next/dynamic', () => () => {
  const MockCoverageMap = ({
    locationPins,
    highlightInstructorId,
    focusInstructorId,
    onPinHover,
    onPinClick,
  }: {
    locationPins?: unknown[];
    highlightInstructorId?: string | null;
    focusInstructorId?: string | null;
    onPinHover?: (instructorId: string | null) => void;
    onPinClick?: (instructorId: string) => void;
  }) => (
    <div
      data-testid="coverage-map"
      data-pin-count={String(Array.isArray(locationPins) ? locationPins.length : 0)}
      data-highlight-id={highlightInstructorId ?? ''}
      data-focus-id={focusInstructorId ?? ''}
    >
      <button
        type="button"
        data-testid="pin-hover-inst-1"
        onMouseOver={() => onPinHover?.('inst-1')}
        onMouseOut={() => onPinHover?.(null)}
      >
        Hover pin
      </button>
      <button
        type="button"
        data-testid="pin-click-inst-1"
        onClick={() => onPinClick?.('inst-1')}
      >
        Click pin
      </button>
    </div>
  );

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
  const MockInstructorCard = ({ instructor }: { instructor?: { user_id?: string } }) => (
    <div data-testid="instructor-card-body">{instructor?.user_id ?? 'unknown-instructor'}</div>
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

describe('SearchResultsPage map sync', () => {
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
              format_prices: [{ format: 'instructor_location', hourly_rate: 60 }],
            },
            other_matches: [],
          },
        ],
        meta: { total_results: 1 },
      },
      status: 200,
    });

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

  it('updates the map highlight prop when a card is hovered', async () => {
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
    });

    const card = document.getElementById('instructor-card-inst-1');
    expect(card).toBeInTheDocument();

    fireEvent.mouseEnter(card!);

    expect(screen.getByTestId('coverage-map')).toHaveAttribute('data-highlight-id', 'inst-1');

    fireEvent.mouseLeave(card!);

    expect(screen.getByTestId('coverage-map')).toHaveAttribute('data-highlight-id', '');
  });

  it('highlights the corresponding card when a map pin is hovered', async () => {
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
    });

    const card = document.getElementById('instructor-card-inst-1');
    expect(card).toHaveAttribute('data-hovered', 'false');

    fireEvent.mouseOver(screen.getByTestId('pin-hover-inst-1'));
    expect(card).toHaveAttribute('data-hovered', 'true');

    fireEvent.mouseOut(screen.getByTestId('pin-hover-inst-1'));
    expect(card).toHaveAttribute('data-hovered', 'false');
  });

  it('scrolls the matching card into view when a map pin is clicked', async () => {
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
    });

    fireEvent.click(screen.getByTestId('pin-click-inst-1'));

    expect(scrolledIds.at(-1)).toBe('instructor-card-inst-1');
    expect(screen.getByTestId('coverage-map')).toHaveAttribute('data-focus-id', 'inst-1');

    scrollSpy.mockRestore();
  });
});
