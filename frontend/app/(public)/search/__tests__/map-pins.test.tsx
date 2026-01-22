import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

import SearchResultsPage from '../page';

jest.mock('next/dynamic', () => () => {
  const MockCoverageMap = ({ locationPins }: { locationPins?: unknown[] }) => (
    <div data-testid="coverage-map" data-pins={JSON.stringify(locationPins ?? [])} />
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
};

describe('Search results map pins', () => {
  beforeAll(() => {
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
              last_initial: 'L',
              bio_snippet: '',
              profile_picture_url: '',
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
              price_per_hour: 60,
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
  });

  it('passes teaching location pins to the map', async () => {
    render(<SearchResultsPage />);

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
      });
    });
  });
});
