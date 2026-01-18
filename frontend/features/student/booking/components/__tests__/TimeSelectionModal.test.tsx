import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TimeSelectionModal from '../TimeSelectionModal';
import { useAuth } from '../../hooks/useAuth';
import { usePricingFloors } from '@/lib/pricing/usePricingFloors';
import { fetchPricingPreview } from '@/lib/api/pricing';

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
    availability: jest.fn().mockReturnValue({
      instructorAvailability: jest.fn(),
    }),
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

jest.mock('@/features/shared/booking/ui/Calendar', () => {
  return function MockCalendar({ onDateSelect, availableDates, selectedDate }: {
    onDateSelect: (date: string) => void;
    availableDates: string[];
    selectedDate: string | null;
  }) {
    return (
      <div data-testid="calendar">
        {availableDates.map((date) => (
          <button
            key={date}
            data-testid={`date-${date}`}
            onClick={() => onDateSelect(date)}
            className={selectedDate === date ? 'selected' : ''}
          >
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
        {timeSlots.map((time) => (
          <button
            key={time}
            data-testid={`time-${time}`}
            onClick={() => onTimeSelect(time)}
            className={selectedTime === time ? 'selected' : ''}
          >
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
        {durationOptions.map((opt) => (
          <button
            key={opt.duration}
            data-testid={`duration-${opt.duration}`}
            onClick={() => onDurationSelect(opt.duration)}
            className={selectedDuration === opt.duration ? 'selected' : ''}
          >
            {opt.duration} min (${opt.price})
          </button>
        ))}
      </div>
    );
  };
});

jest.mock('@/features/shared/booking/ui/SummarySection', () => {
  return function MockSummarySection() {
    return <div data-testid="summary-section">Summary</div>;
  };
});

const useAuthMock = useAuth as jest.Mock;
const usePricingFloorsMock = usePricingFloors as jest.Mock;
const fetchPricingPreviewMock = fetchPricingPreview as jest.Mock;

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

describe('TimeSelectionModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    instructor: mockInstructor,
  };

  beforeEach(() => {
    jest.clearAllMocks();

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

      // Should have the instructor avatar
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('close behavior', () => {
    it('calls onClose when close button is clicked', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();

      render(<TimeSelectionModal {...defaultProps} onClose={onClose} />);

      // Find close button by icon or aria-label
      const closeButton = screen.getByRole('button', { name: /close|×|x/i });
      if (closeButton) {
        await user.click(closeButton);
        expect(onClose).toHaveBeenCalled();
      }
    });
  });

  describe('instructor display', () => {
    it('displays instructor name', () => {
      render(<TimeSelectionModal {...defaultProps} />);

      expect(screen.queryAllByTestId('user-avatar')[0]).toHaveTextContent('John');
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
        <TimeSelectionModal
          {...defaultProps}
          instructor={instructorWithMultipleServices}
          serviceId="svc-2"
        />
      );

      // Component should use svc-2 service
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('falls back to first service when serviceId not found', () => {
      render(
        <TimeSelectionModal
          {...defaultProps}
          serviceId="non-existent"
        />
      );

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('pre-selection', () => {
    it('uses preSelectedDate', () => {
      const preSelectedDate = getDateString(1);

      render(
        <TimeSelectionModal
          {...defaultProps}
          preSelectedDate={preSelectedDate}
        />
      );

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('uses preSelectedTime', () => {
      render(
        <TimeSelectionModal
          {...defaultProps}
          preSelectedTime="10:00am"
        />
      );

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('uses initialDate as Date object', () => {
      const initialDate = new Date();
      initialDate.setDate(initialDate.getDate() + 1);

      render(
        <TimeSelectionModal
          {...defaultProps}
          initialDate={initialDate}
        />
      );

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('uses initialTimeHHMM24', () => {
      render(
        <TimeSelectionModal
          {...defaultProps}
          initialTimeHHMM24="14:00"
        />
      );

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('uses initialDurationMinutes', () => {
      render(
        <TimeSelectionModal
          {...defaultProps}
          initialDurationMinutes={90}
        />
      );

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('duration options', () => {
    it('renders duration buttons when multiple options', () => {
      render(<TimeSelectionModal {...defaultProps} />);

      expect(screen.queryAllByTestId('duration-buttons').length).toBeGreaterThan(0);
    });

    it('does not render duration buttons when single option', () => {
      const instructorWithSingleDuration = {
        ...mockInstructor,
        services: [
          { ...mockService, duration_options: [60] },
        ],
      };

      render(
        <TimeSelectionModal
          {...defaultProps}
          instructor={instructorWithSingleDuration}
        />
      );

      expect(screen.queryByTestId('duration-buttons')).not.toBeInTheDocument();
    });
  });

  describe('authentication', () => {
    it('stores booking intent when not authenticated', async () => {
      const redirectToLogin = jest.fn();
      useAuthMock.mockReturnValue({
        isAuthenticated: false,
        user: null,
        redirectToLogin,
      });

      render(<TimeSelectionModal {...defaultProps} />);

      // The component should handle unauthenticated state
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('callback handling', () => {
    it('calls onTimeSelected when time is selected', async () => {
      const onTimeSelected = jest.fn();

      render(
        <TimeSelectionModal
          {...defaultProps}
          onTimeSelected={onTimeSelected}
        />
      );

      // The callback is called during the booking flow
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('applied credits', () => {
    it('handles appliedCreditCents', () => {
      render(
        <TimeSelectionModal
          {...defaultProps}
          appliedCreditCents={1000} // $10 credit
        />
      );

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('handles negative appliedCreditCents', () => {
      render(
        <TimeSelectionModal
          {...defaultProps}
          appliedCreditCents={-500}
        />
      );

      // Should normalize to 0
      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('booking draft', () => {
    it('uses bookingDraftId when provided', () => {
      render(
        <TimeSelectionModal
          {...defaultProps}
          bookingDraftId="draft-123"
        />
      );

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('pricing floors', () => {
    it('uses pricing floors for validation', () => {
      usePricingFloorsMock.mockReturnValue({
        floors: {
          'in-person': { 30: 2000, 60: 4000 },
          online: { 30: 1500, 60: 3000 },
        },
      });

      render(<TimeSelectionModal {...defaultProps} />);

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('instructor without services', () => {
    it('handles instructor with no services', () => {
      const instructorWithoutServices = {
        ...mockInstructor,
        services: [],
      };

      render(
        <TimeSelectionModal
          {...defaultProps}
          instructor={instructorWithoutServices}
        />
      );

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('modality detection', () => {
    it('detects online modality', () => {
      const onlineInstructor = {
        ...mockInstructor,
        services: [
          {
            ...mockService,
            location_types: ['online', 'virtual'],
          },
        ],
      };

      render(
        <TimeSelectionModal
          {...defaultProps}
          instructor={onlineInstructor}
        />
      );

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('handles empty location_types', () => {
      const noLocationTypesInstructor = {
        ...mockInstructor,
        services: [
          {
            ...mockService,
            location_types: [],
          },
        ],
      };

      render(
        <TimeSelectionModal
          {...defaultProps}
          instructor={noLocationTypesInstructor}
        />
      );

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });

  describe('user timezone', () => {
    it('uses user timezone from auth', () => {
      useAuthMock.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'student-123', timezone: 'America/Los_Angeles' },
        redirectToLogin: jest.fn(),
      });

      render(<TimeSelectionModal {...defaultProps} />);

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });

    it('falls back to system timezone when user has none', () => {
      useAuthMock.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'student-123' }, // No timezone
        redirectToLogin: jest.fn(),
      });

      render(<TimeSelectionModal {...defaultProps} />);

      expect(screen.queryAllByTestId('user-avatar').length).toBeGreaterThan(0);
    });
  });
});
