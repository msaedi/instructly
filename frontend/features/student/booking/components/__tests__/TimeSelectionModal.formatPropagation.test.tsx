import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TimeSelectionModal from '../TimeSelectionModal';
import { publicApi } from '@/features/shared/api/client';
import { useAuth } from '../../hooks/useAuth';
import { usePricingFloors } from '@/lib/pricing/usePricingFloors';

const pushMock = jest.fn();
const redirectToLoginMock = jest.fn();

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

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

jest.mock('@/hooks/useFocusTrap', () => ({
  useFocusTrap: jest.fn(),
}));

jest.mock('@/hooks/useScrollLock', () => ({
  useScrollLock: jest.fn(),
}));

jest.mock('@/features/shared/booking/ui/Calendar', () => {
  return function MockCalendar({
    availableDates,
    onDateSelect,
  }: {
    availableDates: string[];
    onDateSelect: (date: string) => void;
  }) {
    return (
      <div data-testid="calendar">
        {availableDates.map((date) => (
          <button
            key={date}
            data-testid={`date-${date}`}
            onClick={() => onDateSelect(date)}
          >
            {date}
          </button>
        ))}
      </div>
    );
  };
});

jest.mock('@/features/shared/booking/ui/TimeDropdown', () => {
  return function MockTimeDropdown({
    isVisible,
    timeSlots,
    onTimeSelect,
  }: {
    isVisible: boolean;
    timeSlots: string[];
    onTimeSelect: (time: string) => void;
  }) {
    if (!isVisible) {
      return null;
    }
    return (
      <div data-testid="time-dropdown">
        {timeSlots.map((time) => (
          <button
            key={time}
            data-testid={`time-${time}`}
            onClick={() => onTimeSelect(time)}
          >
            {time}
          </button>
        ))}
      </div>
    );
  };
});

jest.mock('@/features/shared/booking/ui/DurationButtons', () => {
  return function MockDurationButtons({
    durationOptions,
    selectedDuration,
    onDurationSelect,
  }: {
    durationOptions: Array<{ duration: number; price: number }>;
    selectedDuration: number;
    onDurationSelect: (duration: number) => void;
  }) {
    return (
      <div data-testid="duration-buttons">
        {durationOptions.map(({ duration }) => (
          <button
            key={duration}
            data-testid={`duration-${duration}`}
            aria-pressed={selectedDuration === duration}
            onClick={() => onDurationSelect(duration)}
          >
            {duration}
          </button>
        ))}
      </div>
    );
  };
});

jest.mock('@/features/shared/booking/ui/SummarySection', () => {
  return function MockSummarySection({
    isComplete,
    onContinue,
  }: {
    isComplete: boolean;
    onContinue: () => void;
  }) {
    return (
      <div data-testid="summary-section">
        <button data-testid="continue-button" disabled={!isComplete} onClick={onContinue}>
          Continue
        </button>
      </div>
    );
  };
});

const mockedUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;
const mockedUsePricingFloors = usePricingFloors as jest.MockedFunction<typeof usePricingFloors>;
const mockedGetInstructorAvailability = publicApi.getInstructorAvailability as jest.MockedFunction<
  typeof publicApi.getInstructorAvailability
>;

const matchMediaMock = (matches: boolean) =>
  jest.fn().mockImplementation((query: string) => ({
    matches: query === '(min-width: 768px)' ? matches : false,
    media: query,
    onchange: null,
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    addListener: jest.fn(),
    removeListener: jest.fn(),
    dispatchEvent: jest.fn(),
  }));

const availabilityResponse = {
  status: 200 as const,
  data: {
    instructor_id: 'inst-1',
    instructor_first_name: 'Ava',
    instructor_last_initial: 'T.',
    availability_by_date: {
      '2030-01-12': {
        date: '2030-01-12',
        available_slots: [{ start_time: '09:00', end_time: '12:00' }],
        is_blackout: false,
      },
    },
    timezone: 'America/New_York',
    total_available_slots: 1,
    earliest_available_date: '2030-01-12',
  },
};

const singleFormatInstructor = {
  user_id: 'inst-1',
  user: {
    first_name: 'Ava',
    last_initial: 'T.',
    timezone: 'America/New_York',
  },
  services: [
    {
      id: 'svc-online',
      duration_options: [60],
      min_hourly_rate: 60,
      format_prices: [{ format: 'online', hourly_rate: 60 }],
      skill: 'Piano',
    },
  ],
};

const multiFormatInstructor = {
  user_id: 'inst-1',
  user: {
    first_name: 'Ava',
    last_initial: 'T.',
    timezone: 'America/New_York',
  },
  services: [
    {
      id: 'svc-multi',
      duration_options: [60],
      min_hourly_rate: 60,
      format_prices: [
        { format: 'online', hourly_rate: 60 },
        { format: 'student_location', hourly_rate: 95 },
        { format: 'instructor_location', hourly_rate: 80 },
      ],
      skill: 'Piano',
    },
  ],
};

describe('TimeSelectionModal format propagation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: matchMediaMock(true),
    });
    mockedUseAuth.mockReturnValue({
      user: { timezone: 'America/New_York' } as never,
      isAuthenticated: true,
      isLoading: false,
      error: null,
      redirectToLogin: redirectToLoginMock,
      checkAuth: jest.fn(),
    });
    mockedUsePricingFloors.mockReturnValue({
      floors: null,
    } as never);
    mockedGetInstructorAvailability.mockResolvedValue(availabilityResponse);
    sessionStorage.clear();
  });

  it('auto-selects a single format and fetches availability with its exact location_type', async () => {
    render(
      <TimeSelectionModal
        isOpen
        onClose={jest.fn()}
        instructor={singleFormatInstructor}
      />
    );

    await waitFor(() => {
      expect(mockedGetInstructorAvailability).toHaveBeenCalledWith('inst-1', {
        start_date: expect.any(String),
        end_date: expect.any(String),
        location_type: 'online',
      });
    });

    expect(screen.queryAllByTestId('format-selection-required')).toHaveLength(0);
  });

  it('honors an unlocked initialLocationType when it matches an offered format', async () => {
    const user = userEvent.setup();

    render(
      <TimeSelectionModal
        isOpen
        onClose={jest.fn()}
        instructor={multiFormatInstructor}
        initialLocationType="online"
      />
    );

    await waitFor(() => {
      expect(mockedGetInstructorAvailability).toHaveBeenCalledWith('inst-1', {
        start_date: expect.any(String),
        end_date: expect.any(String),
        location_type: 'online',
      });
    });

    const onlineFormatButton = screen.getAllByTestId('format-option-online')[0];
    expect(onlineFormatButton).toBeDefined();
    await user.click(onlineFormatButton!);

    expect(mockedGetInstructorAvailability).toHaveBeenCalledTimes(1);
  });

  it('applies initialLocationType on rerender when the service starts unresolved', async () => {
    const { rerender } = render(
      <TimeSelectionModal
        isOpen
        onClose={jest.fn()}
        instructor={multiFormatInstructor}
      />
    );

    expect(mockedGetInstructorAvailability).not.toHaveBeenCalled();

    rerender(
      <TimeSelectionModal
        isOpen
        onClose={jest.fn()}
        instructor={multiFormatInstructor}
        initialLocationType="online"
      />
    );

    await waitFor(() => {
      expect(mockedGetInstructorAvailability).toHaveBeenCalledWith('inst-1', {
        start_date: expect.any(String),
        end_date: expect.any(String),
        location_type: 'online',
      });
    });
  });

  it('auto-selects a service when a rerender narrows the available formats to one', async () => {
    const multiFormatService = multiFormatInstructor.services[0]!;
    const instructorWithMultipleServices = {
      ...multiFormatInstructor,
      services: [
        multiFormatService,
        {
          id: 'svc-online',
          duration_options: [60],
          min_hourly_rate: 60,
          format_prices: [{ format: 'online', hourly_rate: 60 }],
          skill: 'Piano',
        },
      ],
    };

    const { rerender } = render(
      <TimeSelectionModal
        isOpen
        onClose={jest.fn()}
        instructor={instructorWithMultipleServices}
        serviceId="svc-multi"
      />
    );

    expect(mockedGetInstructorAvailability).not.toHaveBeenCalled();

    rerender(
      <TimeSelectionModal
        isOpen
        onClose={jest.fn()}
        instructor={instructorWithMultipleServices}
        serviceId="svc-online"
      />
    );

    await waitFor(() => {
      expect(mockedGetInstructorAvailability).toHaveBeenCalledWith('inst-1', {
        start_date: expect.any(String),
        end_date: expect.any(String),
        location_type: 'online',
      });
    });
  });

  it('requires a format choice before fetching availability for multi-format services', async () => {
    const user = userEvent.setup();

    render(
      <TimeSelectionModal
        isOpen
        onClose={jest.fn()}
        instructor={multiFormatInstructor}
      />
    );

    expect(screen.getAllByTestId('format-selection-required').length).toBeGreaterThan(0);
    expect(mockedGetInstructorAvailability).not.toHaveBeenCalled();

    const travelFormatButton = screen.getAllByTestId('format-option-student_location')[0];
    expect(travelFormatButton).toBeDefined();
    await user.click(travelFormatButton!);

    await waitFor(() => {
      expect(mockedGetInstructorAvailability).toHaveBeenCalledWith('inst-1', {
        start_date: expect.any(String),
        end_date: expect.any(String),
        location_type: 'student_location',
      });
    });
  });

  it('keeps locked location types, including neutral_location, on downstream flows', async () => {
    render(
      <TimeSelectionModal
        isOpen
        onClose={jest.fn()}
        instructor={multiFormatInstructor}
        initialLocationType="neutral_location"
        lockLocationType
        serviceId="svc-multi"
      />
    );

    await waitFor(() => {
      expect(mockedGetInstructorAvailability).toHaveBeenCalledWith('inst-1', {
        start_date: expect.any(String),
        end_date: expect.any(String),
        location_type: 'neutral_location',
      });
    });

    expect(screen.queryAllByTestId('format-option-online')).toHaveLength(0);
  });

  it('stores metadata.location_type in booking handoff data', async () => {
    const user = userEvent.setup();
    const onClose = jest.fn();

    render(
      <TimeSelectionModal
        isOpen
        onClose={onClose}
        instructor={multiFormatInstructor}
      />
    );

    const travelFormatButton = screen.getAllByTestId('format-option-student_location')[0];
    expect(travelFormatButton).toBeDefined();
    await user.click(travelFormatButton!);

    await waitFor(() => {
      expect(screen.getAllByTestId('date-2030-01-12').length).toBeGreaterThan(0);
    });

    const availableDateButton = screen.getAllByTestId('date-2030-01-12')[0];
    expect(availableDateButton).toBeDefined();
    await user.click(availableDateButton!);

    const selectedTimeButton = screen.getAllByTestId('time-9:00am')[0];
    expect(selectedTimeButton).toBeDefined();
    await user.click(selectedTimeButton!);

    const continueButton = screen.getAllByTestId('continue-button')[0];
    expect(continueButton).toBeDefined();
    await user.click(continueButton!);

    const stored = JSON.parse(sessionStorage.getItem('bookingData') ?? '{}') as {
      metadata?: Record<string, unknown>;
      hourlyRate?: number;
    };

    expect(stored.metadata?.['location_type']).toBe('student_location');
    expect(stored.hourlyRate).toBe(95);
    expect(onClose).toHaveBeenCalled();
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/student/booking/confirm');
    });
  });
});
