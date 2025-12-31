import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import TimeSelectionModal from '../TimeSelectionModal';
import { publicApi } from '@/features/shared/api/client';

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

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    getInstructorAvailability: jest.fn(),
  },
}));

const availabilityMock = publicApi.getInstructorAvailability as jest.MockedFunction<
  typeof publicApi.getInstructorAvailability
>;

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

describe('TimeSelectionModal preselected initialization', () => {
  beforeAll(() => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2030-10-10T12:00:00Z'));
    jest.spyOn(console, 'info').mockImplementation(() => {});
  });

  afterAll(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('preselects initial date/time/duration when provided', async () => {
    availabilityMock.mockResolvedValue({
      status: 200,
      data: {
        instructor_id: 'inst-1',
        instructor_first_name: 'Jordan',
        instructor_last_initial: 'M',
        timezone: 'America/New_York',
        total_available_slots: 2,
        earliest_available_date: '2030-10-18',
        availability_by_date: {
          '2030-10-18': {
            date: '2030-10-18',
            is_blackout: false,
            available_slots: [
              { start_time: '14:00', end_time: '15:00' },
              { start_time: '16:00', end_time: '17:00' },
            ],
          },
        },
      },
    });

    renderWithQueryClient(
      <TimeSelectionModal
        isOpen
        onClose={jest.fn()}
        instructor={{
          user_id: 'inst-1',
          user: { first_name: 'Jordan', last_initial: 'M' },
          services: [
            {
              id: 'svc-1',
              duration_options: [30, 60, 90],
              hourly_rate: 120,
              skill: 'Math Tutoring',
              location_types: ['remote'],
            },
          ],
        }}
        serviceId="svc-1"
        initialDate="2030-10-18"
        initialTimeHHMM24="14:00"
        initialDurationMinutes={60}
      />
    );

    await waitFor(() => expect(availabilityMock).toHaveBeenCalled());

    await waitFor(() => {
      const durationRadios = screen.getAllByRole('radio', { name: /60 min/i }) as HTMLInputElement[];
      expect(durationRadios.some((radio) => radio.checked)).toBe(true);
    });

    const timeButtons = await screen.findAllByRole('button', { name: /2:00pm/i });
    expect(timeButtons.length).toBeGreaterThan(0);

    const selectedDayButtons = await screen.findAllByRole('button', {
      name: '18',
      pressed: true,
    });
    expect(selectedDayButtons.length).toBeGreaterThan(0);
  });

  it('falls back to first slot when preselected time is unavailable (Monday buffer scenario)', async () => {
    // This test simulates the Monday scenario where:
    // - Backend returns availability starting at 10:30 (after 9-10 booking + 30min buffer)
    // - Card preselects 10:00am (which is NOT in the available slots)
    // - Modal should snap to 10:30am (first valid slot)
    availabilityMock.mockResolvedValue({
      status: 200,
      data: {
        instructor_id: 'inst-1',
        instructor_first_name: 'Jordan',
        instructor_last_initial: 'M',
        timezone: 'America/New_York',
        total_available_slots: 1,
        earliest_available_date: '2030-10-18',
        availability_by_date: {
          '2030-10-18': {
            date: '2030-10-18',
            is_blackout: false,
            available_slots: [{ start_time: '10:30', end_time: '12:00' }],
          },
        },
      },
    });

    renderWithQueryClient(
      <TimeSelectionModal
        isOpen
        onClose={jest.fn()}
        instructor={{
          user_id: 'inst-1',
          user: { first_name: 'Jordan', last_initial: 'M' },
          services: [
            {
              id: 'svc-1',
              duration_options: [30, 60, 90],
              hourly_rate: 120,
              skill: 'Math Tutoring',
              location_types: ['remote'],
            },
          ],
        }}
        serviceId="svc-1"
        initialDate="2030-10-18"
        initialTimeHHMM24="10:00"
        initialDurationMinutes={30}
      />
    );

    await waitFor(() => expect(availabilityMock).toHaveBeenCalled());

    // Wait for availability to load
    await screen.findAllByText(/October 18/i);

    // Verify the dropdown button label shows the corrected time (10:30am), not the invalid preselected time (10:00am)
    await waitFor(() => {
      const dropdownButtons = screen.getAllByText(/10:30am/i);
      // Should find at least one button showing 10:30am (the dropdown button)
      expect(dropdownButtons.length).toBeGreaterThan(0);
    });

    // Verify the summary shows the corrected time
    await waitFor(() => {
      const summaryEntries = screen.queryAllByText(/October 18/i);
      const summaryTexts = summaryEntries.map((node) => (node.textContent || '').toLowerCase());
      expect(summaryTexts.some((text) => text.includes('10:30'))).toBe(true);
      expect(summaryTexts.some((text) => text.includes('10:00'))).toBe(false);
    });

    // Verify 10:00am is NOT shown anywhere as a selected time
    expect(screen.queryByText(/10:00am/i)).not.toBeInTheDocument();
  });
});
