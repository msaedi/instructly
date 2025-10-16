import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import TimeSelectionModal from '../TimeSelectionModal';
import { publicApi } from '@/features/shared/api/client';

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingFloors: () => ({ floors: {} }),
}));

jest.mock('@/features/student/booking/hooks/useAuth', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    redirectToLogin: jest.fn(),
    user: { timezone: 'America/New_York' },
  }),
  storeBookingIntent: jest.fn(),
}));

jest.mock('@/lib/api/pricing', () => ({
  fetchPricingPreview: jest.fn(),
  fetchPricingPreviewQuote: jest.fn(),
}));

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    getInstructorAvailability: jest.fn(),
  },
}));

const availabilityMock = publicApi.getInstructorAvailability as jest.MockedFunction<
  typeof publicApi.getInstructorAvailability
>;

describe('TimeSelectionModal preselected initialization', () => {
  beforeAll(() => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2030-10-10T12:00:00Z'));
  });

  afterAll(() => {
    jest.useRealTimers();
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('preselects initial date/time/duration when provided', async () => {
    availabilityMock.mockResolvedValue({
      status: 200,
      data: {
        instructor_id: 'inst-1',
        instructor_first_name: 'Jordan',
        instructor_last_initial: 'M',
        timezone: 'America/New_York',
        total_available_slots: 2,
        earliest_available_date: '2030-10-18',
        availability_by_date: {
          '2030-10-18': {
            date: '2030-10-18',
            is_blackout: false,
            available_slots: [
              { start_time: '14:00', end_time: '15:00' },
              { start_time: '16:00', end_time: '17:00' },
            ],
          },
        },
      },
    });

    render(
      <TimeSelectionModal
        isOpen
        onClose={jest.fn()}
        instructor={{
          user_id: 'inst-1',
          user: { first_name: 'Jordan', last_initial: 'M' },
          services: [
            {
              id: 'svc-1',
              duration_options: [30, 60, 90],
              hourly_rate: 120,
              skill: 'Math Tutoring',
              location_types: ['remote'],
            },
          ],
        }}
        serviceId="svc-1"
        initialDate="2030-10-18"
        initialTimeHHMM24="14:00"
        initialDurationMinutes={60}
      />
    );

    await waitFor(() => expect(availabilityMock).toHaveBeenCalled());

    const durationRadio = screen.getAllByRole('radio', { name: /60 min/i })[0] as HTMLInputElement;
    expect(durationRadio.checked).toBe(true);

    const timeButtons = await screen.findAllByRole('button', { name: /2:00pm/i });
    expect(timeButtons.length).toBeGreaterThan(0);

    const selectedDayButtons = await screen.findAllByRole('button', {
      name: '18',
      pressed: true,
    });
    expect(selectedDayButtons.length).toBeGreaterThan(0);
  });
});
