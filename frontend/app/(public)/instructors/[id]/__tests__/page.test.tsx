import React from 'react';
import { render, waitFor } from '@testing-library/react';

import InstructorProfilePage from '../page';

var mockWhereTheyTeach: jest.Mock;

jest.mock('@/components/instructor/WhereTheyTeach', () => {
  mockWhereTheyTeach = jest.fn((_props: unknown) => <div data-testid="where-they-teach" />);
  const MockWhereTheyTeach = (props: unknown) => mockWhereTheyTeach(props);
  MockWhereTheyTeach.displayName = 'MockWhereTheyTeach';
  return { WhereTheyTeach: MockWhereTheyTeach };
});

jest.mock('@/features/instructor-profile/hooks/useInstructorProfile', () => ({
  useInstructorProfile: jest.fn(),
}));

jest.mock('@/hooks/queries/useInstructorAvailability', () => ({
  useInstructorAvailability: jest.fn(() => ({ data: null })),
}));

jest.mock('@/features/instructor-profile/hooks/useBookingModal', () => ({
  useBookingModal: jest.fn(() => ({
    isOpen: false,
    selectedDate: null,
    selectedTime: null,
    openBookingModal: jest.fn(),
    closeBookingModal: jest.fn(),
  })),
}));

jest.mock('@/src/api/services/instructors', () => ({
  useInstructorCoverage: jest.fn(),
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(() => ({ isAuthenticated: false })),
}));

jest.mock('@/lib/config/backgroundProvider', () => ({
  useBackgroundConfig: jest.fn(() => ({ setActivity: jest.fn() })),
}));

jest.mock('@/lib/navigation/navigationStateManager', () => ({
  navigationStateManager: {
    getBookingFlow: jest.fn(() => null),
    clearBookingFlow: jest.fn(),
  },
}));

jest.mock('@/features/shared/utils/booking', () => ({
  storeBookingIntent: jest.fn(),
  getBookingIntent: jest.fn(() => null),
  clearBookingIntent: jest.fn(),
}));

jest.mock('@/features/instructor-profile/components/InstructorHeader', () => {
  const MockInstructorHeader = () => <div data-testid="instructor-header" />;
  MockInstructorHeader.displayName = 'MockInstructorHeader';
  return { InstructorHeader: MockInstructorHeader };
});

jest.mock('@/features/instructor-profile/components/ServiceCards', () => {
  const MockServiceCards = () => <div data-testid="service-cards" />;
  MockServiceCards.displayName = 'MockServiceCards';
  return { ServiceCards: MockServiceCards };
});

jest.mock('@/features/instructor-profile/components/ReviewsSection', () => {
  const MockReviewsSection = () => <div data-testid="reviews-section" />;
  MockReviewsSection.displayName = 'MockReviewsSection';
  return { ReviewsSection: MockReviewsSection };
});

jest.mock('@/features/instructor-profile/components/BookingButton', () => {
  const MockBookingButton = () => <div data-testid="booking-button" />;
  MockBookingButton.displayName = 'MockBookingButton';
  return { BookingButton: MockBookingButton };
});

jest.mock('@/features/instructor-profile/components/InstructorProfileSkeleton', () => {
  const MockInstructorProfileSkeleton = () => <div data-testid="profile-skeleton" />;
  MockInstructorProfileSkeleton.displayName = 'MockInstructorProfileSkeleton';
  return { InstructorProfileSkeleton: MockInstructorProfileSkeleton };
});

jest.mock('@/features/student/booking/components/TimeSelectionModal', () => {
  const MockTimeSelectionModal = () => <div data-testid="time-selection-modal" />;
  MockTimeSelectionModal.displayName = 'MockTimeSelectionModal';
  return { __esModule: true, default: MockTimeSelectionModal };
});

jest.mock('@/components/UserProfileDropdown', () => {
  const MockUserProfileDropdown = () => <div data-testid="user-profile-dropdown" />;
  MockUserProfileDropdown.displayName = 'MockUserProfileDropdown';
  return { __esModule: true, default: MockUserProfileDropdown };
});

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
  })),
  usePathname: jest.fn(() => '/instructors/inst-1'),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  useParams: jest.fn(() => ({ id: 'inst-1' })),
}));

const mockUseInstructorProfile = jest.requireMock(
  '@/features/instructor-profile/hooks/useInstructorProfile'
).useInstructorProfile as jest.Mock;

const mockUseInstructorCoverage = jest.requireMock(
  '@/src/api/services/instructors'
).useInstructorCoverage as jest.Mock;

describe('InstructorProfilePage', () => {
  beforeEach(() => {
    mockWhereTheyTeach.mockClear();

    mockUseInstructorProfile.mockReturnValue({
      data: {
        user_id: 'inst-1',
        user: { first_name: 'Ava', last_initial: 'L' },
        services: [
          {
            id: 'svc-1',
            service_catalog_id: 'cat-1',
            service_catalog_name: 'Piano',
            hourly_rate: 60,
            offers_travel: true,
            offers_at_location: true,
            offers_online: false,
          },
        ],
        preferred_teaching_locations: [
          {
            approx_lat: 40.7128,
            approx_lng: -74.006,
            neighborhood: 'Lower East Side, Manhattan',
            label: 'Studio',
          },
        ],
        services_count: 1,
      },
      isLoading: false,
      error: null,
      refetch: jest.fn(),
      isFetching: false,
    });

    mockUseInstructorCoverage.mockReturnValue({
      data: { type: 'FeatureCollection', features: [] },
    });
  });

  it('passes coverage and studio pins to WhereTheyTeach', async () => {
    render(<InstructorProfilePage />);

    await waitFor(() => {
      expect(mockWhereTheyTeach).toHaveBeenCalled();
    });

    const firstCall = mockWhereTheyTeach.mock.calls.at(0);
    if (!firstCall) {
      throw new Error('WhereTheyTeach was not called');
    }
    const props = firstCall[0] as {
      offersTravel: boolean;
      offersAtLocation: boolean;
      offersOnline: boolean;
      coverage: unknown;
      studioPins: Array<{ lat: number; lng: number; label?: string }>;
    };

    expect(props.offersTravel).toBe(true);
    expect(props.offersAtLocation).toBe(true);
    expect(props.offersOnline).toBe(false);
    expect(props.coverage).toEqual({ type: 'FeatureCollection', features: [] });
    expect(props.studioPins).toEqual([
      { lat: 40.7128, lng: -74.006, label: 'Lower East Side, Manhattan' },
    ]);
  });
});
