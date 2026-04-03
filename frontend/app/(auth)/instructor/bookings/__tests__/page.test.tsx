import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import InstructorBookingsPage from '../page';
import { useInstructorBookings } from '@/hooks/queries/useInstructorBookings';

const replaceMock = jest.fn();
let currentTabParam: string | null = null;
let embedded = false;

const searchParamsMock = {
  get: jest.fn((key: string) => {
    if (key === 'tab') {
      return currentTabParam;
    }

    if (key === 'panel' && embedded) {
      return 'bookings';
    }

    return null;
  }),
  toString: jest.fn(() => {
    const params = new URLSearchParams();

    if (embedded) {
      params.set('panel', 'bookings');
    }

    if (currentTabParam) {
      params.set('tab', currentTabParam);
    }

    return params.toString();
  }),
};

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: replaceMock,
  }),
  useSearchParams: () => searchParamsMock,
}));

jest.mock('@/components/UserProfileDropdown', () => {
  const MockUserProfileDropdown = () => <div data-testid="user-dropdown" />;
  MockUserProfileDropdown.displayName = 'MockUserProfileDropdown';
  return {
    __esModule: true,
    default: MockUserProfileDropdown,
  };
});

jest.mock('../../_embedded/EmbeddedContext', () => ({
  useEmbedded: () => embedded,
}));

jest.mock('@/hooks/queries/useInstructorBookings');

const mockUseInstructorBookings = useInstructorBookings as jest.MockedFunction<
  typeof useInstructorBookings
>;

const emptyBookingsResponse = {
  items: [],
  total: 0,
  page: 1,
  per_page: 50,
  has_next: false,
  has_prev: false,
};

const createBooking = (id: string, firstName: string, lastInitial: string, status: string) => ({
  id,
  booking_date: '2026-03-16',
  start_time: '16:30:00',
  end_time: '17:15:00',
  status,
  service_name: 'Piano',
  duration_minutes: 45,
  location_type: 'student_location',
  location_address: null,
  meeting_location: null,
  student: {
    id: `${id}-student`,
    first_name: firstName,
    last_initial: lastInitial,
  },
});

const createBookingsQueryResult = (items: ReturnType<typeof createBooking>[]) =>
  ({
    data: {
      ...emptyBookingsResponse,
      items,
    },
    isLoading: false,
    isError: false,
    error: null,
    refetch: jest.fn(),
  }) as unknown as ReturnType<typeof useInstructorBookings>;

describe('InstructorBookingsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    currentTabParam = null;
    embedded = false;

    mockUseInstructorBookings.mockImplementation(({ upcoming }) =>
      upcoming
        ? createBookingsQueryResult([createBooking('upcoming-booking', 'Ava', 'M', 'CONFIRMED')])
        : createBookingsQueryResult([createBooking('past-booking', 'Riley', 'T', 'COMPLETED')])
    );
  });

  it('renders separate empty-state headings and subtitles for upcoming and past tabs', async () => {
    const user = userEvent.setup();

    mockUseInstructorBookings.mockImplementation(
      () => createBookingsQueryResult([])
    );

    const { rerender } = render(<InstructorBookingsPage />);

    expect(screen.getByText('No upcoming bookings')).toBeInTheDocument();
    expect(screen.getByText('New bookings will appear here.')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Past' }));
    currentTabParam = 'past';
    rerender(<InstructorBookingsPage />);

    expect(screen.getByText('No completed lessons yet')).toBeInTheDocument();
    expect(screen.getByText('Your completed sessions will appear here.')).toBeInTheDocument();
  });

  it('respects a direct past tab URL on first render', () => {
    currentTabParam = 'past';

    render(<InstructorBookingsPage />);

    expect(screen.getByText('Riley T.')).toBeInTheDocument();
    expect(screen.queryByText('Ava M.')).not.toBeInTheDocument();
  });

  it('syncs the rendered tab when the URL changes without remounting', () => {
    const { rerender } = render(<InstructorBookingsPage />);

    expect(screen.getByText('Ava M.')).toBeInTheDocument();
    expect(screen.queryByText('Riley T.')).not.toBeInTheDocument();

    currentTabParam = 'past';
    rerender(<InstructorBookingsPage />);

    expect(screen.getByText('Riley T.')).toBeInTheDocument();
    expect(screen.queryByText('Ava M.')).not.toBeInTheDocument();
  });

  it('updates the URL when switching tabs', async () => {
    const user = userEvent.setup();

    render(<InstructorBookingsPage />);

    await user.click(screen.getByRole('tab', { name: 'Past' }));

    expect(replaceMock).toHaveBeenCalledWith('/instructor/bookings?tab=past', {
      scroll: false,
    });
  });

  it('renders the active tab underline directly on the divider line', () => {
    render(<InstructorBookingsPage />);

    const upcomingTab = screen.getByRole('tab', { name: 'Upcoming' });
    const pastTab = screen.getByRole('tab', { name: 'Past' });

    expect(upcomingTab).toHaveClass('-mb-px', 'border-b-2', 'border-[#7E22CE]');
    expect(pastTab).toHaveClass('border-transparent');
  });

  it('renders the past tab correctly when embedded in the dashboard panel', () => {
    embedded = true;
    currentTabParam = 'past';

    render(<InstructorBookingsPage />);

    expect(screen.getByText('Riley T.')).toBeInTheDocument();
    expect(screen.queryByText('Ava M.')).not.toBeInTheDocument();
  });

  it('updates the dashboard route when switching tabs in embedded mode', async () => {
    const user = userEvent.setup();
    embedded = true;

    render(<InstructorBookingsPage />);

    await user.click(screen.getByRole('tab', { name: 'Past' }));

    expect(replaceMock).toHaveBeenCalledWith('/instructor/dashboard?panel=bookings&tab=past', {
      scroll: false,
    });
  });
});
