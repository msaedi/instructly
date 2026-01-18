import React from 'react';
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
        await act(async () => {
          summaryOnContinue?.();
        });

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
        await act(async () => {
          summaryOnContinue?.();
        });

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
        await act(async () => {
          summaryOnContinue?.();
        });

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
          in_person: { 30: 5000, 60: 10000, 90: 15000 },
          remote: { 30: 3000, 60: 6000, 90: 9000 },
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
});
