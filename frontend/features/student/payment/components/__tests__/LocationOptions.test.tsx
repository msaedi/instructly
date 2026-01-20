import React from 'react';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';

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
  metadata: { modality: 'remote' },
};

const mockFetchInstructorProfile = fetchInstructorProfile as jest.Mock;

const flushTimers = async () => {
  await act(async () => {
    jest.advanceTimersByTime(300);
    await Promise.resolve();
  });
};

const renderConfirmation = async (services: Record<string, unknown>[]) => {
  mockFetchInstructorProfile.mockResolvedValueOnce({
    services,
    preferred_teaching_locations: [{ address: '123 Studio Lane', label: 'Studio' }],
  });

  render(
    <PaymentConfirmation
      booking={baseBooking}
      paymentMethod={PaymentMethod.CREDIT_CARD}
      onConfirm={jest.fn()}
      onBack={jest.fn()}
    />,
  );

  await flushTimers();
  await waitFor(() => expect(mockFetchInstructorProfile).toHaveBeenCalled());

  if (!screen.queryByLabelText('Online')) {
    fireEvent.click(screen.getByText('Lesson Location'));
  }
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

  it('shows only online when offers_online=true only', async () => {
    await renderConfirmation([
      { id: 'svc-1', offers_online: true, offers_travel: false, offers_at_location: false },
    ]);

    expect(screen.getByLabelText('Online')).toBeInTheDocument();
    expect(screen.queryByText('At your location')).not.toBeInTheDocument();
    expect(screen.queryByText('At a public location')).not.toBeInTheDocument();
    expect(screen.queryByText("At Lee's location")).not.toBeInTheDocument();
  });

  it('shows all options when all capabilities true', async () => {
    await renderConfirmation([
      { id: 'svc-1', offers_online: true, offers_travel: true, offers_at_location: true },
    ]);

    await waitFor(() => expect(screen.getByLabelText('Online')).toBeChecked());
    fireEvent.click(screen.getByLabelText('Online'));

    await waitFor(() => {
      expect(screen.getByLabelText('Online')).not.toBeChecked();
      expect(screen.getByText('At your location')).toBeInTheDocument();
      expect(screen.getByText('At a public location')).toBeInTheDocument();
      expect(screen.getByText("At Lee's location")).toBeInTheDocument();
    });
  });

  it('hides student_location when offers_travel=false', async () => {
    await renderConfirmation([
      { id: 'svc-1', offers_online: true, offers_travel: false, offers_at_location: true },
    ]);

    await waitFor(() => expect(screen.getByLabelText('Online')).toBeChecked());
    fireEvent.click(screen.getByLabelText('Online'));

    await waitFor(() => {
      expect(screen.getByLabelText('Online')).not.toBeChecked();
      expect(screen.queryByText('At your location')).not.toBeInTheDocument();
      expect(screen.queryByText('At a public location')).not.toBeInTheDocument();
      expect(screen.getByText("At Lee's location")).toBeInTheDocument();
    });
  });

  it('hides instructor_location when offers_at_location=false', async () => {
    await renderConfirmation([
      { id: 'svc-1', offers_online: true, offers_travel: true, offers_at_location: false },
    ]);

    await waitFor(() => expect(screen.getByLabelText('Online')).toBeChecked());
    fireEvent.click(screen.getByLabelText('Online'));

    await waitFor(() => {
      expect(screen.getByLabelText('Online')).not.toBeChecked();
      expect(screen.getByText('At your location')).toBeInTheDocument();
      expect(screen.getByText('At a public location')).toBeInTheDocument();
      expect(screen.queryByText("At Lee's location")).not.toBeInTheDocument();
    });
  });
});
