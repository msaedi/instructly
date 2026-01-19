import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import TimeSelectionModal, { type TimeSelectionModalProps } from '../TimeSelectionModal';
import { publicApi } from '@/features/shared/api/client';

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    getInstructorAvailability: jest.fn(),
  },
}));

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingFloors: () => ({ floors: {} }),
  usePricingConfig: () => ({ config: { student_fee_pct: 0.12 }, isLoading: false, error: null }),
}));

jest.mock('@radix-ui/react-tooltip', () => ({
  Provider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Root: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Trigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Content: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Arrow: () => null,
}));

jest.mock('@/features/student/booking/hooks/useAuth', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    redirectToLogin: jest.fn(),
    user: { timezone: 'America/New_York' },
  }),
  storeBookingIntent: jest.fn(),
}));

jest.mock('@/lib/api/pricing', () => {
  const actual = jest.requireActual('@/lib/api/pricing');
  return {
    ...actual,
    fetchPricingPreview: jest.fn(),
    fetchPricingPreviewQuote: jest.fn(),
    fetchPricingConfig: jest.fn().mockResolvedValue({
      config: {
        student_fee_pct: 0.12,
        instructor_tiers: [],
        price_floor_cents: {} as never,
      },
      updated_at: null,
    }),
  };
});

const availabilityMock = publicApi.getInstructorAvailability as jest.MockedFunction<typeof publicApi.getInstructorAvailability>;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'QueryClientWrapper';
  return Wrapper;
};

const renderWithQueryClient = (ui: React.ReactElement) =>
  render(ui, { wrapper: createWrapper() });

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

const instructor: TimeSelectionModalProps['instructor'] = {
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
      location_types: ['online'],
    },
  ],
};

const baseProps = {
  isOpen: true,
  onClose: jest.fn(),
  instructor,
  serviceId: 'svc-1',
  preSelectedDate: '2030-10-17',
};

describe('TimeSelectionModal duration changes', () => {
  beforeAll(() => {
    jest.spyOn(console, 'info').mockImplementation(() => {});
  });

  afterAll(() => {
    jest.restoreAllMocks();
  });

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

    renderWithQueryClient(<TimeSelectionModal {...baseProps} />);

    await waitFor(() => expect(availabilityMock).toHaveBeenCalled());

    await screen.findAllByText(/9:00am/i);
    await screen.findAllByText(/October 17/i);

    const duration45 = screen.getAllByLabelText(/45 min/)[0];
    if (!duration45) {
      throw new Error('Expected 45 min option to be present');
    }
    fireEvent.click(duration45);

    await waitFor(() => expect(screen.getAllByText(/9:00am/i).length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByText(/October 17/i).length).toBeGreaterThan(0));
    expect(screen.queryByText(/No 45-min slots/)).toBeNull();
  });

  it('renders backend-provided half-hour start times', async () => {
    availabilityMock.mockResolvedValue(
      buildAvailabilityResponse({
        '2030-10-17': {
          available_slots: [{ start_time: '13:30', end_time: '15:30' }],
        },
      })
    );

    renderWithQueryClient(<TimeSelectionModal {...baseProps} />);

    await waitFor(() => expect(availabilityMock).toHaveBeenCalled());
    const timeButtons = await screen.findAllByRole('button', { name: /1:30pm/i });
    const firstHalfHourButton = timeButtons[0];
    if (!firstHalfHourButton) {
      throw new Error('Expected at least one 1:30pm option');
    }
    fireEvent.click(firstHalfHourButton);
    await screen.findByText(/2:00pm/i);
  });

  it('shows half-hour starts for 60-minute duration', async () => {
    availabilityMock.mockResolvedValue(
      buildAvailabilityResponse({
        '2030-10-17': {
          available_slots: [{ start_time: '10:30', end_time: '12:30' }],
        },
      })
    );

    renderWithQueryClient(<TimeSelectionModal {...baseProps} />);

    await waitFor(() => expect(availabilityMock).toHaveBeenCalled());

    const duration60Buttons = screen.getAllByLabelText(/60 min/);
    const duration60 = duration60Buttons[0];
    if (!duration60) {
      throw new Error('Expected 60 min button');
    }
    fireEvent.click(duration60);

    const timeButtons = await screen.findAllByRole('button', { name: /10:30am/i });
    const firstTimeButton = timeButtons[0];
    if (!firstTimeButton) {
      throw new Error('Expected at least one 10:30am option');
    }
    fireEvent.click(firstTimeButton);

    await screen.findAllByText(/10:30am/i);
    expect(screen.queryByText(/10:00am/i)).toBeNull();
  });

  it('keeps windows ending at midnight when building slots', async () => {
    availabilityMock.mockResolvedValue(
      buildAvailabilityResponse({
        '2030-10-17': {
          available_slots: [{ start_time: '17:00', end_time: '00:00' }],
        },
      })
    );

    renderWithQueryClient(<TimeSelectionModal {...baseProps} />);

    await waitFor(() => expect(availabilityMock).toHaveBeenCalled());
    const timeButtons = await screen.findAllByText(/5:00pm/i);
    expect(timeButtons.length).toBeGreaterThan(0);
  });

  it('renders the 11:30pm slot when the window ends at midnight', async () => {
    availabilityMock.mockResolvedValue(
      buildAvailabilityResponse({
        '2030-10-17': {
          available_slots: [{ start_time: '23:30', end_time: '00:00' }],
        },
      })
    );

    renderWithQueryClient(<TimeSelectionModal {...baseProps} />);

    await waitFor(() => expect(availabilityMock).toHaveBeenCalled());
    const timeButtons = await screen.findAllByText(/11:30pm/i);
    expect(timeButtons.length).toBeGreaterThan(0);
  });
});
