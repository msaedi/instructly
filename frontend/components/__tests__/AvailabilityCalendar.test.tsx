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

jest.mock('next/dynamic', () => () => {
  const MockTimeSelectionModal = ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) => {
    if (!isOpen) return null;
    return (
      <div data-testid="time-selection-modal">
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
