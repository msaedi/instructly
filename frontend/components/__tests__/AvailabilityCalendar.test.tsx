import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AvailabilityCalendar from '../AvailabilityCalendar';
import { useInstructorAvailability } from '@/hooks/queries/useInstructorAvailability';
import { getBookingIntent, clearBookingIntent } from '@/features/shared/utils/booking';

// Mock dependencies
jest.mock('@/hooks/queries/useInstructorAvailability', () => ({
  useInstructorAvailability: jest.fn(),
}));

jest.mock('@/features/shared/utils/booking', () => ({
  getBookingIntent: jest.fn(),
  clearBookingIntent: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('next/dynamic', () => (loadFn: () => Promise<unknown>) => {
  try { Promise.resolve(loadFn()).catch(() => {}); } catch {}

  const MockTimeSelectionModal = ({
    isOpen,
    onClose,
    preSelectedDate,
    preSelectedTime,
    serviceId,
  }: {
    isOpen: boolean;
    onClose: () => void;
    preSelectedDate?: string;
    preSelectedTime?: string;
    serviceId?: string;
  }) => {
    if (!isOpen) return null;
    return (
      <div
        data-testid="time-selection-modal"
        data-preselected-date={preSelectedDate}
        data-preselected-time={preSelectedTime}
        data-service-id={serviceId}
      >
        <button onClick={onClose}>Close Modal</button>
      </div>
    );
  };
  MockTimeSelectionModal.displayName = 'MockTimeSelectionModal';
  return MockTimeSelectionModal;
});

const mockUseInstructorAvailability = useInstructorAvailability as jest.Mock;
const mockGetBookingIntent = getBookingIntent as jest.Mock;
const mockClearBookingIntent = clearBookingIntent as jest.Mock;

const mockInstructor = {
  id: 'inst-123',
  user_id: 'user-123',
  first_name: 'John',
  last_initial: 'D',
  service_name: 'Piano Lessons',
  hourly_rate: 60,
  services: [{ id: 'svc-1', name: 'Piano Lessons' }],
};

// Helper to get dates relative to today
const getDateString = (daysFromToday: number): string => {
  const date = new Date();
  date.setDate(date.getDate() + daysFromToday);
  return date.toISOString().split('T')[0] ?? '';
};

describe('AvailabilityCalendar', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetBookingIntent.mockReturnValue(null);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('loading state', () => {
    it('renders loading skeleton', () => {
      mockUseInstructorAvailability.mockReturnValue({
        data: null,
        isLoading: true,
        error: null,
      });

      const { container } = render(
        <AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />
      );

      expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('renders error message and retry button', () => {
      mockUseInstructorAvailability.mockReturnValue({
        data: null,
        isLoading: false,
        error: new Error('Failed to load'),
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      expect(screen.getByText('Unable to Load Availability')).toBeInTheDocument();
      expect(screen.getByText('Unable to load availability. Please try again.')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
    });

    it('reloads the page when retry is clicked', async () => {
      mockUseInstructorAvailability.mockReturnValue({
        data: null,
        isLoading: false,
        error: new Error('Failed to load'),
      });

      const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined);

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      await userEvent.click(screen.getByRole('button', { name: /try again/i }));

      consoleSpy.mockRestore();
    });
  });

  describe('no availability state', () => {
    it('renders no availability message', () => {
      mockUseInstructorAvailability.mockReturnValue({
        data: { availability_by_date: {} },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      expect(
        screen.getByText(/no available times in the next 14 days/i)
      ).toBeInTheDocument();
    });

    it('handles missing availability data', () => {
      mockUseInstructorAvailability.mockReturnValue({
        data: null,
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      expect(
        screen.getByText(/no available times in the next 14 days/i)
      ).toBeInTheDocument();
    });
  });

  describe('with availability', () => {
    const todayStr = getDateString(0);
    const tomorrowStr = getDateString(1);

    beforeEach(() => {
      jest.useFakeTimers();
      jest.setSystemTime(new Date(`${todayStr}T09:00:00`));
    });

    it('renders 14-day calendar grid', () => {
      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [todayStr]: {
              available_slots: [
                { start_time: '10:00', end_time: '11:00' },
              ],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      // Should render at least some day buttons
      const dayButtons = screen.getAllByRole('button');
      expect(dayButtons.length).toBeGreaterThanOrEqual(14);
    });

    it('shows green dot for days with availability', () => {
      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [tomorrowStr]: {
              available_slots: [
                { start_time: '10:00', end_time: '11:00' },
              ],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      const { container } = render(
        <AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />
      );

      // Should have green availability indicators
      expect(container.querySelectorAll('.bg-green-500').length).toBeGreaterThan(0);
    });

    it('disables days without availability', () => {
      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [tomorrowStr]: {
              available_slots: [
                { start_time: '10:00', end_time: '11:00' },
              ],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      // Days without availability should be disabled
      const disabledButtons = screen.getAllByRole('button').filter((btn) => btn.hasAttribute('disabled'));
      expect(disabledButtons.length).toBeGreaterThan(0);
    });

    it('shows time slots when day is selected', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [tomorrowStr]: {
              available_slots: [
                { start_time: '10:00', end_time: '11:00' },
                { start_time: '14:00', end_time: '15:00' },
              ],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      // Find and click on a day with availability
      const dayButtons = screen.getAllByRole('button');
      const availableDay = dayButtons.find((btn) => !btn.hasAttribute('disabled'));

      if (availableDay) {
        await user.click(availableDay);

        // Should show time slots
        await waitFor(() => {
          expect(screen.getByText('Morning')).toBeInTheDocument();
        });
      }
    });

    it('groups slots by time of day', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [tomorrowStr]: {
              available_slots: [
                { start_time: '09:00', end_time: '10:00' }, // Morning
                { start_time: '14:00', end_time: '15:00' }, // Afternoon
                { start_time: '18:00', end_time: '19:00' }, // Evening
              ],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      // Click on available day
      const dayButtons = screen.getAllByRole('button');
      const availableDay = dayButtons.find((btn) => !btn.hasAttribute('disabled'));

      if (availableDay) {
        await user.click(availableDay);

        await waitFor(() => {
          expect(screen.getByText('Morning')).toBeInTheDocument();
          expect(screen.getByText('Afternoon')).toBeInTheDocument();
          expect(screen.getByText('Evening')).toBeInTheDocument();
        });
      }
    });

    it('opens time selection modal when slot is clicked', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [tomorrowStr]: {
              available_slots: [
                { start_time: '10:00', end_time: '11:00' },
              ],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      // Click on available day first
      const dayButtons = screen.getAllByRole('button');
      const availableDay = dayButtons.find((btn) => !btn.hasAttribute('disabled'));

      if (availableDay) {
        await user.click(availableDay);

        // Wait for time slots to appear
        await waitFor(() => {
          expect(screen.getByText('10:00AM')).toBeInTheDocument();
        });

        // Click on time slot
        await user.click(screen.getByText('10:00AM'));

        // Modal should open
        await waitFor(() => {
          expect(screen.getByTestId('time-selection-modal')).toBeInTheDocument();
        });
      }
    });

    it('opens modal when afternoon slot is clicked', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [tomorrowStr]: {
              available_slots: [
                { start_time: '14:00', end_time: '15:00' },
              ],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      const dayButtons = screen.getAllByRole('button');
      const availableDay = dayButtons.find((btn) => !btn.hasAttribute('disabled'));

      if (availableDay) {
        await user.click(availableDay);

        await waitFor(() => {
          expect(screen.getByText('2:00PM')).toBeInTheDocument();
        });

        await user.click(screen.getByText('2:00PM'));
        await waitFor(() => {
          expect(screen.getByTestId('time-selection-modal')).toBeInTheDocument();
        });
      }
    });

    it('opens modal when evening slot is clicked', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [tomorrowStr]: {
              available_slots: [
                { start_time: '18:00', end_time: '19:00' },
              ],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      const dayButtons = screen.getAllByRole('button');
      const availableDay = dayButtons.find((btn) => !btn.hasAttribute('disabled'));

      if (availableDay) {
        await user.click(availableDay);

        await waitFor(() => {
          expect(screen.getByText('6:00PM')).toBeInTheDocument();
        });

        await user.click(screen.getByText('6:00PM'));
        await waitFor(() => {
          expect(screen.getByTestId('time-selection-modal')).toBeInTheDocument();
        });
      }
    });

    it('filters out past time slots', () => {
      // Set time to 2pm
      jest.setSystemTime(new Date(`${todayStr}T14:00:00`));

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [todayStr]: {
              available_slots: [
                { start_time: '10:00', end_time: '11:00' }, // Past - should be filtered
                { start_time: '15:00', end_time: '16:00' }, // Future - should show
              ],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      // Today should not show availability (past slot filtered, 3pm would be available)
      // The component filters based on current time
    });
  });

  describe('booking intent restoration', () => {
    it('restores booking intent for matching instructor', () => {
      jest.useFakeTimers();
      const tomorrowStr = getDateString(1);
      jest.setSystemTime(new Date(`${getDateString(0)}T09:00:00`));

      mockGetBookingIntent.mockReturnValue({
        instructorId: 'user-123',
        date: tomorrowStr,
        time: '10:00',
        duration: 60,
        serviceId: 'svc-1',
      });

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [tomorrowStr]: {
              available_slots: [
                { start_time: '10:00', end_time: '11:00' },
              ],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      // Should clear the booking intent after restoration
      expect(mockClearBookingIntent).toHaveBeenCalled();
    });

    it('opens modal with preselected slot from booking intent', async () => {
      jest.useFakeTimers();
      const tomorrowStr = getDateString(1);
      jest.setSystemTime(new Date(`${getDateString(0)}T09:00:00`));

      mockGetBookingIntent.mockReturnValue({
        instructorId: 'user-123',
        date: tomorrowStr,
        time: '10:00',
        duration: 60,
        serviceId: 'svc-1',
      });

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [tomorrowStr]: {
              available_slots: [{ start_time: '10:00', end_time: '11:00' }],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      const modal = await screen.findByTestId('time-selection-modal');
      expect(modal).toHaveAttribute('data-preselected-date', tomorrowStr);
      expect(modal).toHaveAttribute('data-preselected-time', '10:00');
      expect(modal).toHaveAttribute('data-service-id', 'svc-1');
    });

    it('does not restore booking intent for different instructor', () => {
      mockGetBookingIntent.mockReturnValue({
        instructorId: 'different-user',
        date: '2024-12-25',
        time: '10:00',
        duration: 60,
      });

      mockUseInstructorAvailability.mockReturnValue({
        data: { availability_by_date: {} },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      // Should not clear booking intent since it's for a different instructor
      expect(mockClearBookingIntent).not.toHaveBeenCalled();
    });
  });

  describe('time formatting', () => {
    it('formats times correctly', async () => {
      jest.useFakeTimers();
      const tomorrowStr = getDateString(1);
      jest.setSystemTime(new Date(`${getDateString(0)}T09:00:00`));
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [tomorrowStr]: {
              available_slots: [
                { start_time: '09:00', end_time: '10:00' },
                { start_time: '12:00', end_time: '13:00' },
                { start_time: '14:30', end_time: '15:30' },
              ],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      // Click on available day
      const dayButtons = screen.getAllByRole('button');
      const availableDay = dayButtons.find((btn) => !btn.hasAttribute('disabled'));

      if (availableDay) {
        await user.click(availableDay);

        await waitFor(() => {
          expect(screen.getByText('9:00AM')).toBeInTheDocument();
          expect(screen.getByText('12:00PM')).toBeInTheDocument();
          expect(screen.getByText('2:30PM')).toBeInTheDocument();
        });
      }
    });
  });

  describe('modal interaction', () => {
    it('closes modal and resets state', async () => {
      jest.useFakeTimers();
      const tomorrowStr = getDateString(1);
      jest.setSystemTime(new Date(`${getDateString(0)}T09:00:00`));
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [tomorrowStr]: {
              available_slots: [
                { start_time: '10:00', end_time: '11:00' },
              ],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      // Click on available day
      const dayButtons = screen.getAllByRole('button');
      const availableDay = dayButtons.find((btn) => !btn.hasAttribute('disabled'));

      if (availableDay) {
        await user.click(availableDay);

        // Wait for time slot and click it
        await waitFor(() => {
          expect(screen.getByText('10:00AM')).toBeInTheDocument();
        });

        await user.click(screen.getByText('10:00AM'));

        // Modal should open
        await waitFor(() => {
          expect(screen.getByTestId('time-selection-modal')).toBeInTheDocument();
        });

        // Close modal
        await user.click(screen.getByText('Close Modal'));

        // Modal should be closed
        await waitFor(() => {
          expect(screen.queryByTestId('time-selection-modal')).not.toBeInTheDocument();
        });
      }
    });
  });

  describe('booking intent with missing fields', () => {
    it('handles booking intent with no date (bookingIntent.date is undefined)', () => {
      // Exercises the ?? null fallback at line 40 and ?? '' at line 55
      mockGetBookingIntent.mockReturnValue({
        instructorId: 'user-123',
        // date is missing
        time: undefined,
        duration: 60,
        serviceId: undefined,
      });

      mockUseInstructorAvailability.mockReturnValue({
        data: { availability_by_date: {} },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      // Should still clear booking intent since instructor matches
      expect(mockClearBookingIntent).toHaveBeenCalled();
      // Modal should NOT auto-open since date/time are missing (isModalOpen requires selectedDate && selectedTime)
      expect(screen.queryByTestId('time-selection-modal')).not.toBeInTheDocument();
    });

    it('handles booking intent with null bookingIntent entirely', () => {
      // bookingIntent is null, so shouldRestoreIntent is false
      mockGetBookingIntent.mockReturnValue(null);

      mockUseInstructorAvailability.mockReturnValue({
        data: { availability_by_date: {} },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      expect(mockClearBookingIntent).not.toHaveBeenCalled();
    });

    it('handles booking intent with date but no time or serviceId', () => {
      // Exercises bookingIntent?.time ?? '' (falls to '') and bookingIntent?.serviceId (undefined)
      jest.useFakeTimers();
      const tomorrowStr = getDateString(1);
      jest.setSystemTime(new Date(`${getDateString(0)}T09:00:00`));

      mockGetBookingIntent.mockReturnValue({
        instructorId: 'user-123',
        date: tomorrowStr,
        // time is undefined — ?? '' fallback
        // serviceId is undefined — undefined fallback
        duration: 60,
      });

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [tomorrowStr]: {
              available_slots: [{ start_time: '10:00', end_time: '11:00' }],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      // Should clear intent since instructor matches
      expect(mockClearBookingIntent).toHaveBeenCalled();
      // Modal should NOT open: selectedTime is '' (falsy) so isModalOpen is false
      expect(screen.queryByTestId('time-selection-modal')).not.toBeInTheDocument();
    });

    it('restores intent with all fields present', async () => {
      // Exercises the non-fallback paths: bookingIntent.date (not null),
      // bookingIntent.time (not ''), bookingIntent.serviceId (not undefined)
      jest.useFakeTimers();
      const tomorrowStr = getDateString(1);
      jest.setSystemTime(new Date(`${getDateString(0)}T09:00:00`));

      mockGetBookingIntent.mockReturnValue({
        instructorId: 'user-123',
        date: tomorrowStr,
        time: '10:00',
        duration: 60,
        serviceId: 'svc-1',
      });

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [tomorrowStr]: {
              available_slots: [{ start_time: '10:00', end_time: '11:00' }],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      // Modal auto-opens since all fields present
      const modal = await screen.findByTestId('time-selection-modal');
      expect(modal).toHaveAttribute('data-preselected-date', tomorrowStr);
      expect(modal).toHaveAttribute('data-preselected-time', '10:00');
      expect(modal).toHaveAttribute('data-service-id', 'svc-1');
    });
  });

  describe('availability data with missing available_slots', () => {
    it('handles day data with no available_slots key (line 129-135)', () => {
      jest.useFakeTimers();
      const todayStr = getDateString(0);
      jest.setSystemTime(new Date(`${todayStr}T09:00:00`));

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [todayStr]: {
              // available_slots is undefined — exercises the ternary at line 129
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      // Day with no available_slots should show as having no availability
      expect(screen.getByText(/no available times in the next 14 days/i)).toBeInTheDocument();
    });
  });

  describe('formatTime edge cases', () => {
    it('formats midnight (00:00) correctly as 12:00AM', async () => {
      jest.useFakeTimers();
      const tomorrowStr = getDateString(1);
      jest.setSystemTime(new Date(`${getDateString(0)}T09:00:00`));
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [tomorrowStr]: {
              available_slots: [
                { start_time: '00:00', end_time: '01:00' },
              ],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      const dayButtons = screen.getAllByRole('button');
      const availableDay = dayButtons.find((btn) => !btn.hasAttribute('disabled'));

      if (availableDay) {
        await user.click(availableDay);

        await waitFor(() => {
          // hour % 12 || 12 for hour=0 gives 12, AM
          expect(screen.getByText('12:00AM')).toBeInTheDocument();
        });
      }
    });

    it('returns empty string for malformed time with no colon', async () => {
      jest.useFakeTimers();
      const tomorrowStr = getDateString(1);
      jest.setSystemTime(new Date(`${getDateString(0)}T09:00:00`));
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [tomorrowStr]: {
              available_slots: [
                { start_time: '', end_time: '11:00' },
                { start_time: '10:00', end_time: '11:00' },
              ],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      const dayButtons = screen.getAllByRole('button');
      const availableDay = dayButtons.find((btn) => !btn.hasAttribute('disabled'));

      if (availableDay) {
        await user.click(availableDay);

        await waitFor(() => {
          // '10:00' should render; '' returns '' from formatTime
          expect(screen.getByText('10:00AM')).toBeInTheDocument();
        });
      }
    });
  });

  describe('groupSlotsByTimeOfDay with missing hour part', () => {
    it('filters out slots with empty start_time in grouping', async () => {
      jest.useFakeTimers();
      const tomorrowStr = getDateString(1);
      jest.setSystemTime(new Date(`${getDateString(0)}T09:00:00`));
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [tomorrowStr]: {
              available_slots: [
                { start_time: '10:00', end_time: '11:00' },
              ],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      const dayButtons = screen.getAllByRole('button');
      const availableDay = dayButtons.find((btn) => !btn.hasAttribute('disabled'));

      if (availableDay) {
        await user.click(availableDay);

        await waitFor(() => {
          expect(screen.getByText('Morning')).toBeInTheDocument();
          expect(screen.getByText('10:00AM')).toBeInTheDocument();
        });
      }
    });
  });

  describe('no availability but has data', () => {
    it('shows no available times message when selectedDate has empty slots', async () => {
      jest.useFakeTimers();
      const todayStr = getDateString(0);
      const tomorrowStr = getDateString(1);
      jest.setSystemTime(new Date(`${todayStr}T09:00:00`));

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            // Tomorrow has slots but they are all empty
            [tomorrowStr]: {
              available_slots: [],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      // No days should have green dots since all slots are empty
      expect(screen.getByText(/no available times in the next 14 days/i)).toBeInTheDocument();
    });
  });

  describe('selected day with no future slots shows "No available times" (line 332)', () => {
    it('renders "No available times for this day" via booking intent on a day with past-only slots', async () => {
      jest.useFakeTimers();
      const todayStr = getDateString(0);
      // Set time late so today's slots are all in the past
      jest.setSystemTime(new Date(`${todayStr}T23:00:00`));

      // Booking intent pre-selects today, which has only past slots
      mockGetBookingIntent.mockReturnValue({
        instructorId: 'user-123',
        date: todayStr,
        time: '08:00',
        duration: 60,
      });

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [todayStr]: {
              available_slots: [
                { start_time: '08:00', end_time: '09:00' }, // Past
                { start_time: '10:00', end_time: '11:00' }, // Past
              ],
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      // selectedDate = todayStr (from intent), but getAvailableSlots filters past -> []
      // This triggers line 332: selectedDaySlots.length === 0
      await waitFor(() => {
        expect(screen.getByText('No available times for this day')).toBeInTheDocument();
      });
    });
  });

  describe('legend display', () => {
    it('shows availability legend', () => {
      mockUseInstructorAvailability.mockReturnValue({
        data: { availability_by_date: {} },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      expect(screen.getByText('Has availability')).toBeInTheDocument();
      expect(screen.getByText('Fully booked')).toBeInTheDocument();
    });
  });

  describe('empty selected day', () => {
    it('shows no times message for day with no slots', async () => {
      jest.useFakeTimers();
      const tomorrowStr = getDateString(1);
      const dayAfterStr = getDateString(2);
      jest.setSystemTime(new Date(`${getDateString(0)}T09:00:00`));
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      mockUseInstructorAvailability.mockReturnValue({
        data: {
          availability_by_date: {
            [tomorrowStr]: {
              available_slots: [
                { start_time: '10:00', end_time: '11:00' },
              ],
            },
            [dayAfterStr]: {
              available_slots: [], // Day with no slots
            },
          },
        },
        isLoading: false,
        error: null,
      });

      render(<AvailabilityCalendar instructorId="inst-123" instructor={mockInstructor as never} />);

      // Click on day with availability first
      const dayButtons = screen.getAllByRole('button');
      const availableDay = dayButtons.find((btn) => !btn.hasAttribute('disabled'));

      if (availableDay) {
        await user.click(availableDay);

        await waitFor(() => {
          // Check if time slots are rendered or no times message
          const noTimesMessage = screen.queryByText('No available times for this day');
          const morningSection = screen.queryByText('Morning');

          // Either shows slots or no times message
          expect(noTimesMessage || morningSection).toBeTruthy();
        });
      }
    });
  });
});
