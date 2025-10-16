import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import TimeSelectionModal from '../TimeSelectionModal';
import { publicApi } from '@/features/shared/api/client';

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    getInstructorAvailability: jest.fn(),
  },
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

const availabilityMock = publicApi.getInstructorAvailability as jest.MockedFunction<typeof publicApi.getInstructorAvailability>;

const buildAvailabilityResponse = (
  availabilityByDate: Record<string, { available_slots: Array<{ start_time: string; end_time: string }> }>
): Awaited<ReturnType<typeof publicApi.getInstructorAvailability>> => {
  const entries = Object.entries(availabilityByDate).reduce<
    Record<
      string,
      {
        date: string;
        available_slots: Array<{ start_time: string; end_time: string }>;
        is_blackout: boolean;
      }
    >
  >((acc, [date, value]) => {
    acc[date] = {
      date,
      available_slots: value.available_slots,
      is_blackout: false,
    };
    return acc;
  }, {});

  const earliestDate = Object.keys(entries).sort()[0] ?? '';

  return {
    status: 200,
    data: {
      instructor_id: instructor.user_id,
      instructor_first_name: instructor.user.first_name,
      instructor_last_initial: instructor.user.last_initial,
      availability_by_date: entries,
      timezone: 'America/New_York',
      total_available_slots: Object.values(entries).reduce((total, day) => total + day.available_slots.length, 0),
      earliest_available_date: earliestDate,
    },
  };
};

const instructor = {
  user_id: 'inst-1',
  user: {
    first_name: 'Jordan',
    last_initial: 'M',
  },
  services: [
    {
      id: 'svc-1',
      duration_options: [30, 45, 60],
      hourly_rate: 120,
      skill: 'Math Tutoring',
      location_types: ['remote'],
    },
  ],
} as const;

const baseProps = {
  isOpen: true,
  onClose: jest.fn(),
  instructor,
  serviceId: 'svc-1',
  preSelectedDate: '2030-10-17',
};

describe('TimeSelectionModal duration changes', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    sessionStorage.clear();
  });

  it('keeps selected date when new duration has slots on that date', async () => {
    availabilityMock.mockResolvedValue(
      buildAvailabilityResponse({
        '2030-10-17': {
          available_slots: [{ start_time: '09:00', end_time: '11:00' }],
        },
        '2030-10-18': {
          available_slots: [{ start_time: '10:00', end_time: '12:00' }],
        },
      })
    );

    render(<TimeSelectionModal {...baseProps} />);

    await waitFor(() => expect(availabilityMock).toHaveBeenCalled());

    await screen.findAllByRole('button', { name: /9:00am/i });
    await screen.findAllByText(/October 17/i);

    fireEvent.click(screen.getAllByLabelText(/45 min/)[0]);

    await waitFor(() => expect(screen.getAllByRole('button', { name: /9:00am/i }).length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByText(/October 17/i).length).toBeGreaterThan(0));
    expect(screen.queryByText(/No 45-min slots/)).toBeNull();
  });

  it('shows notice and jump action when current date lacks availability for new duration', async () => {
    availabilityMock.mockResolvedValue(
      buildAvailabilityResponse({
        '2030-10-17': {
          available_slots: [{ start_time: '09:00', end_time: '09:30' }],
        },
        '2030-10-18': {
          available_slots: [{ start_time: '10:00', end_time: '11:30' }],
        },
      })
    );

    render(<TimeSelectionModal {...baseProps} />);

    await waitFor(() => expect(availabilityMock).toHaveBeenCalled());

    await screen.findAllByRole('button', { name: /9:00am/i });
    fireEvent.click(screen.getAllByLabelText(/60 min/)[0]);

    const notices = await screen.findAllByText(/No 60-min slots on Oct 17/i);
    expect(notices.length).toBeGreaterThan(0);

    await waitFor(() => expect(screen.getAllByRole('button', { name: /No times available for this date/i }).length).toBeGreaterThan(0));

    fireEvent.click(screen.getAllByRole('button', { name: /Jump to Oct 18/i })[0]);

    await waitFor(() => expect(screen.getAllByText(/October 18/i).length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByRole('button', { name: /10:00am/i }).length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.queryAllByText(/No 60-min slots/)).toHaveLength(0));
  });
});
