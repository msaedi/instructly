import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RescheduleModal } from '@/components/lessons/modals/RescheduleModal';
import { Booking } from '@/types/booking';
import { format } from 'date-fns';

// Mock the hooks
jest.mock('@/hooks/useMyLessons', () => ({
  useRescheduleLesson: jest.fn(() => ({
    mutate: jest.fn(),
    mutateAsync: jest.fn().mockResolvedValue({}),
    isPending: false,
  })),
}));

// Mock the queryFn from react-query api
jest.mock('@/lib/react-query/api', () => ({
  queryFn: () => () => {
    // Import format inside the mock
    const { format } = require('date-fns');

    // Generate dates for the next few days from today
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(today.getDate() + 1);
    const dayAfter = new Date(today);
    dayAfter.setDate(today.getDate() + 2);

    return Promise.resolve({
      available_slots: [
        {
          date: format(tomorrow, 'yyyy-MM-dd'),
          start_time: '10:00:00',
          end_time: '11:00:00',
        },
        {
          date: format(tomorrow, 'yyyy-MM-dd'),
          start_time: '14:00:00',
          end_time: '15:00:00',
        },
        {
          date: format(dayAfter, 'yyyy-MM-dd'),
          start_time: '09:00:00',
          end_time: '10:00:00',
        },
      ],
    });
  },
}));

const createTestQueryClient = () => {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
};

describe('RescheduleModal', () => {
  const mockBooking: Booking = {
    id: 1,
    booking_date: '2025-12-25',
    start_time: '14:00:00',
    end_time: '15:00:00',
    status: 'CONFIRMED',
    total_price: 60,
    hourly_rate: 60,
    duration_minutes: 60,
    instructor_id: 1,
    student_id: 1,
    service_id: 1,
    service_name: 'Mathematics',
    created_at: '2025-12-01T10:00:00Z',
    updated_at: '2025-12-01T10:00:00Z',
    instructor: {
      id: 1,
      full_name: 'John Doe',
      email: 'john@example.com',
      role: 'INSTRUCTOR',
      created_at: '2024-01-01T00:00:00Z',
    },
  };

  const mockOnClose = jest.fn();

  const renderWithProviders = (ui: React.ReactElement) => {
    const queryClient = createTestQueryClient();
    return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders modal when isOpen is true', () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    expect(screen.getByText('Need to reschedule?')).toBeInTheDocument();
    expect(screen.getByText(/Select a new time with John Doe/)).toBeInTheDocument();
  });

  it('does not render modal when isOpen is false', () => {
    renderWithProviders(
      <RescheduleModal isOpen={false} onClose={mockOnClose} lesson={mockBooking} />
    );

    expect(screen.queryByText('Need to reschedule?')).not.toBeInTheDocument();
  });

  it('calls onClose when cancel button is clicked', () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    const cancelButton = screen.getByRole('button', { name: /cancel/i });
    fireEvent.click(cancelButton);

    expect(mockOnClose).toHaveBeenCalledTimes(1);
  });

  it('shows calendar with available dates', async () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    // Check that calendar is displayed with current month
    await waitFor(() => {
      // The calendar shows the current month, not the booking month
      const currentMonth = format(new Date(), 'MMMM yyyy');
      expect(screen.getByText(currentMonth)).toBeInTheDocument();
    });

    // Check that day labels are shown
    expect(screen.getByText('Mo')).toBeInTheDocument();
    expect(screen.getByText('Tu')).toBeInTheDocument();
  });

  it('allows selecting a date', async () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    // Wait for calendar to load and find tomorrow's date
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowDay = format(tomorrow, 'd');

    await waitFor(() => {
      expect(screen.getByText(tomorrowDay)).toBeInTheDocument();
    });

    // Click on tomorrow's date (which has availability)
    const dateButton = screen.getByText(tomorrowDay);
    fireEvent.click(dateButton);

    // Should show available times for that date
    await waitFor(() => {
      expect(screen.getByText(/Available times on/)).toBeInTheDocument();
    });
  });

  it('allows selecting a time slot', async () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    // Select tomorrow's date first
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowDay = format(tomorrow, 'd');

    // Wait for calendar to load and click tomorrow's date
    const dateButton = await screen.findByText(tomorrowDay);
    fireEvent.click(dateButton);

    // Wait for "Available times" header to appear
    await waitFor(() => {
      expect(screen.getByText(/Available times on/)).toBeInTheDocument();
    });

    // Select a time slot - the component formats as "10:00 AM"
    const timeSlot = await screen.findByText('10:00 AM');
    fireEvent.click(timeSlot);

    // Confirm button should be enabled
    const confirmButton = screen.getByRole('button', { name: /confirm reschedule/i });
    expect(confirmButton).not.toBeDisabled();
  });

  it('disables confirm button when no time slot is selected', () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    const confirmButton = screen.getByRole('button', { name: /confirm reschedule/i });
    expect(confirmButton).toBeDisabled();
  });

  it('shows current booking date highlighted', () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    expect(screen.getByText(/Current lesson: .* Dec 25/)).toBeInTheDocument();
  });

  it('handles reschedule mutation', async () => {
    const mockMutateAsync = jest.fn().mockResolvedValue({});
    const useRescheduleLesson = require('@/hooks/useMyLessons').useRescheduleLesson;
    useRescheduleLesson.mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    });

    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    // Select tomorrow's date
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowDay = format(tomorrow, 'd');

    await waitFor(() => {
      const dateButton = screen.getByText(tomorrowDay);
      fireEvent.click(dateButton);
    });

    // Select a time slot
    await waitFor(() => {
      const timeSlot = screen.getByText('10:00 AM');
      fireEvent.click(timeSlot);
    });

    // Click confirm
    const confirmButton = screen.getByRole('button', { name: /confirm reschedule/i });
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        lessonId: 1,
        newDate: format(tomorrow, 'yyyy-MM-dd'),
        newStartTime: '10:00:00',
        newEndTime: '11:00:00',
      });
    });

    expect(mockOnClose).toHaveBeenCalled();
  });

  it('shows loading state during reschedule', () => {
    const { useRescheduleLesson } = require('@/hooks/useMyLessons');
    useRescheduleLesson.mockReturnValue({
      mutateAsync: jest.fn(),
      isPending: true,
    });

    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    // When loading, the confirm button should show "Rescheduling..."
    const confirmButton = screen.getByRole('button', { name: /confirm reschedule|rescheduling/i });
    expect(confirmButton).toHaveTextContent('Rescheduling...');
    expect(confirmButton).toBeDisabled();
  });

  it('shows chat to reschedule option', () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    expect(screen.getByText('Chat to reschedule')).toBeInTheDocument();
  });
});
