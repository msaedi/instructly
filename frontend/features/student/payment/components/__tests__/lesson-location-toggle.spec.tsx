import React from 'react';
import { render, fireEvent, waitFor, screen, act } from '@testing-library/react';
import PaymentConfirmation from '../PaymentConfirmation';
import { PaymentMethod, PaymentStatus } from '../../types';
import { BookingType } from '@/features/shared/types/booking';

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingFloors: () => ({ floors: null }),
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

jest.mock('@/features/shared/api/schemas/instructorProfile', () => ({
  loadInstructorProfileSchema: jest.fn().mockResolvedValue({ services: [] }),
}));

jest.mock('@/features/student/booking/components/TimeSelectionModal', () => ({
  __esModule: true,
  default: () => null,
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
    paymentStatus: PaymentStatus.PENDING,
    metadata: { modality: 'remote' },
    ...overrides,
  };
}

describe('Lesson Location toggle', () => {
  let fetchMock: jest.SpyInstance;
  const flushConflicts = async () => {
    await act(async () => {
      jest.advanceTimersByTime(300);
      await Promise.resolve();
    });
  };

  const getLessonAddressInput = () => screen.getByTestId('addr-street') as HTMLInputElement;

  beforeEach(() => {
    jest.useFakeTimers();
    fetchMock = jest.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.href
          : (input as { url?: string }).url ?? '';

      if (url.includes('/api/v1/addresses/places/autocomplete')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            items: [
              {
                place_id: 'place_1',
                description: '225 Cherry St, Brooklyn, NY 11201',
                provider: 'google',
              },
            ],
          }),
        } as unknown as Response);
      }

      if (url.includes('/api/v1/addresses/places/details')) {
        expect(url).toContain('place_id=place_1');
        expect(url).toContain('provider=google');
        return Promise.resolve({
          ok: true,
          json: async () => ({
            result: {
              address: {
                line1: '225 Cherry St',
                city: 'Brooklyn',
                state: 'NY',
                postal: '11201',
                country: 'US',
              },
              formatted_address: '225 Cherry St, Brooklyn, NY 11201',
            },
          }),
        } as unknown as Response);
      }

      return Promise.resolve({
        ok: true,
        json: async () => ({}),
      } as unknown as Response);
    });
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
    fetchMock.mockRestore();
  });

  it('maintains remote modality and disables address inputs when online', async () => {
    const booking = createBooking();
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
      />
    );

    await flushConflicts();
    await waitFor(() => expect(onBookingUpdate).toHaveBeenCalled());
    await waitFor(() => expect(latestBooking.metadata?.modality).toBe('remote'));
    expect(screen.getByLabelText(/Online/i)).toBeChecked();
    expect(latestBooking.location).toBe('Online');
    const addressInput = getLessonAddressInput();
    expect(addressInput).toBeDisabled();
    expect(addressInput).toBeVisible();
    expect(addressInput).toHaveValue('');
    const cityInput = screen.getByTestId('addr-city');
    expect(cityInput).toBeDisabled();
    expect(cityInput).toBeVisible();
  });

  it('allows switching to an address and updates booking metadata/location', async () => {
    const booking = createBooking();
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
      />
    );

    await flushConflicts();
    const onlineToggle = screen.getByLabelText(/Online/i);
    await waitFor(() => expect(onlineToggle).toBeChecked());

    fireEvent.click(onlineToggle);

    await waitFor(() => expect(onlineToggle).not.toBeChecked());

    const addressInput = getLessonAddressInput();
    expect(addressInput).not.toBeDisabled();
    expect(addressInput).toHaveValue('');

    fireEvent.change(addressInput, { target: { value: '225 Ch' } });

    await act(async () => {
      jest.advanceTimersByTime(300);
      await Promise.resolve();
    });

    const suggestion = await screen.findByRole('option', {
      name: /225 Cherry St, Brooklyn, NY 11201/i,
    });
    fireEvent.click(suggestion);

    await flushConflicts();

    await waitFor(() => expect(screen.getByTestId('addr-street')).toHaveValue('225 Cherry St'));
    await waitFor(() => expect(screen.getByTestId('addr-city')).toHaveValue('Brooklyn'));
    await waitFor(() => expect(screen.getByTestId('addr-state')).toHaveValue('NY'));
    await waitFor(() => expect(screen.getByTestId('addr-zip')).toHaveValue('11201'));

    await waitFor(() => expect(latestBooking.metadata?.modality).toBe('in_person'));
    await waitFor(() =>
      expect(latestBooking.location).toBe('225 Cherry St, Brooklyn, NY 11201'),
    );

    fireEvent.click(screen.getByText('Lesson Location'));
    await waitFor(() =>
      expect(screen.getAllByText('225 Cherry St, Brooklyn, NY 11201')[0]).toBeInTheDocument(),
    );
  });

  it('Change button enables editing of a saved location and focuses the address field', async () => {
    const booking = createBooking({
      location: '456 Market St, Springfield',
      metadata: { modality: 'in_person' },
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
      />
    );

    await flushConflicts();
    fireEvent.click(screen.getByText('Lesson Location'));

    const changeButton = await screen.findByRole('button', { name: /change/i });
    fireEvent.click(changeButton);

    const displayInput = (await screen
      .findByDisplayValue(/456 Market St/i)
      .catch(() => null)) as HTMLInputElement | null;
    const addressInput = displayInput ?? getLessonAddressInput();
    await waitFor(() => expect(addressInput).not.toBeDisabled());
    await waitFor(() => expect(document.activeElement).toBe(addressInput));
    expect(latestBooking.metadata?.modality).toBe('in_person');
  });
});
