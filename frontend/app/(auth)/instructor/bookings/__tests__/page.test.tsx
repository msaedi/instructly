import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import InstructorBookingsPage from '../page';
import { useInstructorBookings } from '@/hooks/queries/useInstructorBookings';
import { useCompleteBooking, useMarkBookingNoShow } from '@/src/api/services/bookings';

const pushMock = jest.fn();
const replaceMock = jest.fn();
const invalidateQueriesMock = jest.fn();
const searchParamsMock = {
  get: jest.fn(() => null),
  toString: jest.fn(() => ''),
};

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
  }),
  useSearchParams: () => searchParamsMock,
}));

jest.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({
    invalidateQueries: invalidateQueriesMock,
  }),
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
  useEmbedded: () => false,
}));

jest.mock('@/hooks/queries/useInstructorBookings');
jest.mock('@/src/api/services/bookings');

const mockUseInstructorBookings = useInstructorBookings as jest.MockedFunction<typeof useInstructorBookings>;
const mockUseCompleteBooking = useCompleteBooking as jest.MockedFunction<typeof useCompleteBooking>;
const mockUseMarkBookingNoShow = useMarkBookingNoShow as jest.MockedFunction<typeof useMarkBookingNoShow>;

const emptyBookingsResponse = {
  items: [],
  total: 0,
  page: 1,
  per_page: 50,
  has_next: false,
  has_prev: false,
};

describe('Instructor bookings page empty states', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    searchParamsMock.get.mockReturnValue(null);
    searchParamsMock.toString.mockReturnValue('');

    mockUseInstructorBookings.mockImplementation(() => ({
      data: emptyBookingsResponse,
      isLoading: false,
      isError: false,
      error: null,
      refetch: jest.fn(),
    }));

    const mutationMock = {
      mutateAsync: jest.fn(),
      isPending: false,
    };
    mockUseCompleteBooking.mockReturnValue(mutationMock as unknown as ReturnType<typeof useCompleteBooking>);
    mockUseMarkBookingNoShow.mockReturnValue(mutationMock as unknown as ReturnType<typeof useMarkBookingNoShow>);
  });

  it('renders separate empty-state headings and subtitles for upcoming and past tabs', async () => {
    const user = userEvent.setup();

    render(<InstructorBookingsPage />);

    expect(screen.getByText('No upcoming bookings')).toBeInTheDocument();
    expect(screen.getByText('New bookings will appear here.')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Past' }));

    expect(screen.getByText('No completed lessons yet')).toBeInTheDocument();
    expect(screen.getByText('Your completed sessions will appear here.')).toBeInTheDocument();
  });
});
