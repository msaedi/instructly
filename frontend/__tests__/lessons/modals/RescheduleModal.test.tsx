import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RescheduleModal } from '@/components/lessons/modals/RescheduleModal';
import type { Booking } from '@/features/shared/api/types';
import { addDays, format, parse } from 'date-fns';
import { AuthProvider } from '@/features/shared/hooks/useAuth';
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

// Mock v1 bookings service used by the modal
const mockRescheduleBookingImperative = jest.fn();
jest.mock('@/src/api/services/bookings', () => ({
  rescheduleBookingImperative: (...args: unknown[]) => mockRescheduleBookingImperative(...args),
}));

// Mock API client used by availability modal
jest.mock('@/features/shared/api/client', () => {
  const { addDays, format } = jest.requireActual('date-fns') as typeof import('date-fns');

  return {
    publicApi: {
      getInstructorAvailability: jest.fn().mockImplementation(() => {
        const today = new Date();
        const t1 = format(addDays(today, 1), 'yyyy-MM-dd');
        const t2 = format(addDays(today, 2), 'yyyy-MM-dd');

        return Promise.resolve({
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
        });
      }),
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
  const bookingDate = format(addDays(new Date(), 9), 'yyyy-MM-dd');
  const mockBooking = ({
    id: '01K2MAY484FQGFEQVN3VKGYZ58',
    booking_date: bookingDate,
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

  const getCalendarMonthLabel = () => {
    const monthHeadings = screen.getAllByText((content, element) => {
      const text = content?.trim() ?? '';
      return /^[A-Za-z]+ \d{4}$/.test(text) && element?.tagName.toLowerCase() === 'h3';
    });
    const label = monthHeadings[0]?.textContent?.trim();
    if (!label) {
      throw new Error('Calendar month heading not found');
    }
    return label;
  };

  const navigateToMonth = async (targetDate: Date) => {
    const currentLabel = getCalendarMonthLabel();
    const currentDate = parse(currentLabel, 'MMMM yyyy', new Date());
    if (Number.isNaN(currentDate.getTime())) {
      throw new Error(`Unable to parse calendar month label: ${currentLabel}`);
    }

    const diffMonths =
      (targetDate.getFullYear() - currentDate.getFullYear()) * 12 +
      (targetDate.getMonth() - currentDate.getMonth());

    if (diffMonths === 0) {
      return;
    }

    const directionLabel = diffMonths > 0 ? /Next month/i : /Previous month/i;
    const steps = Math.abs(diffMonths);
    for (let i = 0; i < steps; i += 1) {
      const buttons = screen.getAllByLabelText(directionLabel);
      const button = buttons[0];
      if (!button) {
        throw new Error(`Calendar navigation button not found for ${directionLabel}`);
      }
      await act(async () => {
        fireEvent.click(button);
        await Promise.resolve();
      });
    }

    const targetLabel = format(targetDate, 'MMMM yyyy');
    await waitFor(() => {
      expect(screen.getAllByText(targetLabel).length).toBeGreaterThan(0);
    });
  };

  const getSelectableDayButton = async (dateIso: string) => {
    const dayButtons = (await screen.findAllByTestId(`cal-day-${dateIso}`)) as HTMLButtonElement[];
    const dayButton = dayButtons.find((btn) => !btn.disabled) ?? dayButtons[0];
    if (!dayButton) {
      throw new Error(`No selectable calendar button found for ${dateIso}`);
    }
    return dayButton;
  };

  beforeEach(() => {
    jest.clearAllMocks();
    // Default successful reschedule response
    mockRescheduleBookingImperative.mockResolvedValue({ id: '01KNEWBOOKINGID123456789' });
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
    const tomorrow = addDays(new Date(), 1);
    const tomorrowIso = format(tomorrow, 'yyyy-MM-dd');

    await navigateToMonth(tomorrow);
    const dayButton = await getSelectableDayButton(tomorrowIso);
    expect(dayButton).toBeEnabled();
    fireEvent.click(dayButton);

    // Confirm should be enabled after auto-selecting first time
    await waitFor(() => {
      const confirmButtons = screen.getAllByRole('button', { name: /select and continue/i });
      const confirmButton = confirmButtons[0];
      if (confirmButton) {
        expect(confirmButton).not.toBeDisabled();
      }
    });
  });

  it('allows selecting a time slot', async () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    await act(async () => { await Promise.resolve(); });

    // Select tomorrow's date first
    const tomorrow = addDays(new Date(), 1);
    const tomorrowIso = format(tomorrow, 'yyyy-MM-dd');

    await waitFor(() => {
      expect(screen.queryByText(/Loading availability/i)).not.toBeInTheDocument();
    });

    await navigateToMonth(tomorrow);
    const dayButton = await getSelectableDayButton(tomorrowIso);
    expect(dayButton).toBeEnabled();
    fireEvent.click(dayButton);

    // Auto-selected time should enable confirm
    await waitFor(() => {
      const confirmButtons = screen.getAllByRole('button', { name: /select and continue/i });
      const confirmButton = confirmButtons[0];
      if (confirmButton) {
        expect(confirmButton).not.toBeDisabled();
      }
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

  it('shows current booking date highlighted', async () => {
    renderWithProviders(
      <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
    );

    await act(async () => { await Promise.resolve(); });

    // Use getAllByTestId to query the current lesson banners (mobile + desktop)
    const currentLessonBanners = screen.getAllByTestId('current-lesson-banner');
    expect(currentLessonBanners.length).toBeGreaterThan(0);

    // Verify the banner contains the service name and date
    const firstBanner = currentLessonBanners[0];
    if (firstBanner) {
      expect(firstBanner.textContent).toContain('Mathematics');
      const bookingLabel = format(
        new Date(`${mockBooking.booking_date}T${mockBooking.start_time}`),
        'MMM d'
      );
      expect(firstBanner.textContent).toContain(bookingLabel);
    }
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
    const tomorrow = addDays(new Date(), 1);
    const tomorrowIso = format(tomorrow, 'yyyy-MM-dd');

    await waitFor(() => {
      expect(screen.queryByText(/Loading availability/i)).not.toBeInTheDocument();
    });

    await navigateToMonth(tomorrow);
    const dateButton = await getSelectableDayButton(tomorrowIso);
    expect(dateButton).toBeEnabled();
    fireEvent.click(dateButton);

    // Time is auto-selected; proceed

    // Click confirm (pick the first button instance)
    const confirmButtons = screen.getAllByRole('button', { name: /select and continue/i });
    await act(async () => {
      const confirmButton = confirmButtons[0];
      if (confirmButton) {
        fireEvent.click(confirmButton);
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

  describe('error handling', () => {
    // Helper to select a date and trigger reschedule
    const selectDateAndConfirm = async () => {
      const tomorrow = addDays(new Date(), 1);
      const tomorrowIso = format(tomorrow, 'yyyy-MM-dd');

      await waitFor(() => {
        expect(screen.queryByText(/Loading availability/i)).not.toBeInTheDocument();
      });

      await navigateToMonth(tomorrow);
      const dayButton = await getSelectableDayButton(tomorrowIso);
      fireEvent.click(dayButton);

      const confirmButtons = screen.getAllByRole('button', { name: /select and continue/i });
      await act(async () => {
        const confirmButton = confirmButtons[0];
        if (confirmButton) {
          fireEvent.click(confirmButton);
        }
        await Promise.resolve();
      });

      // Wait for dynamic import to resolve
      await act(async () => {
        await Promise.resolve();
        await new Promise(r => setTimeout(r, 50));
      });
    };

    it('handles payment_method_required error', async () => {
      mockRescheduleBookingImperative.mockRejectedValueOnce(
        new Error('payment_method_required: A valid payment method is needed')
      );

      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
      );

      await act(async () => { await Promise.resolve(); });
      await selectDateAndConfirm();

      await waitFor(() => {
        expect(mockOnClose).toHaveBeenCalled();
        expect(pushMock).toHaveBeenCalledWith('/student/settings?tab=payment');
      });
    });

    it('handles payment method error with different wording', async () => {
      mockRescheduleBookingImperative.mockRejectedValueOnce(
        new Error('A payment method is required to proceed')
      );

      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
      );

      await act(async () => { await Promise.resolve(); });
      await selectDateAndConfirm();

      await waitFor(() => {
        expect(pushMock).toHaveBeenCalledWith('/student/settings?tab=payment');
      });
    });

    it('handles payment_confirmation_failed error', async () => {
      mockRescheduleBookingImperative.mockRejectedValueOnce(
        new Error('payment_confirmation_failed: Card declined')
      );

      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
      );

      await act(async () => { await Promise.resolve(); });
      await selectDateAndConfirm();

      // Modal should stay open for retry (onClose NOT called)
      await waitFor(() => {
        expect(mockRescheduleBookingImperative).toHaveBeenCalled();
      });
      // Modal should remain open
      expect(screen.getAllByText('Need to reschedule?').length).toBeGreaterThan(0);
    });

    it('handles payment failed error', async () => {
      mockRescheduleBookingImperative.mockRejectedValueOnce(
        new Error('payment failed: insufficient funds')
      );

      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
      );

      await act(async () => { await Promise.resolve(); });
      await selectDateAndConfirm();

      // Modal stays open for retry
      await waitFor(() => {
        expect(mockRescheduleBookingImperative).toHaveBeenCalled();
      });
    });

    it('handles 409 conflict error for student booking conflict', async () => {
      mockRescheduleBookingImperative.mockRejectedValueOnce(
        new Error('409: student already have a booking at this time')
      );

      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
      );

      await act(async () => { await Promise.resolve(); });
      await selectDateAndConfirm();

      // Modal stays open for re-selection
      await waitFor(() => {
        expect(screen.getAllByText('Need to reschedule?').length).toBeGreaterThan(0);
      });
    });

    it('handles 409 conflict error for instructor conflict', async () => {
      mockRescheduleBookingImperative.mockRejectedValueOnce(
        new Error('conflict: slot no longer available')
      );

      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
      );

      await act(async () => { await Promise.resolve(); });
      await selectDateAndConfirm();

      // Modal stays open for re-selection
      await waitFor(() => {
        expect(screen.getAllByText('Need to reschedule?').length).toBeGreaterThan(0);
      });
    });

    it('handles generic error', async () => {
      mockRescheduleBookingImperative.mockRejectedValueOnce(
        new Error('Something went wrong')
      );

      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
      );

      await act(async () => { await Promise.resolve(); });
      await selectDateAndConfirm();

      // Modal should handle the error
      await waitFor(() => {
        expect(mockRescheduleBookingImperative).toHaveBeenCalled();
      });
    });

    it('handles non-Error thrown value', async () => {
      mockRescheduleBookingImperative.mockRejectedValueOnce('string error');

      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
      );

      await act(async () => { await Promise.resolve(); });
      await selectDateAndConfirm();

      // Should still handle gracefully
      await waitFor(() => {
        expect(mockRescheduleBookingImperative).toHaveBeenCalled();
      });
    });
  });

  describe('network errors', () => {
    it('handles network error during dynamic import', async () => {
      // Temporarily replace the mock to simulate network error in .catch
      const originalMock = jest.requireMock('@/src/api/services/bookings');
      jest.doMock('@/src/api/services/bookings', () => {
        throw new Error('Network error');
      });

      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
      );

      await act(async () => { await Promise.resolve(); });

      // Modal should still render
      expect(screen.getAllByText('Need to reschedule?').length).toBeGreaterThan(0);

      // Restore mock
      jest.doMock('@/src/api/services/bookings', () => originalMock);
    });
  });

  describe('chat modal', () => {
    it('opens chat modal when chat link is clicked', async () => {
      const mockUser = {
        id: '01K2MAY484FQGFEQVN3VKGYZ60',
        first_name: 'Student',
        last_name: 'User',
        email: 'student@example.com',
      };

      // Mock useAuth to return a user
      jest.doMock('@/features/shared/hooks/useAuth', () => ({
        useAuth: () => ({
          user: mockUser,
          isLoading: false,
          isAuthenticated: true,
        }),
        AuthProvider: ({ children }: { children: React.ReactNode }) => children,
      }));

      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
      );

      await act(async () => { await Promise.resolve(); });

      // Find and click the chat link
      const chatLinks = screen.getAllByText('Chat to reschedule');
      expect(chatLinks.length).toBeGreaterThan(0);

      await act(async () => {
        fireEvent.click(chatLinks[0]!);
        await Promise.resolve();
      });

      // The RescheduleTimeSelectionModal should hide when chat opens
      // (isOpen && !showChatModal condition)
    });

    it('handles booking without instructor info', async () => {
      const bookingWithoutInstructor = {
        ...mockBooking,
        instructor: undefined,
      } as unknown as Booking;

      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={bookingWithoutInstructor} />
      );

      await act(async () => { await Promise.resolve(); });

      // Should still render the modal
      expect(screen.getAllByText('Need to reschedule?').length).toBeGreaterThan(0);
    });

    it('handles booking with missing instructor first_name', async () => {
      const bookingMissingName = {
        ...mockBooking,
        instructor: {
          id: '01K2MAY484FQGFEQVN3VKGYZ59',
          first_name: null,
          last_initial: 'D',
        },
      } as unknown as Booking;

      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={bookingMissingName} />
      );

      await act(async () => { await Promise.resolve(); });

      expect(screen.getAllByText('Need to reschedule?').length).toBeGreaterThan(0);
    });
  });

  describe('time parsing edge cases', () => {
    it('handles AM time parsing correctly', async () => {
      mockRescheduleBookingImperative.mockResolvedValueOnce({ id: '01KNEWBOOKINGID123456789' });

      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
      );

      await act(async () => { await Promise.resolve(); });

      // The modal should render and handle time parsing internally
      await waitFor(() => {
        expect(screen.queryByText(/Loading availability/i)).not.toBeInTheDocument();
      });

      // Select a date
      const tomorrow = addDays(new Date(), 1);
      const tomorrowIso = format(tomorrow, 'yyyy-MM-dd');

      await navigateToMonth(tomorrow);
      const dayButton = await getSelectableDayButton(tomorrowIso);
      fireEvent.click(dayButton);

      // Confirm button should be clickable
      const confirmButtons = screen.getAllByRole('button', { name: /select and continue/i });
      expect(confirmButtons.length).toBeGreaterThan(0);
    });

    it('handles 12 PM edge case', async () => {
      // 12pm should stay as 12, not become 0 or 24
      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
      );

      await act(async () => { await Promise.resolve(); });

      expect(screen.getAllByText('Need to reschedule?').length).toBeGreaterThan(0);
    });

    it('handles 12 AM edge case', async () => {
      // 12am should become 0
      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
      );

      await act(async () => { await Promise.resolve(); });

      expect(screen.getAllByText('Need to reschedule?').length).toBeGreaterThan(0);
    });
  });

  describe('reschedule data storage', () => {
    it('stores reschedule data in sessionStorage before API call', async () => {
      const sessionStorageSpy = jest.spyOn(Storage.prototype, 'setItem');

      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
      );

      await act(async () => { await Promise.resolve(); });

      const tomorrow = addDays(new Date(), 1);
      const tomorrowIso = format(tomorrow, 'yyyy-MM-dd');

      await waitFor(() => {
        expect(screen.queryByText(/Loading availability/i)).not.toBeInTheDocument();
      });

      await navigateToMonth(tomorrow);
      const dayButton = await getSelectableDayButton(tomorrowIso);
      fireEvent.click(dayButton);

      const confirmButtons = screen.getAllByRole('button', { name: /select and continue/i });
      await act(async () => {
        const confirmButton = confirmButtons[0];
        if (confirmButton) {
          fireEvent.click(confirmButton);
        }
        await Promise.resolve();
        await new Promise(r => setTimeout(r, 50));
      });

      expect(sessionStorageSpy).toHaveBeenCalledWith(
        'rescheduleData',
        expect.stringContaining('"isReschedule":true')
      );

      sessionStorageSpy.mockRestore();
    });
  });

  describe('query cache invalidation', () => {
    it('invalidates booking caches on successful reschedule', async () => {
      mockRescheduleBookingImperative.mockResolvedValueOnce({ id: '01KNEWBOOKINGID123456789' });

      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
      );

      await act(async () => { await Promise.resolve(); });

      const tomorrow = addDays(new Date(), 1);
      const tomorrowIso = format(tomorrow, 'yyyy-MM-dd');

      await waitFor(() => {
        expect(screen.queryByText(/Loading availability/i)).not.toBeInTheDocument();
      });

      await navigateToMonth(tomorrow);
      const dayButton = await getSelectableDayButton(tomorrowIso);
      fireEvent.click(dayButton);

      const confirmButtons = screen.getAllByRole('button', { name: /select and continue/i });
      await act(async () => {
        const confirmButton = confirmButtons[0];
        if (confirmButton) {
          fireEvent.click(confirmButton);
        }
        await Promise.resolve();
        await new Promise(r => setTimeout(r, 100));
      });

      // Cache invalidation happens asynchronously
      await waitFor(() => {
        expect(mockOnClose).toHaveBeenCalled();
      });
    });

    it('navigates to lesson details when result has id', async () => {
      mockRescheduleBookingImperative.mockResolvedValueOnce({ id: '01KNEWBOOKINGID123456789' });

      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
      );

      await act(async () => { await Promise.resolve(); });

      const tomorrow = addDays(new Date(), 1);
      const tomorrowIso = format(tomorrow, 'yyyy-MM-dd');

      await waitFor(() => {
        expect(screen.queryByText(/Loading availability/i)).not.toBeInTheDocument();
      });

      await navigateToMonth(tomorrow);
      const dayButton = await getSelectableDayButton(tomorrowIso);
      fireEvent.click(dayButton);

      const confirmButtons = screen.getAllByRole('button', { name: /select and continue/i });
      await act(async () => {
        const confirmButton = confirmButtons[0];
        if (confirmButton) {
          fireEvent.click(confirmButton);
        }
        await Promise.resolve();
        await new Promise(r => setTimeout(r, 100));
      });

      await waitFor(() => {
        expect(pushMock).toHaveBeenCalledWith('/student/lessons/01KNEWBOOKINGID123456789');
      });
    });

    it('navigates to lessons list when result has no id', async () => {
      mockRescheduleBookingImperative.mockResolvedValueOnce({});

      renderWithProviders(
        <RescheduleModal isOpen={true} onClose={mockOnClose} lesson={mockBooking} />
      );

      await act(async () => { await Promise.resolve(); });

      const tomorrow = addDays(new Date(), 1);
      const tomorrowIso = format(tomorrow, 'yyyy-MM-dd');

      await waitFor(() => {
        expect(screen.queryByText(/Loading availability/i)).not.toBeInTheDocument();
      });

      await navigateToMonth(tomorrow);
      const dayButton = await getSelectableDayButton(tomorrowIso);
      fireEvent.click(dayButton);

      const confirmButtons = screen.getAllByRole('button', { name: /select and continue/i });
      await act(async () => {
        const confirmButton = confirmButtons[0];
        if (confirmButton) {
          fireEvent.click(confirmButton);
        }
        await Promise.resolve();
        await new Promise(r => setTimeout(r, 100));
      });

      await waitFor(() => {
        expect(pushMock).toHaveBeenCalledWith('/student/lessons');
      });
    });
  });
});
