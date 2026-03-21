import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

import PaymentConfirmation from '../PaymentConfirmation';
import { PaymentMethod, PAYMENT_STATUS, type BookingPayment } from '../../types';
import { BookingType } from '@/features/shared/types/booking';
import { fetchInstructorProfile } from '@/src/api/services/instructors';

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingFloors: () => ({ floors: null, config: { student_fee_pct: 0.12 }, isLoading: false, error: null }),
  usePricingConfig: () => ({ config: { student_fee_pct: 0.12 }, isLoading: false, error: null }),
}));

jest.mock('@/hooks/useServiceAreaCheck', () => ({
  useServiceAreaCheck: () => ({ data: { is_covered: true }, isLoading: false }),
}));

jest.mock('@/hooks/useSavedAddresses', () => ({
  useSavedAddresses: () => ({ addresses: [], isLoading: false, data: { items: [] } }),
  formatAddress: () => '',
  getAddressLabel: () => 'Address',
}));

jest.mock('@/components/forms/PlacesAutocompleteInput', () => ({
  PlacesAutocompleteInput: (() => {
    const ReactMock = jest.requireActual<typeof import('react')>('react');
    const PlacesAutocompleteInput = ReactMock.forwardRef<
      HTMLInputElement,
      { value?: string; onValueChange?: (value: string) => void }
    >(({ value = '', onValueChange }, ref) => (
      <input
        ref={ref}
        value={value}
        onChange={(event) => onValueChange?.(event.target.value)}
        data-testid="mock-places-input"
      />
    ));
    PlacesAutocompleteInput.displayName = 'MockPlacesAutocompleteInput';
    return PlacesAutocompleteInput;
  })(),
}));

jest.mock('@/features/student/booking/components/TimeSelectionModal', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('@/src/api/services/bookings', () => ({
  fetchBookingsList: jest.fn().mockResolvedValue({ items: [] }),
}));

jest.mock('@/src/api/services/instructors', () => ({
  fetchInstructorProfile: jest.fn(),
}));

const baseBooking: BookingPayment & { metadata?: Record<string, unknown> } = {
  bookingId: 'booking-1',
  instructorId: 'inst-1',
  instructorName: 'Lee Instructor',
  lessonType: 'Math',
  date: new Date('2025-05-06T00:00:00Z'),
  startTime: '2:00pm',
  endTime: '3:00pm',
  duration: 60,
  location: 'Online',
  basePrice: 80,
  totalAmount: 95,
  bookingType: BookingType.STANDARD,
  paymentStatus: PAYMENT_STATUS.SCHEDULED,
  metadata: { modality: 'remote', location_type: 'online' },
};

const mockFetchInstructorProfile = fetchInstructorProfile as jest.Mock;

const flushTimers = async () => {
  await act(async () => {
    jest.advanceTimersByTime(300);
    await Promise.resolve();
  });
};

const renderConfirmation = async (
  services: Record<string, unknown>[],
  booking: BookingPayment & { metadata?: Record<string, unknown> } = baseBooking,
) => {
  mockFetchInstructorProfile.mockResolvedValueOnce({
    services,
    preferred_teaching_locations: [{ address: '123 Studio Lane', label: 'Studio' }],
    preferred_public_spaces: [{ address: 'Bryant Park', label: 'Park' }],
  });

  render(
    <PaymentConfirmation
      booking={booking}
      paymentMethod={PaymentMethod.CREDIT_CARD}
      onConfirm={jest.fn()}
      onBack={jest.fn()}
    />,
  );

  await flushTimers();
  await waitFor(() => expect(mockFetchInstructorProfile).toHaveBeenCalled());
  fireEvent.click(screen.getByText('Lesson Location'));
};

describe('Location options based on capabilities', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
    mockFetchInstructorProfile.mockReset();
  });

  it('keeps online checkout format read-only even when the instructor supports every capability', async () => {
    await renderConfirmation([
      {
        id: 'svc-1',
        min_hourly_rate: 100,
        offers_online: true,
        offers_travel: true,
        offers_at_location: true,
        format_prices: [
          { format: 'online', hourly_rate: 100 },
          { format: 'student_location', hourly_rate: 100 },
          { format: 'instructor_location', hourly_rate: 100 },
        ],
      },
    ]);

    expect(screen.getAllByText('Online').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Video lesson through the platform').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /online/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /in person/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /at lee's location/i })).not.toBeInTheDocument();
  });

  it('shows the instructor-location summary when preserved booking metadata says instructor location', async () => {
    await renderConfirmation(
      [
        {
          id: 'svc-1',
          min_hourly_rate: 100,
          offers_online: false,
          offers_travel: false,
          offers_at_location: true,
          format_prices: [{ format: 'instructor_location', hourly_rate: 100 }],
        },
      ],
      {
        ...baseBooking,
        location: "At instructor's location",
        metadata: { modality: 'studio', location_type: 'instructor_location' },
      },
    );

    expect(screen.getAllByText("At instructor's location").length).toBeGreaterThan(0);
    expect(screen.getAllByText("You'll travel to the instructor").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText('Instructor address shared after booking confirmation').length,
    ).toBeGreaterThan(0);
    expect(screen.queryByTestId('addr-street')).not.toBeInTheDocument();
  });

  it('shows meeting-point copy and editable address fields for neutral_location bookings', async () => {
    await renderConfirmation(
      [
        {
          id: 'svc-1',
          min_hourly_rate: 100,
          offers_online: true,
          offers_travel: true,
          offers_at_location: false,
          format_prices: [
            { format: 'online', hourly_rate: 100 },
            { format: 'student_location', hourly_rate: 100 },
          ],
        },
      ],
      {
        ...baseBooking,
        location: 'Bryant Park',
        metadata: { modality: 'neutral', location_type: 'neutral_location' },
      },
    );

    expect(screen.getAllByText('At a meeting point').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Choose or confirm the meeting address below').length).toBeGreaterThan(0);
    expect(screen.getByTestId('mock-places-input')).toHaveValue('Bryant Park');
  });
});
