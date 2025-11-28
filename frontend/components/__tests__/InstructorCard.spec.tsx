import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import InstructorCard, { type InstructorAvailabilityData } from '@/components/InstructorCard';
import type { Instructor } from '@/types/api';

const pushMock = jest.fn();

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

jest.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({
    invalidateQueries: jest.fn(),
    setQueryData: jest.fn(),
  }),
}));

jest.mock('@/hooks/queries/useFavoriteStatus', () => ({
  useFavoriteStatus: () => ({ data: false, isLoading: false }),
  useSetFavoriteStatus: () => jest.fn(),
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => ({ user: null }),
}));

jest.mock('@/hooks/queries/useRatings', () => ({
  useSearchRatingQuery: () => ({ data: null }),
}));

jest.mock('@/src/api/services/reviews', () => ({
  useRecentReviews: () => ({ data: { reviews: [] }, isLoading: false }),
}));

jest.mock('@/services/api/favorites', () => ({
  favoritesApi: {
    check: jest.fn().mockResolvedValue({ is_favorited: false }),
    add: jest.fn().mockResolvedValue(undefined),
    remove: jest.fn().mockResolvedValue(undefined),
  },
}));

jest.mock('@/services/api/reviews', () => ({
  reviewsApi: {
    getRecent: jest.fn().mockResolvedValue({ reviews: [] }),
  },
}));

jest.mock('@/lib/api/pricing', () => ({
  fetchPricingPreview: jest.fn(),
  formatCentsToDisplay: jest.fn((amount: number) => `$${(amount / 100).toFixed(2)}`),
}));

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    getCatalogServices: jest.fn().mockResolvedValue({ data: [] }),
  },
  protectedApi: {},
}));

const buildInstructor = (): Instructor => ({
  id: 'instructor-profile-1',
  user_id: 'user-1',
  bio: 'Dedicated instructor',
  years_experience: 5,
  user: {
    first_name: 'Sarah',
    last_initial: 'C',
  },
  services: [
    {
      id: 'service-1',
      service_catalog_id: 'catalog-1',
      hourly_rate: 60,
      description: 'Lesson',
      duration_options: [30, 45, 60],
      is_active: true,
      skill: 'Piano',
    },
  ],
  service_area_summary: 'NYC',
  rating: 4.9,
  total_reviews: 12,
});

const buildAvailabilityData = (availability: InstructorAvailabilityData['availabilityByDate']): InstructorAvailabilityData => ({
  timezone: 'America/New_York',
  availabilityByDate: availability,
});

describe('InstructorCard next available booking', () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date('2024-05-08T12:00:00Z'));
    pushMock.mockClear();
    sessionStorage.clear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('uses the selected duration when booking the next available slot', async () => {
    render(
      <InstructorCard
        instructor={buildInstructor()}
        availabilityData={buildAvailabilityData({
          '2024-06-01': {
            available_slots: [{ start_time: '10:00', end_time: '11:00' }],
          },
        })}
      />
    );

    fireEvent.click(screen.getByLabelText(/60 min/));
    fireEvent.click(screen.getByRole('button', { name: /Next Available/ }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/student/booking/confirm'));

    const stored = sessionStorage.getItem('bookingData');
    expect(stored).toBeTruthy();
    const parsed = JSON.parse(stored as string);
    expect(parsed.duration).toBe(60);
    expect(parsed.endTime).toBe('11:00');
    expect(parsed.basePrice).toBe(60);
    expect(parsed.totalAmount).toBe(60);
  });
  it('updates the next available label when duration changes', async () => {
    render(
      <InstructorCard
        instructor={buildInstructor()}
        availabilityData={buildAvailabilityData({
          '2024-05-10': {
            available_slots: [{ start_time: '09:00', end_time: '09:30' }],
          },
          '2024-05-11': {
            available_slots: [{ start_time: '09:00', end_time: '10:30' }],
          },
        })}
      />
    );

    const button = screen.getByRole('button', { name: /Next Available/i });
    expect(button).toHaveTextContent(/Next Available: Fri, May 10/);

    fireEvent.click(screen.getByLabelText(/60 min/));

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /Next Available/i })
      ).toHaveTextContent(/Sat, May 11/);
    });
  });
});
