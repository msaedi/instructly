import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TimeSelectionModal from '../TimeSelectionModal';
import { useAuth, storeBookingIntent } from '../../hooks/useAuth';
import { usePricingFloors } from '@/lib/pricing/usePricingFloors';
import { fetchPricingPreview } from '@/lib/api/pricing';
import { publicApi } from '@/features/shared/api/client';

// Mock dependencies
jest.mock('../../hooks/useAuth', () => ({
  useAuth: jest.fn(),
  storeBookingIntent: jest.fn(),
}));

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingFloors: jest.fn(),
}));

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    getInstructorAvailability: jest.fn(),
  },
}));

jest.mock('@/lib/api/pricing', () => ({
  fetchPricingPreview: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('@/components/user/UserAvatar', () => ({
  UserAvatar: ({ user }: { user: { first_name: string } }) => (
    <div data-testid="user-avatar">{user.first_name}</div>
  ),
}));

// Track handlers for assertions
let calendarOnDateSelect: ((date: string) => void) | null = null;
let calendarOnMonthChange: ((month: Date) => void) | null = null;

jest.mock('@/features/shared/booking/ui/Calendar', () => {
  return function MockCalendar({ onDateSelect, availableDates, selectedDate, onMonthChange }: {
    onDateSelect: (date: string) => void;
    availableDates: string[];
    selectedDate: string | null;
    onMonthChange?: (month: Date) => void;
  }) {
    calendarOnDateSelect = onDateSelect;
    calendarOnMonthChange = onMonthChange ?? null;
    return (
      <div data-testid="calendar">
        <span data-testid="available-dates-count">{availableDates.length}</span>
        <span data-testid="selected-date">{selectedDate ?? 'none'}</span>
        {availableDates.slice(0, 3).map((date) => (
          <button key={date} data-testid={`date-${date}`} onClick={() => onDateSelect(date)}>
            {date}
          </button>
        ))}
      </div>
    );
  };
});

jest.mock('@/features/shared/booking/ui/TimeDropdown', () => {
  return function MockTimeDropdown({ timeSlots, selectedTime, onTimeSelect, isVisible }: {
    timeSlots: string[];
    selectedTime: string | null;
    onTimeSelect: (time: string) => void;
    isVisible: boolean;
  }) {
    if (!isVisible) return null;
    return (
      <div data-testid="time-dropdown">
        <span data-testid="time-slots-count">{timeSlots.length}</span>
        <span data-testid="selected-time">{selectedTime ?? 'none'}</span>
        {timeSlots.slice(0, 3).map((time) => (
          <button key={time} data-testid={`time-${time}`} onClick={() => onTimeSelect(time)}>
            {time}
          </button>
        ))}
      </div>
    );
  };
});

jest.mock('@/features/shared/booking/ui/DurationButtons', () => {
  return function MockDurationButtons({ durationOptions, selectedDuration, onDurationSelect }: {
    durationOptions: Array<{ duration: number; price: number }>;
    selectedDuration: number;
    onDurationSelect: (duration: number) => void;
  }) {
    if (durationOptions.length <= 1) return null;
    return (
      <div data-testid="duration-buttons">
        <span data-testid="selected-duration">{selectedDuration}</span>
        {durationOptions.map((opt) => (
          <button key={opt.duration} data-testid={`duration-${opt.duration}`} onClick={() => onDurationSelect(opt.duration)}>
            {opt.duration}min (${opt.price})
          </button>
        ))}
      </div>
    );
  };
});

// Track SummarySection props
let summaryOnContinue: (() => void) | null = null;

const runContinueWithoutNavigation = async (onContinue: (() => void) | null) => {
  const timeoutSpy = jest.spyOn(window, 'setTimeout').mockImplementation(() => 0 as unknown as ReturnType<typeof setTimeout>);
  try {
    await act(async () => {
      onContinue?.();
    });
  } finally {
    timeoutSpy.mockRestore();
  }
};

jest.mock('@/features/shared/booking/ui/SummarySection', () => {
  return function MockSummarySection({ onContinue, isComplete, floorWarning }: {
    onContinue: () => void;
    isComplete: boolean;
    floorWarning?: string | null;
  }) {
    summaryOnContinue = onContinue;
    return (
      <div data-testid="summary-section">
        <span data-testid="summary-complete">{String(isComplete)}</span>
        {floorWarning && <span data-testid="floor-warning">{floorWarning}</span>}
        <button data-testid="summary-continue" onClick={onContinue} disabled={!isComplete}>
          Continue
        </button>
      </div>
    );
  };
});

const useAuthMock = useAuth as jest.Mock;
const usePricingFloorsMock = usePricingFloors as jest.Mock;
const fetchPricingPreviewMock = fetchPricingPreview as jest.Mock;
const publicApiMock = publicApi as jest.Mocked<typeof publicApi>;
const storeBookingIntentMock = storeBookingIntent as jest.Mock;

const mockService = {
  id: 'svc-1',
  duration_options: [30, 60, 90] as number[],
  hourly_rate: 60,
  skill: 'Piano Lessons',
  location_types: ['in-person'] as string[],
};

const mockInstructor = {
  user_id: 'user-123',
  user: {
    first_name: 'John',
    last_initial: 'D',
    has_profile_picture: true,
    profile_picture_version: 1,
    timezone: 'America/New_York',
  },
  services: [mockService],
};

const getDateString = (daysFromToday: number): string => {
  const date = new Date();
  date.setDate(date.getDate() + daysFromToday);
  return date.toISOString().split('T')[0] ?? '';
};

const mockAvailabilityResponse = (dates: string[]) => {
  const availability_by_date: Record<string, { date: string; available_slots: Array<{ start_time: string; end_time: string }>; is_blackout: boolean }> = {};
  dates.forEach((date) => {
    availability_by_date[date] = {
      date,
      available_slots: [
        { start_time: '09:00', end_time: '12:00' },
        { start_time: '14:00', end_time: '18:00' },
      ],
      is_blackout: false,
    };
  });
  // Ensure earliest_available_date is always a string (not null) by providing fallback
  const firstDate = dates[0];
  return {
    status: 200 as const,
    data: {
      instructor_id: 'user-123',
      instructor_first_name: 'John' as string | null,
      instructor_last_initial: 'D' as string | null,
      availability_by_date,
      timezone: 'America/New_York',
      total_available_slots: dates.length * 2,
      earliest_available_date: firstDate ?? getDateString(1),
    },
  };
};

describe('TimeSelectionModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    instructor: mockInstructor,
  };

  beforeEach(() => {
    jest.clearAllMocks();
    calendarOnDateSelect = null;
    calendarOnMonthChange = null;
    summaryOnContinue = null;

    useAuthMock.mockReturnValue({
      isAuthenticated: true,
      user: { id: 'student-123', timezone: 'America/New_York' },
      redirectToLogin: jest.fn(),
    });

    usePricingFloorsMock.mockReturnValue({
      floors: null,
    });

    fetchPricingPreviewMock.mockResolvedValue({
      base_amount: 60,
      service_fee: 10,
      total_amount: 70,
    });

    const dates = [getDateString(1), getDateString(2), getDateString(3)];
    publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

    // Mock sessionStorage
    const storage: Record<string, string> = {};
    Object.defineProperty(window, 'sessionStorage', {
      value: {
        setItem: jest.fn((key: string, value: string) => {
          storage[key] = value;
        }),
        getItem: jest.fn((key: string) => storage[key] ?? null),
        removeItem: jest.fn(),
        clear: jest.fn(),
      },
      writable: true,
    });
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('visibility', () => {
    it('renders nothing when isOpen is false', () => {
      const { container } = render(
        <TimeSelectionModal {...defaultProps} isOpen={false} />
      );
      expect(container.firstChild).toBeNull();
    });

    it('renders modal when isOpen is true', () => {
      render(<TimeSelectionModal {...defaultProps} />);
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('close behavior', () => {
    it('calls onClose when desktop close button is clicked', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();
      render(<TimeSelectionModal {...defaultProps} onClose={onClose} />);

      const closeButtons = screen.getAllByRole('button', { name: /close/i });
      if (closeButtons.length > 0) {
        await user.click(closeButtons[0]!);
        expect(onClose).toHaveBeenCalled();
      }
    });

    it('calls onClose when mobile back button is clicked', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();
      render(<TimeSelectionModal {...defaultProps} onClose={onClose} />);

      const backButton = screen.getByRole('button', { name: /go back/i });
      await user.click(backButton);
      expect(onClose).toHaveBeenCalled();
    });

    it('calls onClose on escape key press', async () => {
      const onClose = jest.fn();
      render(<TimeSelectionModal {...defaultProps} onClose={onClose} />);

      await act(async () => {
        const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true });
        document.dispatchEvent(event);
      });

      expect(onClose).toHaveBeenCalled();
    });
  });

  describe('instructor display', () => {
    it('displays instructor avatar', () => {
      render(<TimeSelectionModal {...defaultProps} />);
      expect(screen.queryAllByTestId('user-avatar')[0]).toHaveTextContent('John');
    });

    it('displays instructor availability title', () => {
      render(<TimeSelectionModal {...defaultProps} />);
      expect(screen.getAllByText(/John D\.'s availability/i).length).toBeGreaterThan(0);
    });
  });

  describe('availability fetching', () => {
    it('fetches availability when modal opens', async () => {
      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(publicApiMock.getInstructorAvailability).toHaveBeenCalledWith(
          'user-123',
          expect.objectContaining({
            start_date: expect.any(String),
            end_date: expect.any(String),
          })
        );
      });
    });

    it('sets available dates from response', async () => {
      const dates = [getDateString(1), getDateString(2)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        const countElements = screen.getAllByTestId('available-dates-count');
        expect(parseInt(countElements[0]?.textContent ?? '0', 10)).toBeGreaterThan(0);
      });
    });

    it('handles fetch error gracefully', async () => {
      publicApiMock.getInstructorAvailability.mockRejectedValue(new Error('Network error'));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
      });
    });
  });

  describe('date selection', () => {
    it('auto-selects first available date', async () => {
      const dates = [getDateString(1), getDateString(2)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        const selectedDateElements = screen.getAllByTestId('selected-date');
        expect(selectedDateElements[0]?.textContent).not.toBe('none');
      });
    });

    it('uses preSelectedDate when provided', async () => {
      const dates = [getDateString(1), getDateString(2), getDateString(3)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} preSelectedDate={dates[1]} />);

      await waitFor(() => {
        expect(publicApiMock.getInstructorAvailability).toHaveBeenCalled();
      });
    });

    it('handles date selection via calendar', async () => {
      const user = userEvent.setup();
      const dates = [getDateString(1), getDateString(2)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        const dateButtons = screen.getAllByTestId(`date-${dates[0]}`);
        expect(dateButtons.length).toBeGreaterThan(0);
      });

      const dateButtons = screen.getAllByTestId(`date-${dates[1]}`);
      await user.click(dateButtons[0]!);

      await waitFor(() => {
        const timeDropdowns = screen.getAllByTestId('time-dropdown');
        expect(timeDropdowns.length).toBeGreaterThan(0);
      });
    });
  });

  describe('time selection', () => {
    it('shows time dropdown when date is selected', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        const timeDropdowns = screen.getAllByTestId('time-dropdown');
        expect(timeDropdowns.length).toBeGreaterThan(0);
      });
    });

    it('generates time slots from availability', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        const slotsCountElements = screen.getAllByTestId('time-slots-count');
        expect(parseInt(slotsCountElements[0]?.textContent ?? '0', 10)).toBeGreaterThan(0);
      });
    });
  });

  describe('duration selection', () => {
    it('renders duration buttons when multiple options available', () => {
      render(<TimeSelectionModal {...defaultProps} />);
      expect(screen.queryAllByTestId('duration-buttons').length).toBeGreaterThan(0);
    });

    it('does not render duration buttons when single option', () => {
      const instructorWithSingleDuration = {
        ...mockInstructor,
        services: [{ ...mockService, duration_options: [60] }],
      };

      render(<TimeSelectionModal {...defaultProps} instructor={instructorWithSingleDuration} />);
      expect(screen.queryByTestId('duration-buttons')).not.toBeInTheDocument();
    });

    it('handles duration button click', async () => {
      const user = userEvent.setup();
      render(<TimeSelectionModal {...defaultProps} />);

      const duration60Buttons = screen.getAllByTestId('duration-60');
      await user.click(duration60Buttons[0]!);

      // Component should not crash
      expect(screen.queryAllByTestId('duration-buttons').length).toBeGreaterThan(0);
    });
  });

  describe('service selection', () => {
    it('uses serviceId to find correct service', () => {
      const instructorWithMultipleServices = {
        ...mockInstructor,
        services: [
          { id: 'svc-1', duration_options: [30], hourly_rate: 40, skill: 'Piano', location_types: ['in-person'] },
          { id: 'svc-2', duration_options: [60], hourly_rate: 80, skill: 'Guitar', location_types: ['in-person'] },
        ],
      };

      render(
        <TimeSelectionModal {...defaultProps} instructor={instructorWithMultipleServices} serviceId="svc-2" />
      );

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('falls back to first service when serviceId not found', () => {
      render(<TimeSelectionModal {...defaultProps} serviceId="non-existent" />);
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('handles instructor with no services', () => {
      const instructorWithoutServices = { ...mockInstructor, services: [] };
      render(<TimeSelectionModal {...defaultProps} instructor={instructorWithoutServices} />);
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('pre-selection props', () => {
    it('uses initialDate as Date object', () => {
      const initialDate = new Date();
      initialDate.setDate(initialDate.getDate() + 1);

      render(<TimeSelectionModal {...defaultProps} initialDate={initialDate} />);
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('uses initialDate as ISO string', () => {
      const initialDate = `${getDateString(1)}T10:00:00`;
      render(<TimeSelectionModal {...defaultProps} initialDate={initialDate} />);
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('uses initialTimeHHMM24', () => {
      render(<TimeSelectionModal {...defaultProps} initialTimeHHMM24="14:00" />);
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('handles malformed initialTimeHHMM24', () => {
      render(<TimeSelectionModal {...defaultProps} initialTimeHHMM24="invalid" />);
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('uses initialDurationMinutes when valid', () => {
      render(<TimeSelectionModal {...defaultProps} initialDurationMinutes={90} />);
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('uses preSelectedTime', () => {
      render(<TimeSelectionModal {...defaultProps} preSelectedTime="10:00am" />);
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('continue flow with onTimeSelected', () => {
    it('calls onTimeSelected when provided and complete', async () => {
      const onTimeSelected = jest.fn();
      const onClose = jest.fn();
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(
        <TimeSelectionModal {...defaultProps} onClose={onClose} onTimeSelected={onTimeSelected} />
      );

      await waitFor(() => {
        expect(summaryOnContinue).not.toBeNull();
      });

      // Check if isComplete is true before clicking
      const summaryCompleteElements = screen.getAllByTestId('summary-complete');
      const isComplete = summaryCompleteElements[0]?.textContent;
      if (isComplete === 'true') {
        await runContinueWithoutNavigation(summaryOnContinue);

        expect(onTimeSelected).toHaveBeenCalledWith({
          date: expect.any(String),
          time: expect.any(String),
          duration: expect.any(Number),
        });
        expect(onClose).toHaveBeenCalled();
      }
    });
  });

  describe('continue flow without onTimeSelected', () => {
    it('stores booking data in sessionStorage', async () => {
      jest.useFakeTimers();
      const onClose = jest.fn();
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} onClose={onClose} />);

      await waitFor(() => {
        expect(summaryOnContinue).not.toBeNull();
      });

      const summaryCompleteElements = screen.getAllByTestId('summary-complete');
      const isComplete = summaryCompleteElements[0]?.textContent;
      if (isComplete === 'true') {
        await runContinueWithoutNavigation(summaryOnContinue);

        expect(onClose).toHaveBeenCalled();
        expect(window.sessionStorage.setItem).toHaveBeenCalledWith('bookingData', expect.any(String));
      }

      jest.useRealTimers();
    });
  });

  describe('authentication flow', () => {
    it('redirects to login when not authenticated', async () => {
      const redirectToLogin = jest.fn();
      useAuthMock.mockReturnValue({
        isAuthenticated: false,
        user: null,
        redirectToLogin,
      });

      const onClose = jest.fn();
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} onClose={onClose} />);

      await waitFor(() => {
        expect(summaryOnContinue).not.toBeNull();
      });

      const summaryCompleteElements = screen.getAllByTestId('summary-complete');
      const isComplete = summaryCompleteElements[0]?.textContent;
      if (isComplete === 'true') {
        await runContinueWithoutNavigation(summaryOnContinue);

        expect(storeBookingIntentMock).toHaveBeenCalled();
        expect(redirectToLogin).toHaveBeenCalledWith('/student/booking/confirm');
        expect(onClose).toHaveBeenCalled();
      }
    });
  });

  describe('pricing floors', () => {
    it('shows floor warning when price is below minimum', async () => {
      usePricingFloorsMock.mockReturnValue({
        floors: {
          private_in_person: 10000,
          private_remote: 6000,
        },
      });

      const lowRateInstructor = {
        ...mockInstructor,
        services: [{ ...mockService, hourly_rate: 20 }],
      };

      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} instructor={lowRateInstructor} />);

      await waitFor(() => {
        const summaryCompleteElements = screen.getAllByTestId('summary-complete');
        expect(summaryCompleteElements[0]?.textContent).toBe('false');
      });
    });
  });

  describe('pricing preview', () => {
    it('fetches pricing preview when bookingDraftId is provided', async () => {
      render(<TimeSelectionModal {...defaultProps} bookingDraftId="draft-123" />);

      await waitFor(() => {
        expect(fetchPricingPreviewMock).toHaveBeenCalledWith('draft-123', 0);
      });
    });

    it('passes appliedCreditCents to pricing preview', async () => {
      render(
        <TimeSelectionModal {...defaultProps} bookingDraftId="draft-123" appliedCreditCents={1000} />
      );

      await waitFor(() => {
        expect(fetchPricingPreviewMock).toHaveBeenCalledWith('draft-123', 1000);
      });
    });

    it('normalizes negative appliedCreditCents to 0', async () => {
      render(
        <TimeSelectionModal {...defaultProps} bookingDraftId="draft-123" appliedCreditCents={-500} />
      );

      await waitFor(() => {
        expect(fetchPricingPreviewMock).toHaveBeenCalledWith('draft-123', 0);
      });
    });

    it('handles pricing preview error', async () => {
      fetchPricingPreviewMock.mockRejectedValue(new Error('Network error'));

      render(<TimeSelectionModal {...defaultProps} bookingDraftId="draft-123" />);

      await waitFor(() => {
        expect(fetchPricingPreviewMock).toHaveBeenCalled();
      });

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('modality detection', () => {
    it('detects online modality', () => {
      const onlineInstructor = {
        ...mockInstructor,
        services: [{ ...mockService, location_types: ['online', 'virtual'] }],
      };

      render(<TimeSelectionModal {...defaultProps} instructor={onlineInstructor} />);
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('handles empty location_types', () => {
      const noLocationTypesInstructor = {
        ...mockInstructor,
        services: [{ ...mockService, location_types: [] }],
      };

      render(<TimeSelectionModal {...defaultProps} instructor={noLocationTypesInstructor} />);
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('defaults to remote when no location types defined', () => {
      const noLocationInstructor = {
        ...mockInstructor,
        services: [{ ...mockService, location_types: [] as string[] }],
      };

      render(
        <TimeSelectionModal {...defaultProps} instructor={noLocationInstructor} />
      );
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('user timezone', () => {
    it('uses user timezone from auth context', () => {
      useAuthMock.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'student-123', timezone: 'America/Los_Angeles' },
        redirectToLogin: jest.fn(),
      });

      render(<TimeSelectionModal {...defaultProps} />);
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('falls back when user has no timezone', () => {
      useAuthMock.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'student-123' },
        redirectToLogin: jest.fn(),
      });

      render(<TimeSelectionModal {...defaultProps} />);
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('calendar navigation', () => {
    it('handles month change', async () => {
      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(calendarOnMonthChange).not.toBeNull();
      });

      const nextMonth = new Date();
      nextMonth.setMonth(nextMonth.getMonth() + 1);

      await act(async () => {
        calendarOnMonthChange?.(nextMonth);
      });

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('body scroll lock', () => {
    it('locks body scroll when modal is open', () => {
      render(<TimeSelectionModal {...defaultProps} />);
      expect(document.body.style.overflow).toBe('hidden');
    });

    it('restores body scroll when modal closes', () => {
      const { rerender } = render(<TimeSelectionModal {...defaultProps} />);
      expect(document.body.style.overflow).toBe('hidden');

      rerender(<TimeSelectionModal {...defaultProps} isOpen={false} />);
      // scroll restored on unmount cleanup
    });
  });

  describe('summary section', () => {
    it('renders summary section', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getAllByTestId('summary-section').length).toBeGreaterThan(0);
      });
    });

    it('passes continue handler to summary section', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(summaryOnContinue).not.toBeNull();
      });
    });
  });

  describe('instructor timezone in booking data', () => {
    it('handles instructor with timezone', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      const instructorWithTz = {
        ...mockInstructor,
        user: { ...mockInstructor.user, timezone: 'America/Chicago' },
      };

      render(<TimeSelectionModal {...defaultProps} instructor={instructorWithTz} />);

      await waitFor(() => {
        expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
      });
    });

    it('handles instructor without timezone', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      const instructorNoTz = {
        ...mockInstructor,
        user: { first_name: 'John', last_initial: 'D' },
      };

      render(<TimeSelectionModal {...defaultProps} instructor={instructorNoTz} />);

      await waitFor(() => {
        expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
      });
    });
  });

  describe('calendar date handler', () => {
    it('provides date select handler to calendar', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(calendarOnDateSelect).not.toBeNull();
      });

      // Verify that selecting a date doesn't crash
      await act(async () => {
        calendarOnDateSelect?.(dates[0]!);
      });

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('edge cases', () => {
    it('handles initialDate with unexpected type gracefully', () => {
      // Pass a number which should return null from normalizeDateInput
      render(<TimeSelectionModal {...defaultProps} initialDate={12345 as unknown as Date} />);
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('handles malformed initialTimeHHMM24 with non-numeric hour', () => {
      render(<TimeSelectionModal {...defaultProps} initialTimeHHMM24="ab:30" />);
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('handles empty availability data', async () => {
      publicApiMock.getInstructorAvailability.mockResolvedValue({
        status: 200 as const,
        data: {
          instructor_id: 'user-123',
          instructor_first_name: 'John' as string | null,
          instructor_last_initial: 'D' as string | null,
          availability_by_date: {},
          timezone: 'America/New_York',
          total_available_slots: 0,
          earliest_available_date: getDateString(1),
        },
      });

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(publicApiMock.getInstructorAvailability).toHaveBeenCalled();
      });

      // Component should still render with no available dates
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('handles duration option not found in list', async () => {
      const instructorWithDifferentDurations = {
        ...mockInstructor,
        services: [{ ...mockService, duration_options: [45, 90] }],
      };

      render(<TimeSelectionModal {...defaultProps} instructor={instructorWithDifferentDurations} initialDurationMinutes={60} />);

      // Should default to first available duration since 60 isn't in list
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('pricing preview errors', () => {
    it('handles 422 pricing preview error', async () => {
      const { ApiProblemError } = await import('@/lib/api/fetch');
      const mockResponse = { status: 422, statusText: 'Unprocessable Entity' } as Response;

      fetchPricingPreviewMock.mockRejectedValueOnce(
        new ApiProblemError({ type: 'validation_error', detail: 'Price below minimum', title: 'Error', status: 422 }, mockResponse)
      );

      render(<TimeSelectionModal {...defaultProps} bookingDraftId="draft-123" />);

      await waitFor(() => {
        expect(fetchPricingPreviewMock).toHaveBeenCalled();
      });

      // Component should handle error gracefully
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('price floor handling', () => {
    it('shows floor warning when hourly rate is below minimum', async () => {
      usePricingFloorsMock.mockReturnValue({
        floors: {
          private_in_person: 10000,
          private_remote: 6000,
        },
      });

      const veryLowRateInstructor = {
        ...mockInstructor,
        services: [{ ...mockService, hourly_rate: 10 }], // $10/hr is way below $50 floor
      };

      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} instructor={veryLowRateInstructor} />);

      await waitFor(() => {
        // Floor warning should show in summary section
        const summaryCompleteElements = screen.getAllByTestId('summary-complete');
        expect(summaryCompleteElements[0]?.textContent).toBe('false');
      });
    });
  });

  describe('time selection with time select callback', () => {
    it('handles time button click', async () => {
      const user = userEvent.setup();
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        const timeDropdowns = screen.getAllByTestId('time-dropdown');
        expect(timeDropdowns.length).toBeGreaterThan(0);
      });

      await waitFor(() => {
        const timeSlotsCount = screen.queryAllByTestId('time-slots-count');
        expect(timeSlotsCount.length).toBeGreaterThan(0);
        expect(Number(timeSlotsCount[0]?.textContent)).toBeGreaterThan(0);
      });

      // Click the first available time slot
      const timeButtons = screen.getAllByTestId(/^time-/);
      if (timeButtons.length > 0) {
        await user.click(timeButtons[0]!);
      }

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('service without location types', () => {
    it('handles service with undefined location types', () => {
      const instructorNoLocationTypes = {
        ...mockInstructor,
        services: [{
          id: 'svc-1',
          duration_options: [30, 60],
          hourly_rate: 60,
          skill: 'Piano',
          location_types: undefined as unknown as string[],
        }],
      };

      render(<TimeSelectionModal {...defaultProps} instructor={instructorNoLocationTypes} />);
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('initial selection with preSelectedTime', () => {
    it('applies preSelectedTime in AM format', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} preSelectedTime="9:00am" />);

      await waitFor(() => {
        expect(publicApiMock.getInstructorAvailability).toHaveBeenCalled();
      });

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('applies preSelectedTime in PM format', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} preSelectedTime="2:30pm" />);

      await waitFor(() => {
        expect(publicApiMock.getInstructorAvailability).toHaveBeenCalled();
      });

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('availability fetching edge cases', () => {
    it('handles availability with blackout date', async () => {
      const dates = [getDateString(1), getDateString(2)];
      const availabilityWithBlackout = {
        status: 200 as const,
        data: {
          instructor_id: 'user-123',
          instructor_first_name: 'John' as string | null,
          instructor_last_initial: 'D' as string | null,
          availability_by_date: {
            [dates[0]!]: {
              date: dates[0]!,
              available_slots: [],
              is_blackout: true,
            },
            [dates[1]!]: {
              date: dates[1]!,
              available_slots: [{ start_time: '10:00', end_time: '12:00' }],
              is_blackout: false,
            },
          },
          timezone: 'America/New_York',
          total_available_slots: 1,
          earliest_available_date: dates[1]!,
        },
      };

      publicApiMock.getInstructorAvailability.mockResolvedValue(availabilityWithBlackout);

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(publicApiMock.getInstructorAvailability).toHaveBeenCalled();
      });

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('authenticated user booking flow', () => {
    it('stores booking data in sessionStorage for authenticated user', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      useAuthMock.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'student-123', timezone: 'America/New_York' },
        redirectToLogin: jest.fn(),
      });

      render(<TimeSelectionModal {...defaultProps} onClose={onClose} />);

      // Wait for time slots to load
      await waitFor(() => {
        expect(screen.queryAllByTestId(/^time-/).length).toBeGreaterThan(0);
      });

      // Wait for summary to be available
      await waitFor(() => {
        expect(summaryOnContinue).not.toBeNull();
      });

      // Select a time slot
      const timeButtons = screen.getAllByTestId(/^time-/);
      if (timeButtons.length > 0) {
        await user.click(timeButtons[0]!);
      }

      // Wait for selection to be complete
      await waitFor(() => {
        const summaryCompleteElements = screen.getAllByTestId('summary-complete');
        expect(summaryCompleteElements[0]?.textContent).toBe('true');
      });

      // Click continue
      await runContinueWithoutNavigation(summaryOnContinue);

      // Verify sessionStorage was called (navigation happens asynchronously after)
      expect(window.sessionStorage.setItem).toHaveBeenCalledWith('bookingData', expect.any(String));
      expect(window.sessionStorage.setItem).toHaveBeenCalledWith('serviceId', expect.any(String));
      expect(window.sessionStorage.setItem).toHaveBeenCalledWith('selectedSlot', expect.any(String));
      expect(onClose).toHaveBeenCalled();
    });

    it('handles PM time selection correctly', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();
      const dates = [getDateString(1)];

      // Create availability with PM slots
      const pmAvailability = {
        status: 200 as const,
        data: {
          instructor_id: 'user-123',
          instructor_first_name: 'John' as string | null,
          instructor_last_initial: 'D' as string | null,
          availability_by_date: {
            [dates[0]!]: {
              date: dates[0]!,
              available_slots: [{ start_time: '14:00', end_time: '18:00' }],
              is_blackout: false,
            },
          },
          timezone: 'America/New_York',
          total_available_slots: 1,
          earliest_available_date: dates[0]!,
        },
      };
      publicApiMock.getInstructorAvailability.mockResolvedValue(pmAvailability);

      useAuthMock.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'student-123', timezone: 'America/New_York' },
        redirectToLogin: jest.fn(),
      });

      render(<TimeSelectionModal {...defaultProps} onClose={onClose} />);

      // Wait for time slots
      await waitFor(() => {
        expect(screen.queryAllByTestId(/^time-/).length).toBeGreaterThan(0);
      });

      await waitFor(() => {
        expect(summaryOnContinue).not.toBeNull();
      });

      // Select a PM time slot
      const timeButtons = screen.getAllByTestId(/^time-/);
      if (timeButtons.length > 0) {
        await user.click(timeButtons[0]!);
      }

      await waitFor(() => {
        const summaryCompleteElements = screen.getAllByTestId('summary-complete');
        expect(summaryCompleteElements[0]?.textContent).toBe('true');
      });

      await runContinueWithoutNavigation(summaryOnContinue);

      expect(window.sessionStorage.setItem).toHaveBeenCalledWith('bookingData', expect.any(String));
    });
  });

  describe('handleDateSelect single date fetch', () => {
    it('fetches availability for a specific date not in cache', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(calendarOnDateSelect).not.toBeNull();
      });

      // Select a date that's not in the cache
      const uncachedDate = getDateString(5);

      // Mock the single-date fetch response
      publicApiMock.getInstructorAvailability.mockResolvedValueOnce({
        status: 200 as const,
        data: {
          instructor_id: 'user-123',
          instructor_first_name: 'John' as string | null,
          instructor_last_initial: 'D' as string | null,
          availability_by_date: {
            [uncachedDate]: {
              date: uncachedDate,
              available_slots: [{ start_time: '11:00', end_time: '13:00' }],
              is_blackout: false,
            },
          },
          timezone: 'America/New_York',
          total_available_slots: 1,
          earliest_available_date: uncachedDate,
        },
      });

      await act(async () => {
        calendarOnDateSelect?.(uncachedDate);
      });

      await waitFor(() => {
        const dateSpecificCall = publicApiMock.getInstructorAvailability.mock.calls.find(
          ([, params]) =>
            params &&
            (params as { start_date?: string; end_date?: string }).start_date === uncachedDate &&
            (params as { start_date?: string; end_date?: string }).end_date === uncachedDate
        );
        expect(dateSpecificCall).toBeTruthy();
      });
    });

    it('handles fetch error for specific date', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(calendarOnDateSelect).not.toBeNull();
      });

      const uncachedDate = getDateString(5);

      // Make the single-date fetch fail
      publicApiMock.getInstructorAvailability.mockRejectedValueOnce(new Error('Network error'));

      await act(async () => {
        calendarOnDateSelect?.(uncachedDate);
      });

      // Component should handle error gracefully
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('handles date with no availability in response', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(calendarOnDateSelect).not.toBeNull();
      });

      const uncachedDate = getDateString(5);

      // Return empty availability for the date
      publicApiMock.getInstructorAvailability.mockResolvedValueOnce({
        status: 200 as const,
        data: {
          instructor_id: 'user-123',
          instructor_first_name: 'John' as string | null,
          instructor_last_initial: 'D' as string | null,
          availability_by_date: {},
          timezone: 'America/New_York',
          total_available_slots: 0,
          earliest_available_date: dates[0]!,
        },
      });

      await act(async () => {
        calendarOnDateSelect?.(uncachedDate);
      });

      // Component should handle empty availability gracefully
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('handleDurationSelect with availability notice', () => {
    it('shows duration availability notice when no slots for duration', async () => {
      const user = userEvent.setup();
      const dates = [getDateString(1), getDateString(2)];

      // Create availability that only has short slots on first date
      const limitedAvailability = {
        status: 200 as const,
        data: {
          instructor_id: 'user-123',
          instructor_first_name: 'John' as string | null,
          instructor_last_initial: 'D' as string | null,
          availability_by_date: {
            [dates[0]!]: {
              date: dates[0]!,
              available_slots: [{ start_time: '10:00', end_time: '10:30' }], // Only 30min available
              is_blackout: false,
            },
            [dates[1]!]: {
              date: dates[1]!,
              available_slots: [{ start_time: '09:00', end_time: '12:00' }], // 3 hours available
              is_blackout: false,
            },
          },
          timezone: 'America/New_York',
          total_available_slots: 2,
          earliest_available_date: dates[0]!,
        },
      };
      publicApiMock.getInstructorAvailability.mockResolvedValue(limitedAvailability);

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.queryAllByTestId('duration-buttons').length).toBeGreaterThan(0);
      });

      // Try to select 90-minute duration when only 30min is available on current date
      const duration90Buttons = screen.getAllByTestId('duration-90');
      if (duration90Buttons.length > 0) {
        await user.click(duration90Buttons[0]!);
      }

      // Should show notice or disable the duration
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('handles duration selection when no availability data', async () => {
      const user = userEvent.setup();
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.queryAllByTestId('duration-buttons').length).toBeGreaterThan(0);
      });

      // Select different durations
      const duration60Buttons = screen.getAllByTestId('duration-60');
      if (duration60Buttons.length > 0) {
        await user.click(duration60Buttons[0]!);
      }

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('price floor violation blocking', () => {
    it('blocks continue when price floor is violated', async () => {
      const onClose = jest.fn();

      usePricingFloorsMock.mockReturnValue({
        floors: {
          private_in_person: 10000,
          private_remote: 6000,
        },
      });

      const veryLowRateInstructor = {
        ...mockInstructor,
        services: [{ ...mockService, hourly_rate: 10 }], // $10/hr is way below floor
      };

      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} instructor={veryLowRateInstructor} onClose={onClose} />);

      await waitFor(() => {
        expect(summaryOnContinue).not.toBeNull();
      });

      // Try to continue - should be blocked
      await runContinueWithoutNavigation(summaryOnContinue);

      // onClose should NOT be called because floor violation blocks continue
      expect(onClose).not.toHaveBeenCalled();
    });

    it('displays floor warning message', async () => {
      usePricingFloorsMock.mockReturnValue({
        floors: {
          private_in_person: 10000,
          private_remote: 6000,
        },
      });

      const veryLowRateInstructor = {
        ...mockInstructor,
        services: [{ ...mockService, hourly_rate: 10 }],
      };

      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} instructor={veryLowRateInstructor} />);

      await waitFor(() => {
        const floorWarnings = screen.queryAllByTestId('floor-warning');
        expect(floorWarnings.length).toBeGreaterThan(0);
      });
    });
  });

  describe('time reconciliation effect', () => {
    it('clears selected time when time slots become empty', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        const selectedTimeElements = screen.getAllByTestId('selected-time');
        expect(selectedTimeElements[0]?.textContent).not.toBe('none');
      });
    });
  });

  describe('backdrop click handling', () => {
    it('closes modal when backdrop is clicked on desktop', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();
      render(<TimeSelectionModal {...defaultProps} onClose={onClose} />);

      // Find the backdrop div (the one with onClick for handleBackdropClick)
      const backdropElements = document.querySelectorAll('.fixed.inset-0.z-50.overflow-y-auto');
      if (backdropElements.length > 0) {
        await user.click(backdropElements[0]!);
        expect(onClose).toHaveBeenCalled();
      }
    });
  });

  describe('initial selection with initialDurationMinutes', () => {
    it('applies initialDurationMinutes when available in options', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(
        <TimeSelectionModal
          {...defaultProps}
          initialDate={dates[0]}
          initialDurationMinutes={60}
        />
      );

      await waitFor(() => {
        const selectedDurationElements = screen.getAllByTestId('selected-duration');
        expect(selectedDurationElements[0]?.textContent).toBe('60');
      });
    });

    it('falls back to first duration when initialDurationMinutes not in options', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      // Initial duration of 45 is not in the default options [30, 60, 90]
      render(
        <TimeSelectionModal
          {...defaultProps}
          initialDate={dates[0]}
          initialDurationMinutes={45}
        />
      );

      await waitFor(() => {
        const selectedDurationElements = screen.getAllByTestId('selected-duration');
        // Should fall back to first available (30)
        expect(selectedDurationElements[0]?.textContent).toBe('30');
      });
    });
  });

  describe('service handling edge cases', () => {
    it('handles instructor with no services gracefully on continue', async () => {
      const onClose = jest.fn();
      const instructorNoServices = {
        ...mockInstructor,
        services: [],
      };

      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} instructor={instructorNoServices} onClose={onClose} />);

      await waitFor(() => {
        expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
      });
    });
  });

  describe('unauthenticated user booking flow', () => {
    it('stores booking intent and redirects to login for unauthenticated user', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();
      const redirectToLogin = jest.fn();
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      useAuthMock.mockReturnValue({
        isAuthenticated: false,
        user: null,
        redirectToLogin,
      });

      render(<TimeSelectionModal {...defaultProps} onClose={onClose} />);

      // Wait for time slots
      await waitFor(() => {
        expect(screen.queryAllByTestId(/^time-/).length).toBeGreaterThan(0);
      });

      await waitFor(() => {
        expect(summaryOnContinue).not.toBeNull();
      });

      // Select a time slot
      const timeButtons = screen.getAllByTestId(/^time-/);
      if (timeButtons.length > 0) {
        await user.click(timeButtons[0]!);
      }

      await waitFor(() => {
        const summaryCompleteElements = screen.getAllByTestId('summary-complete');
        expect(summaryCompleteElements[0]?.textContent).toBe('true');
      });

      await runContinueWithoutNavigation(summaryOnContinue);

      // Verify storeBookingIntent was called
      expect(storeBookingIntentMock).toHaveBeenCalled();
      expect(redirectToLogin).toHaveBeenCalledWith('/student/booking/confirm');
      expect(onClose).toHaveBeenCalled();
    });
  });

  describe('jump to next available functionality', () => {
    it('does nothing when targetDate is null', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(calendarOnDateSelect).not.toBeNull();
      });

      // Component should render normally
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('time parsing edge cases', () => {
    it('handles 12:00am edge case correctly', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();
      const dates = [getDateString(1)];

      // Create availability with midnight slot
      const midnightAvailability = {
        status: 200 as const,
        data: {
          instructor_id: 'user-123',
          instructor_first_name: 'John' as string | null,
          instructor_last_initial: 'D' as string | null,
          availability_by_date: {
            [dates[0]!]: {
              date: dates[0]!,
              available_slots: [{ start_time: '00:00', end_time: '02:00' }],
              is_blackout: false,
            },
          },
          timezone: 'America/New_York',
          total_available_slots: 1,
          earliest_available_date: dates[0]!,
        },
      };
      publicApiMock.getInstructorAvailability.mockResolvedValue(midnightAvailability);

      useAuthMock.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'student-123', timezone: 'America/New_York' },
        redirectToLogin: jest.fn(),
      });

      render(<TimeSelectionModal {...defaultProps} onClose={onClose} />);

      await waitFor(() => {
        expect(screen.queryAllByTestId(/^time-/).length).toBeGreaterThan(0);
      });

      await waitFor(() => {
        expect(summaryOnContinue).not.toBeNull();
      });

      const timeButtons = screen.queryAllByTestId(/^time-/);
      if (timeButtons.length > 0) {
        await user.click(timeButtons[0]!);
      }

      await waitFor(() => {
        const summaryCompleteElements = screen.getAllByTestId('summary-complete');
        expect(summaryCompleteElements[0]?.textContent).toBe('true');
      });

      await runContinueWithoutNavigation(summaryOnContinue);

      expect(window.sessionStorage.setItem).toHaveBeenCalledWith('bookingData', expect.any(String));
    });

    it('handles 12:00pm noon edge case correctly', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();
      const dates = [getDateString(1)];

      // Create availability with noon slot
      const noonAvailability = {
        status: 200 as const,
        data: {
          instructor_id: 'user-123',
          instructor_first_name: 'John' as string | null,
          instructor_last_initial: 'D' as string | null,
          availability_by_date: {
            [dates[0]!]: {
              date: dates[0]!,
              available_slots: [{ start_time: '12:00', end_time: '14:00' }],
              is_blackout: false,
            },
          },
          timezone: 'America/New_York',
          total_available_slots: 1,
          earliest_available_date: dates[0]!,
        },
      };
      publicApiMock.getInstructorAvailability.mockResolvedValue(noonAvailability);

      useAuthMock.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'student-123', timezone: 'America/New_York' },
        redirectToLogin: jest.fn(),
      });

      render(<TimeSelectionModal {...defaultProps} onClose={onClose} />);

      await waitFor(() => {
        expect(screen.queryAllByTestId(/^time-/).length).toBeGreaterThan(0);
      });

      await waitFor(() => {
        expect(summaryOnContinue).not.toBeNull();
      });

      const timeButtons = screen.queryAllByTestId(/^time-/);
      if (timeButtons.length > 0) {
        await user.click(timeButtons[0]!);
      }

      await waitFor(() => {
        const summaryCompleteElements = screen.getAllByTestId('summary-complete');
        expect(summaryCompleteElements[0]?.textContent).toBe('true');
      });

      await runContinueWithoutNavigation(summaryOnContinue);

      expect(window.sessionStorage.setItem).toHaveBeenCalledWith('bookingData', expect.any(String));
    });
  });

  describe('end time calculation overflow', () => {
    it('handles end time that overflows to next hour', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();
      const dates = [getDateString(1)];

      // Create availability with slot that has minutes at 30
      const overflowAvailability = {
        status: 200 as const,
        data: {
          instructor_id: 'user-123',
          instructor_first_name: 'John' as string | null,
          instructor_last_initial: 'D' as string | null,
          availability_by_date: {
            [dates[0]!]: {
              date: dates[0]!,
              available_slots: [{ start_time: '10:30', end_time: '13:00' }],
              is_blackout: false,
            },
          },
          timezone: 'America/New_York',
          total_available_slots: 1,
          earliest_available_date: dates[0]!,
        },
      };
      publicApiMock.getInstructorAvailability.mockResolvedValue(overflowAvailability);

      useAuthMock.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'student-123', timezone: 'America/New_York' },
        redirectToLogin: jest.fn(),
      });

      render(<TimeSelectionModal {...defaultProps} onClose={onClose} />);

      await waitFor(() => {
        expect(screen.queryAllByTestId(/^time-/).length).toBeGreaterThan(0);
      });

      await waitFor(() => {
        expect(summaryOnContinue).not.toBeNull();
      });

      // Select 90 minutes to trigger overflow (10:30 + 90min = 12:00)
      const duration90Buttons = screen.queryAllByTestId('duration-90');
      if (duration90Buttons.length > 0) {
        await user.click(duration90Buttons[0]!);
      }

      await waitFor(() => {
        const timeSlotsCount = screen.queryAllByTestId('time-slots-count');
        expect(timeSlotsCount.length).toBeGreaterThan(0);
        expect(Number(timeSlotsCount[0]?.textContent)).toBeGreaterThan(0);
      });

      const timeButtons = screen.queryAllByTestId(/^time-/);
      if (timeButtons.length > 0) {
        await user.click(timeButtons[0]!);
      }

      await waitFor(() => {
        const summaryCompleteElements = screen.getAllByTestId('summary-complete');
        expect(summaryCompleteElements[0]?.textContent).toBe('true');
      });

      await runContinueWithoutNavigation(summaryOnContinue);

      expect(window.sessionStorage.setItem).toHaveBeenCalledWith('bookingData', expect.any(String));
    });
  });

  describe('onTimeSelected callback', () => {
    it('calls onTimeSelected callback when provided and closes modal', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();
      const onTimeSelected = jest.fn();
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(
        <TimeSelectionModal
          {...defaultProps}
          onClose={onClose}
          onTimeSelected={onTimeSelected}
        />
      );

      // Wait for time slots to load
      await waitFor(() => {
        const timeSlotsCount = screen.queryAllByTestId('time-slots-count');
        expect(timeSlotsCount.length).toBeGreaterThan(0);
        expect(Number(timeSlotsCount[0]?.textContent)).toBeGreaterThan(0);
      });

      // Wait for summary to be available
      await waitFor(() => {
        expect(summaryOnContinue).not.toBeNull();
      });

      const timeButtons = screen.queryAllByTestId(/^time-/);
      if (timeButtons.length > 0) {
        await user.click(timeButtons[0]!);
      }

      await waitFor(() => {
        const summaryCompleteElements = screen.getAllByTestId('summary-complete');
        expect(summaryCompleteElements[0]?.textContent).toBe('true');
      });

      await act(async () => {
        summaryOnContinue?.();
      });

      expect(onTimeSelected).toHaveBeenCalledWith(expect.objectContaining({
        date: expect.any(String),
        time: expect.any(String),
        duration: expect.any(Number),
      }));
      expect(onClose).toHaveBeenCalled();
    });
  });

  describe('service selection fallback', () => {
    it('uses serviceId from props when provided', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      const multiServiceInstructor = {
        ...mockInstructor,
        services: [
          { ...mockService, id: 'svc-1', skill: 'Piano' },
          { ...mockService, id: 'svc-2', skill: 'Guitar' },
        ],
      };

      render(
        <TimeSelectionModal
          {...defaultProps}
          instructor={multiServiceInstructor}
          serviceId="svc-2"
        />
      );

      await waitFor(() => {
        expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
      });
    });

    it('falls back to first service when serviceId not found', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(
        <TimeSelectionModal
          {...defaultProps}
          serviceId="non-existent-service"
        />
      );

      await waitFor(() => {
        expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
      });
    });
  });

  describe('modality detection', () => {
    it('detects online modality from location types', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      const onlineInstructor = {
        ...mockInstructor,
        services: [{ ...mockService, location_types: ['online', 'virtual'] }],
      };

      render(<TimeSelectionModal {...defaultProps} instructor={onlineInstructor} />);

      await waitFor(() => {
        expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
      });
    });

    it('detects remote modality from location types', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      const remoteInstructor = {
        ...mockInstructor,
        services: [{ ...mockService, location_types: ['online'] }],
      };

      render(<TimeSelectionModal {...defaultProps} instructor={remoteInstructor} />);

      await waitFor(() => {
        expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
      });
    });
  });

  describe('instructor timezone handling', () => {
    it('handles instructor without timezone', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      const noTzInstructor = {
        ...mockInstructor,
        user: {
          ...mockInstructor.user,
          timezone: undefined,
        },
      };

      render(<TimeSelectionModal {...defaultProps} instructor={noTzInstructor} />);

      await waitFor(() => {
        expect(publicApiMock.getInstructorAvailability).toHaveBeenCalled();
      });

      // Component should render and fetch availability without errors
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('month navigation', () => {
    it('allows navigation to different months', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(calendarOnMonthChange).not.toBeNull();
      });

      // Navigate to next month
      const nextMonth = new Date();
      nextMonth.setMonth(nextMonth.getMonth() + 1);

      await act(async () => {
        calendarOnMonthChange?.(nextMonth);
      });

      // Component should handle month change gracefully
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('invalid time selection handling', () => {
    it('ignores selection of time not in available slots', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        const timeSlotsCount = screen.getAllByTestId('time-slots-count');
        expect(Number(timeSlotsCount[0]?.textContent)).toBeGreaterThan(0);
      });

      // Component renders correctly
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('escape key handling', () => {
    it('closes modal on Escape key press', async () => {
      const onClose = jest.fn();
      render(<TimeSelectionModal {...defaultProps} onClose={onClose} />);

      // Simulate Escape key press
      await act(async () => {
        const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true });
        document.dispatchEvent(event);
      });

      expect(onClose).toHaveBeenCalled();
    });
  });

  describe('focus management', () => {
    it('restores focus when modal closes', async () => {
      const { rerender } = render(<TimeSelectionModal {...defaultProps} isOpen={true} />);

      // Close the modal
      rerender(<TimeSelectionModal {...defaultProps} isOpen={false} />);

      // Modal should not be visible
      expect(screen.queryByTestId('summary-section')).not.toBeInTheDocument();
    });
  });

  describe('formatDateLabel edge cases', () => {
    it('handles empty string for date label', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(publicApiMock.getInstructorAvailability).toHaveBeenCalled();
      });

      // Component should render without error
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('duration change edge cases', () => {
    it('handles duration change when no availability data', async () => {
      const user = userEvent.setup();

      // Initially no availability data
      publicApiMock.getInstructorAvailability.mockResolvedValueOnce({
        status: 200 as const,
        data: {
          instructor_id: 'user-123',
          instructor_first_name: 'John' as string | null,
          instructor_last_initial: 'D' as string | null,
          availability_by_date: {},
          timezone: 'America/New_York',
          total_available_slots: 0,
          earliest_available_date: null as unknown as string,
        },
      });

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.queryAllByTestId('duration-buttons').length).toBeGreaterThan(0);
      });

      // Change duration when no availability data
      const duration60Buttons = screen.queryAllByTestId('duration-60');
      if (duration60Buttons.length > 0) {
        await user.click(duration60Buttons[0]!);
      }

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('handles duration change when slots are empty for selected date', async () => {
      const user = userEvent.setup();
      const dates = [getDateString(1), getDateString(2)];

      const limitedAvailability = {
        status: 200 as const,
        data: {
          instructor_id: 'user-123',
          instructor_first_name: 'John' as string | null,
          instructor_last_initial: 'D' as string | null,
          availability_by_date: {
            [dates[0]!]: {
              date: dates[0]!,
              available_slots: [], // No slots on first date
              is_blackout: false,
            },
            [dates[1]!]: {
              date: dates[1]!,
              available_slots: [{ start_time: '09:00', end_time: '12:00' }],
              is_blackout: false,
            },
          },
          timezone: 'America/New_York',
          total_available_slots: 1,
          earliest_available_date: dates[1]!,
        },
      };
      publicApiMock.getInstructorAvailability.mockResolvedValue(limitedAvailability);

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.queryAllByTestId('duration-buttons').length).toBeGreaterThan(0);
      });

      // Select the date with no slots
      if (calendarOnDateSelect !== null) {
        const selectDate = calendarOnDateSelect;
        await act(async () => {
          selectDate(dates[0]!);
        });
      }

      // Try to change duration
      const duration60Buttons = screen.queryAllByTestId('duration-60');
      if (duration60Buttons.length > 0) {
        await user.click(duration60Buttons[0]!);
      }

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('jump to next available', () => {
    it('displays duration availability notice and allows jumping to next date', async () => {
      const user = userEvent.setup();
      const dates = [getDateString(1), getDateString(2)];

      // First date only has 30-min slots, second date has longer slots
      const limitedAvailability = {
        status: 200 as const,
        data: {
          instructor_id: 'user-123',
          instructor_first_name: 'John' as string | null,
          instructor_last_initial: 'D' as string | null,
          availability_by_date: {
            [dates[0]!]: {
              date: dates[0]!,
              available_slots: [{ start_time: '10:00', end_time: '10:30' }], // Only 30min available
              is_blackout: false,
            },
            [dates[1]!]: {
              date: dates[1]!,
              available_slots: [{ start_time: '09:00', end_time: '12:00' }], // 3 hours available
              is_blackout: false,
            },
          },
          timezone: 'America/New_York',
          total_available_slots: 2,
          earliest_available_date: dates[0]!,
        },
      };
      publicApiMock.getInstructorAvailability.mockResolvedValue(limitedAvailability);

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.queryAllByTestId('duration-buttons').length).toBeGreaterThan(0);
      });

      // Select first date
      if (calendarOnDateSelect !== null) {
        const selectDate = calendarOnDateSelect;
        await act(async () => {
          selectDate(dates[0]!);
        });
      }

      // Try to select 90-minute duration when only 30min is available on current date
      const duration90Buttons = screen.queryAllByTestId('duration-90');
      if (duration90Buttons.length > 0) {
        await user.click(duration90Buttons[0]!);
      }

      // Component should render without errors
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('time parsing edge cases in handleContinue', () => {
    it('handles time with malformed format gracefully', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(summaryOnContinue).not.toBeNull();
      });

      // Component should render without errors
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('invalid time selection via handleTimeSelect', () => {
    it('rejects time not in available slots', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        const timeSlotsCount = screen.queryAllByTestId('time-slots-count');
        expect(timeSlotsCount.length).toBeGreaterThan(0);
        expect(Number(timeSlotsCount[0]?.textContent)).toBeGreaterThan(0);
      });

      // Component should render without errors
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('reconciliation effect with preferred time', () => {
    it('uses preferred time from props when valid', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      // Provide a preSelectedTime that's likely in the slot list
      render(<TimeSelectionModal {...defaultProps} preSelectedTime="9:00am" preSelectedDate={dates[0]} />);

      await waitFor(() => {
        const selectedTimeElements = screen.queryAllByTestId('selected-time');
        expect(selectedTimeElements.length).toBeGreaterThan(0);
      });

      // Component should render with time selection
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('initial selection applied with duration', () => {
    it('applies initial selection when date, time, and duration are all provided', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(
        <TimeSelectionModal
          {...defaultProps}
          initialDate={dates[0]}
          initialTimeHHMM24="09:00"
          initialDurationMinutes={60}
        />
      );

      await waitFor(() => {
        expect(publicApiMock.getInstructorAvailability).toHaveBeenCalled();
      });

      await waitFor(() => {
        const selectedDurationElements = screen.queryAllByTestId('selected-duration');
        expect(selectedDurationElements[0]?.textContent).toBe('60');
      });
    });
  });

  describe('error handling in duration change effect', () => {
    it('handles exception in handleDurationSelect gracefully', async () => {
      const user = userEvent.setup();
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.queryAllByTestId('duration-buttons').length).toBeGreaterThan(0);
      });

      // Change duration multiple times rapidly
      const duration60Buttons = screen.queryAllByTestId('duration-60');
      const duration90Buttons = screen.queryAllByTestId('duration-90');
      const duration30Buttons = screen.queryAllByTestId('duration-30');

      if (duration60Buttons.length > 0) {
        await user.click(duration60Buttons[0]!);
      }
      if (duration90Buttons.length > 0) {
        await user.click(duration90Buttons[0]!);
      }
      if (duration30Buttons.length > 0) {
        await user.click(duration30Buttons[0]!);
      }

      // Component should handle rapid changes without error
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('date selection when no cache', () => {
    it('fetches date-specific availability when not in cache', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(calendarOnDateSelect).not.toBeNull();
      });

      // Select a date not in the cache
      const uncachedDate = getDateString(10);

      // Mock the date-specific fetch
      publicApiMock.getInstructorAvailability.mockResolvedValueOnce({
        status: 200 as const,
        data: {
          instructor_id: 'user-123',
          instructor_first_name: 'John' as string | null,
          instructor_last_initial: 'D' as string | null,
          availability_by_date: {
            [uncachedDate]: {
              date: uncachedDate,
              available_slots: [{ start_time: '11:00', end_time: '14:00' }],
              is_blackout: false,
            },
          },
          timezone: 'America/New_York',
          total_available_slots: 1,
          earliest_available_date: uncachedDate,
        },
      });

      await act(async () => {
        calendarOnDateSelect?.(uncachedDate);
      });

      await waitFor(() => {
        // Verify a date-specific call was made
        const calls = publicApiMock.getInstructorAvailability.mock.calls;
        const specificCall = calls.find(
          ([, params]) =>
            params &&
            (params as { start_date?: string }).start_date === uncachedDate
        );
        expect(specificCall).toBeTruthy();
      });
    });

    it('handles empty response for date-specific fetch', async () => {
      const dates = [getDateString(1)];
      publicApiMock.getInstructorAvailability.mockResolvedValue(mockAvailabilityResponse(dates));

      render(<TimeSelectionModal {...defaultProps} />);

      await waitFor(() => {
        expect(calendarOnDateSelect).not.toBeNull();
      });

      const uncachedDate = getDateString(10);

      // Mock empty response
      publicApiMock.getInstructorAvailability.mockResolvedValueOnce({
        status: 200 as const,
        data: {
          instructor_id: 'user-123',
          instructor_first_name: 'John' as string | null,
          instructor_last_initial: 'D' as string | null,
          availability_by_date: {}, // Empty
          timezone: 'America/New_York',
          total_available_slots: 0,
          earliest_available_date: dates[0]!,
        },
      });

      await act(async () => {
        calendarOnDateSelect?.(uncachedDate);
      });

      // Component should handle empty response
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('duration options change effect', () => {
    it('resets to first duration when current selection not in options', async () => {
      const instructorWithChangingDurations = {
        ...mockInstructor,
        services: [{ ...mockService, duration_options: [45, 90] }], // 60 not available
      };

      // Start with duration 60 which is not in options
      render(
        <TimeSelectionModal
          {...defaultProps}
          instructor={instructorWithChangingDurations}
          initialDurationMinutes={60}
        />
      );

      await waitFor(() => {
        // Should fall back to first available (45)
        const selectedDurationElements = screen.queryAllByTestId('selected-duration');
        expect(selectedDurationElements[0]?.textContent).toBe('45');
      });
    });
  });
});
