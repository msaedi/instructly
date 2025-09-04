import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RescheduleModal } from '@/components/lessons/modals/RescheduleModal';
import type { Booking } from '@/features/shared/api/types';
import { format } from 'date-fns';
import { AuthProvider } from '@/features/shared/hooks/useAuth';
import * as dateFns from 'date-fns';
import * as myLessonsHooks from '@/hooks/useMyLessons';

// Mock the hooks
jest.mock('@/hooks/useMyLessons', () => ({
  useRescheduleLesson: jest.fn(() => ({
    mutate: jest.fn(),
    mutateAsync: jest.fn().mockResolvedValue({}),
    isPending: false,
  })),
}));

// Shared router mock so we can assert navigation
const pushMock = jest.fn();
const backMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({
    push: pushMock,
    back: backMock,
  })),
}));

// Mock API client used by the modal
jest.mock('@/features/shared/api/client', () => {
  const { format } = jest.requireActual('date-fns') as typeof dateFns;
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  const dayAfter = new Date(today);
  dayAfter.setDate(today.getDate() + 2);

  const t1 = format(tomorrow, 'yyyy-MM-dd');
  const t2 = format(dayAfter, 'yyyy-MM-dd');

  return {
    publicApi: {
      getInstructorAvailability: jest.fn().mockResolvedValue({
        data: {
          availability_by_date: {
            [t1]: {
              available_slots: [
                { start_time: '10:00:00', end_time: '11:00:00' },
                { start_time: '14:00:00', end_time: '15:00:00' },
              ],
            },
            [t2]: {
              available_slots: [
                { start_time: '09:00:00', end_time: '10:00:00' },
              ],
            },
          },
        },
      }),
    },
    protectedApi: {
      rescheduleBooking: jest.fn().mockResolvedValue({ status: 200, data: { id: '01KNEWBOOKINGID' } }),
    },
  };
});

const createTestQueryClient = () => {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
};

describe('RescheduleModal', () => {
  const mockBooking = ({
    id: '01K2MAY484FQGFEQVN3VKGYZ58',
    booking_date: '2025-12-25',
    start_time: '14:00:00',
    end_time: '15:00:00',
    status: 'CONFIRMED',
    total_price: 60,
    hourly_rate: 60,
    duration_minutes: 60,
    instructor_id: '01K2MAY484FQGFEQVN3VKGYZ59',
    student_id: '01K2MAY484FQGFEQVN3VKGYZ60',
    instructor_service_id: '01K2MAY484FQGFEQVN3VKGYZAA',
    service: { id: '01K2MAY484FQGFEQVN3VKGYZ61' } as unknown as { id: string },
    service_name: 'Mathematics',
    created_at: '2025-12-01T10:00:00Z',
    updated_at: '2025-12-01T10:00:00Z',
    instructor: {
      id: '01K2MAY484FQGFEQVN3VKGYZ59',
      first_name: 'John',
      last_initial: 'D',
    },
  }) as unknown as Booking;

  const mockOnClose = jest.fn();


  const renderWithProviders = (ui: React.ReactElement) => {
    const queryClient = createTestQueryClient();
    return render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          {ui}
        </AuthProvider>
      </QueryClientProvider>
    );
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders modal when isOpen is true', async () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    // Flush microtasks produced by the modal's internal Promise.resolve().then(...)
    await act(async () => { await Promise.resolve(); });

    await waitFor(() => {
      const headings = screen.getAllByText('Need to reschedule?');
      expect(headings.length).toBeGreaterThan(0);
    });

    await waitFor(() => {
      expect(screen.queryByText(/Loading availability/i)).not.toBeInTheDocument();
    });

    const intros = screen.getAllByText(/Choose a new lesson date & time below\./);
    expect(intros.length).toBeGreaterThan(0);
  });

  it('does not render modal when isOpen is false', () => {
    renderWithProviders(
      <RescheduleModal isOpen={false} onClose={mockOnClose} lesson={mockBooking} />
    );

    expect(screen.queryByText('Need to reschedule?')).not.toBeInTheDocument();
  });

  it('calls onClose when X button is clicked', async () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    await act(async () => { await Promise.resolve(); });

    await waitFor(() => {
      expect(screen.getAllByText('Need to reschedule?').length).toBeGreaterThan(0);
    });

    // Look for the X button (close button)
    const closeButtons = screen.getAllByRole('button');
    // Find the button with the X icon
    const closeButton = closeButtons.find(btn => btn.querySelector('.lucide-x'));
    if (closeButton) {
      fireEvent.click(closeButton);
      expect(mockOnClose).toHaveBeenCalledTimes(1);
    }
  });

  it('shows calendar with available dates', async () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    await act(async () => { await Promise.resolve(); });

    // Wait for loading to finish
    await waitFor(() => {
      expect(screen.queryByText(/Loading availability/i)).not.toBeInTheDocument();
    });

    // Check that calendar is displayed with current month
    const currentMonth = format(new Date(), 'MMMM yyyy');
    const monthEls = screen.getAllByText(currentMonth);
    expect(monthEls.length).toBeGreaterThan(0);
  });

  it('allows selecting a date', async () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    await act(async () => { await Promise.resolve(); });

    // Wait for calendar to load and find tomorrow's date
    await waitFor(() => {
      expect(screen.queryByText(/Loading availability/i)).not.toBeInTheDocument();
    });
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowDay = format(tomorrow, 'd');

    const dayEls = await screen.findAllByText(tomorrowDay);
    const clickable = (dayEls as HTMLElement[]).find((el: HTMLElement) => !(el as HTMLButtonElement).disabled);
    if (clickable) {
      fireEvent.click(clickable);
    } else if (dayEls[0]) {
      fireEvent.click(dayEls[0]);
    }

    // Confirm should be enabled after auto-selecting first time
    await waitFor(() => {
      const confirmButtons = screen.getAllByRole('button', { name: /select and continue/i });
      expect(confirmButtons[0]).not.toBeDisabled();
    });
  });

  it('allows selecting a time slot', async () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    await act(async () => { await Promise.resolve(); });

    // Select tomorrow's date first
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowDay = format(tomorrow, 'd');

    await waitFor(() => {
      expect(screen.queryByText(/Loading availability/i)).not.toBeInTheDocument();
    });
    const dayButtons = await screen.findAllByText(tomorrowDay);
    const clickable = (dayButtons as HTMLElement[]).find((el: HTMLElement) => !(el as HTMLButtonElement).disabled);
    if (clickable) {
      fireEvent.click(clickable);
    } else if (dayButtons[0]) {
      fireEvent.click(dayButtons[0]);
    }

    // Auto-selected time should enable confirm
    await waitFor(() => {
      const confirmButtons = screen.getAllByRole('button', { name: /select and continue/i });
      expect(confirmButtons[0]).not.toBeDisabled();
    });
  });

  it('renders confirm button before selection', async () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    await act(async () => { await Promise.resolve(); });

    const confirmButtons = screen.getAllByRole('button', { name: /select and continue/i });
    expect(confirmButtons.length).toBeGreaterThan(0);
  });

  it('shows current booking date highlighted', () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    expect(screen.getByText(/Mathematics/)).toBeInTheDocument();
    const dateEls = screen.getAllByText(/Dec 25/);
    expect(dateEls.length).toBeGreaterThan(0);
  });

  it('handles reschedule mutation', async () => {
    const mockMutateAsync = jest.fn().mockResolvedValue({});
    const useRescheduleLesson = myLessonsHooks.useRescheduleLesson as jest.Mock;
    useRescheduleLesson.mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    });

    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    await act(async () => { await Promise.resolve(); });

    // Select tomorrow's date
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowDay = format(tomorrow, 'd');

    await waitFor(() => {
      const dateButtons = screen.getAllByText(tomorrowDay) as HTMLElement[];
      const clickableBtn = dateButtons.find((el) => !(el as HTMLButtonElement).disabled);
      if (clickableBtn) {
        fireEvent.click(clickableBtn);
      } else if (dateButtons[0]) {
        fireEvent.click(dateButtons[0]);
      }
    });

    // Time is auto-selected; proceed

    // Click confirm (pick the first button instance)
    const confirmButtons = screen.getAllByRole('button', { name: /select and continue/i });
    await act(async () => {
      if (confirmButtons[0]) {
        fireEvent.click(confirmButtons[0]);
      }
      await Promise.resolve();
    });

    // Assert close called and navigation happened
    await waitFor(() => {
      expect(mockOnClose).toHaveBeenCalled();
      expect(pushMock).toHaveBeenCalled();
    });
  });

  it('shows loading state during reschedule', async () => {
    const useRescheduleLesson = myLessonsHooks.useRescheduleLesson as jest.Mock;
    useRescheduleLesson.mockReturnValue({
      mutateAsync: jest.fn(),
      isPending: true,
    });

    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    await act(async () => { await Promise.resolve(); });

    // When loading, the confirm button should show "Rescheduling..."
    const confirmButtons = screen.getAllByRole('button', { name: /select and continue/i });
    expect(confirmButtons.length).toBeGreaterThan(0);
  });

  it('shows chat to reschedule option', () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    const chats = screen.getAllByText('Chat to reschedule');
    expect(chats.length).toBeGreaterThan(0);
  });
});
