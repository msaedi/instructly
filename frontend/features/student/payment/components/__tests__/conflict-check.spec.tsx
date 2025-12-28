import React from 'react';
import { render, screen, act } from '@testing-library/react';
import PaymentConfirmation from '../PaymentConfirmation';
import { PaymentMethod, PAYMENT_STATUS, type PaymentStatus } from '../../types';
import { BookingType } from '@/features/shared/types/booking';

const mockFetchBookingsList = jest.fn();

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingFloors: () => ({ floors: null, config: { student_fee_pct: 0.12 }, isLoading: false, error: null }),
  usePricingConfig: () => ({ config: { student_fee_pct: 0.12 }, isLoading: false, error: null }),
}));

// Mock v1 bookings service for conflict check
jest.mock('@/src/api/services/bookings', () => ({
  fetchBookingsList: (...args: unknown[]) => mockFetchBookingsList(...args),
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

jest.mock('@/components/forms/PlacesAutocompleteInput', () => {
  type MockProps = React.ComponentPropsWithoutRef<'input'> & {
    value?: string;
    onValueChange?: (value: string) => void;
    inputClassName?: string;
    containerClassName?: string;
    onSelectSuggestion?: (suggestion: unknown) => void;
  };

  let latestSelect: ((suggestion: unknown) => void) | undefined;

  const MockPlacesAutocompleteInput = React.forwardRef<HTMLInputElement, MockProps>(
    ({
      onValueChange,
      value,
      inputClassName,
      className,
      onChange,
      onSelectSuggestion,
      placeholder,
      disabled,
      autoComplete,
      name,
      id,
      style,
    }, ref) => {
      latestSelect = onSelectSuggestion;

      return (
        <input
          ref={ref}
          placeholder={placeholder}
          disabled={disabled}
          autoComplete={autoComplete}
          name={name}
          id={id}
          style={style as React.CSSProperties | undefined}
          className={inputClassName ?? className}
          value={value ?? ''}
          onChange={(event) => {
            onValueChange?.(event.target.value);
            onChange?.(event);
          }}
        />
      );
    },
  );
  MockPlacesAutocompleteInput.displayName = 'MockPlacesAutocompleteInput';

  return {
    PlacesAutocompleteInput: MockPlacesAutocompleteInput,
    __invokeSelect: (suggestion: unknown) => {
      latestSelect?.(suggestion);
    },
  };
});

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
    metadata: { modality: 'remote' },
    ...overrides,
  };
}

// v1 fetchBookingsList returns PaginatedBookingResponse directly
const resolveBookings = (items: Array<Record<string, unknown>>) =>
  Promise.resolve({
    items,
    total: items.length,
    page: 1,
    page_size: 50,
    pages: 1,
  });

const flushConflicts = async () => {
  await act(async () => {
    jest.advanceTimersByTime(300);
    await Promise.resolve();
  });
};

describe('PaymentConfirmation conflict checks', () => {
  let fetchMock: jest.SpyInstance;

  beforeEach(() => {
    jest.useFakeTimers();
    mockFetchBookingsList.mockReset();
    fetchMock = jest
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue({
        ok: true,
        json: async () => ({ result: {} }),
      } as unknown as Response);
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
    fetchMock.mockRestore();
  });

  it('disables CTA when an overlapping booking exists', async () => {
    mockFetchBookingsList.mockImplementation(() =>
      resolveBookings([
        {
          booking_date: '2025-05-06',
          start_time: '14:00',
          duration_minutes: 60,
          status: 'confirmed',
        },
      ]),
    );

    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
      />,
    );

    await flushConflicts();

    // v1 service uses upcoming_only parameter
    expect(mockFetchBookingsList).toHaveBeenCalledWith({ upcoming_only: true });
    const button = await screen.findByRole('button', { name: /conflict/i });
    expect(button).toBeDisabled();
  });

  it('keeps CTA enabled when there is no overlap', async () => {
    mockFetchBookingsList.mockImplementation(() =>
      resolveBookings([
        {
          booking_date: '2025-05-06',
          start_time: '16:00',
          duration_minutes: 60,
          status: 'confirmed',
        },
      ]),
    );

    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
      />,
    );

    await flushConflicts();

    const button = await screen.findByRole('button', { name: /book now/i });
    expect(button).not.toBeDisabled();
  });
});
