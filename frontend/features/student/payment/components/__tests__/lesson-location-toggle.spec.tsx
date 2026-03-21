import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

import PaymentConfirmation from '../PaymentConfirmation';
import { PaymentMethod, PAYMENT_STATUS, type PaymentStatus } from '../../types';
import { BookingType } from '@/features/shared/types/booking';
import { fetchInstructorProfile } from '@/src/api/services/instructors';
import { useServiceAreaCheck } from '@/hooks/useServiceAreaCheck';

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingFloors: () => ({ floors: null, config: { student_fee_pct: 0.12 }, isLoading: false, error: null }),
  usePricingConfig: () => ({ config: { student_fee_pct: 0.12 }, isLoading: false, error: null }),
}));

jest.mock('@/features/shared/api/client', () => ({
  protectedApi: {
    getBookings: jest.fn().mockResolvedValue({ data: { items: [] } }),
  },
}));

jest.mock('@/features/shared/api/http', () => ({
  httpJson: jest.fn().mockResolvedValue({}),
}));

jest.mock('@/lib/apiBase', () => ({
  withApiBase: (path: string) => path,
}));

jest.mock('@/src/api/services/instructors', () => ({
  fetchInstructorProfile: jest.fn(),
}));

jest.mock('@/features/shared/api/schemas/instructorProfile', () => ({
  loadInstructorProfileSchema: jest.fn().mockResolvedValue({ services: [] }),
}));

jest.mock('@/features/student/booking/components/TimeSelectionModal', () => ({
  __esModule: true,
  default: ({ isOpen }: { isOpen: boolean }) =>
    isOpen ? <div data-testid="mock-time-selection-modal" /> : null,
}));

type BookingWithMetadata = {
  bookingId: string;
  instructorId: string;
  instructorName: string;
  lessonType: string;
  date: Date;
  startTime: string;
  endTime: string;
  duration: number;
  location: string;
  basePrice: number;
  totalAmount: number;
  bookingType: BookingType;
  paymentStatus: PaymentStatus;
  metadata?: Record<string, unknown>;
};

function createBooking(overrides: Partial<BookingWithMetadata> = {}): BookingWithMetadata {
  return {
    bookingId: 'booking-1',
    instructorId: 'inst-1',
    instructorName: 'Lee Instructor',
    lessonType: 'Math',
    date: new Date('2025-05-06T12:00:00Z'),
    startTime: '2:00pm',
    endTime: '3:00pm',
    duration: 60,
    location: 'Online',
    basePrice: 80,
    totalAmount: 95,
    bookingType: BookingType.STANDARD,
    paymentStatus: PAYMENT_STATUS.SCHEDULED,
    metadata: { modality: 'remote', location_type: 'online' },
    ...overrides,
  };
}

describe('Lesson Location checkout flow', () => {
  const fetchInstructorProfileMock = fetchInstructorProfile as jest.Mock;
  const useServiceAreaCheckMock = useServiceAreaCheck as jest.Mock;

  const flushConflicts = async () => {
    await act(async () => {
      jest.advanceTimersByTime(300);
      await Promise.resolve();
    });
  };

  beforeEach(() => {
    jest.useFakeTimers();
    fetchInstructorProfileMock.mockResolvedValue({
      services: [
        {
          id: 'svc-1',
          skill: 'Math',
          min_hourly_rate: 80,
          duration_options: [60],
          offers_online: true,
          offers_travel: true,
          offers_at_location: false,
          format_prices: [
            { format: 'online', hourly_rate: 80 },
            { format: 'student_location', hourly_rate: 80 },
          ],
        },
      ],
      preferred_teaching_locations: [],
      preferred_public_spaces: [],
    });
    useServiceAreaCheckMock.mockReturnValue({ data: { is_covered: true }, isLoading: false });
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
    fetchInstructorProfileMock.mockReset();
  });

  it('shows online bookings as read-only and hides checkout format toggles', async () => {
    const booking = createBooking();

    render(
      <PaymentConfirmation
        booking={booking}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
      />,
    );

    await flushConflicts();
    fireEvent.click(screen.getByText('Lesson Location'));

    expect(screen.getAllByText('Online').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Video lesson through the platform').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /online/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /in person/i })).not.toBeInTheDocument();
    expect(screen.queryByTestId('addr-street')).not.toBeInTheDocument();
  });

  it('Change enables editing of a saved travel location while preserving in-person metadata', async () => {
    const booking = createBooking({
      location: '456 Market St, Springfield',
      metadata: { modality: 'in_person', location_type: 'student_location' },
    });
    let latestBooking = { ...booking };
    const onBookingUpdate = jest.fn((updater: (prev: BookingWithMetadata) => BookingWithMetadata) => {
      latestBooking = updater({ ...latestBooking });
    });

    render(
      <PaymentConfirmation
        booking={booking}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
        onBookingUpdate={onBookingUpdate}
      />,
    );

    await flushConflicts();
    fireEvent.click(screen.getByText('Lesson Location'));
    fireEvent.click(await screen.findByRole('button', { name: /change/i }));

    const addressInput = screen.getByTestId('addr-street') as HTMLInputElement;
    await waitFor(() => expect(addressInput).not.toBeDisabled());
    await waitFor(() => expect(document.activeElement).toBe(addressInput));
    expect(latestBooking.metadata?.['modality']).toBe('in_person');
  });

  it('uses Edit lesson as the path to reopen the full time-selection modal', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
      />,
    );

    await flushConflicts();
    expect(screen.queryByTestId('mock-time-selection-modal')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('Edit lesson'));

    await waitFor(() => {
      expect(screen.getByTestId('mock-time-selection-modal')).toBeInTheDocument();
    });
  });

  it('shows the generic instructor-location note instead of an address input', async () => {
    fetchInstructorProfileMock.mockResolvedValueOnce({
      services: [
        {
          id: 'svc-1',
          skill: 'Math',
          min_hourly_rate: 80,
          duration_options: [60],
          offers_online: false,
          offers_travel: false,
          offers_at_location: true,
          format_prices: [{ format: 'instructor_location', hourly_rate: 80 }],
        },
      ],
      preferred_teaching_locations: [
        { id: 'loc-1', label: 'Downtown Studio', address: '123 Studio Lane' },
      ],
      preferred_public_spaces: [],
    });

    render(
      <PaymentConfirmation
        booking={createBooking({
          location: "At instructor's location",
          metadata: { modality: 'studio', location_type: 'instructor_location' },
        })}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
      />,
    );

    await flushConflicts();
    fireEvent.click(screen.getByText('Lesson Location'));

    expect(screen.getAllByText("At instructor's location").length).toBeGreaterThan(0);
    expect(screen.getAllByText("You'll travel to the instructor").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText('Instructor address shared after booking confirmation').length,
    ).toBeGreaterThan(0);
    expect(screen.queryByTestId('addr-street')).not.toBeInTheDocument();
  });
});
