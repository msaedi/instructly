import React, { useState } from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import PaymentConfirmation from '../PaymentConfirmation';
import { PaymentMethod, PaymentStatus } from '../../types';
import { BookingType } from '@/features/shared/types/booking';

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
  };

  const MockPlacesAutocompleteInput = React.forwardRef<HTMLInputElement, MockProps>(
    ({ onValueChange, value, inputClassName, className, onChange, ...rest }, ref) => (
      <input
        ref={ref}
        {...rest}
        className={inputClassName ?? className}
        value={value ?? ''}
        onChange={(event) => {
          onValueChange?.(event.target.value);
          onChange?.(event);
        }}
      />
    ),
  );
  MockPlacesAutocompleteInput.displayName = 'MockPlacesAutocompleteInput';

  return { PlacesAutocompleteInput: MockPlacesAutocompleteInput };
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

const createBooking = (): BookingWithMetadata => ({
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
});

function CreditsHarness() {
  const [creditsUsed, setCreditsUsed] = useState(10);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>(PaymentMethod.MIXED);

  const updateCredits = (next: number) => {
    setCreditsUsed(next);
    setPaymentMethod(next > 0 ? PaymentMethod.MIXED : PaymentMethod.CREDIT_CARD);
  };

  return (
    <PaymentConfirmation
      booking={createBooking()}
      paymentMethod={paymentMethod}
      cardLast4="4242"
      onConfirm={jest.fn()}
      onBack={jest.fn()}
      availableCredits={50}
      creditsUsed={creditsUsed}
      onCreditAmountChange={(amount) => updateCredits(amount)}
      onCreditToggle={() => updateCredits(creditsUsed > 0 ? 0 : 50)}
      creditEarliestExpiry={new Date('2025-12-31')}
      onChangePaymentMethod={jest.fn()}
      referralAppliedCents={0}
      referralActive={false}
      floorViolationMessage={null}
      onClearFloorViolation={jest.fn()}
    />
  );
}

describe('Available Credits accordion', () => {
  let fetchMock: jest.SpyInstance;

  beforeEach(() => {
    jest.useFakeTimers();
    fetchMock = jest
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue({ ok: true, json: async () => ({ result: {} }) } as unknown as Response);
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
    fetchMock.mockRestore();
  });

  it('keeps accordion open at zero credits and preserves slider value when re-expanded', async () => {
    render(<CreditsHarness />);

    await act(async () => {
      jest.advanceTimersByTime(300);
      await Promise.resolve();
    });

    const slider = screen.getByRole('slider') as HTMLInputElement;
    expect(slider.value).toBe('10');

    fireEvent.change(slider, { target: { value: '0' } });
    fireEvent.mouseUp(slider);
    await act(async () => {
      jest.advanceTimersByTime(0);
      await Promise.resolve();
    });

    expect(slider.value).toBe('0');
    expect(screen.getByText('Using $0.00')).toBeInTheDocument();
    expect(screen.getByRole('slider')).toBeInTheDocument();

    const toggle = screen.getByRole('button', { name: /Available Credits/i });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('slider')).not.toBeInTheDocument();

    fireEvent.click(toggle);
    const reopenedSlider = await screen.findByRole('slider');
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect((reopenedSlider as HTMLInputElement).value).toBe('0');
    expect(screen.getByText('Using $0.00')).toBeInTheDocument();

    fireEvent.change(reopenedSlider, { target: { value: '15' } });
    fireEvent.mouseUp(reopenedSlider);
    await act(async () => {
      jest.advanceTimersByTime(0);
      await Promise.resolve();
    });

    expect((reopenedSlider as HTMLInputElement).value).toBe('15');
    expect(screen.getByText('Using $15.00')).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Using $15.00')).toBeInTheDocument();
    expect(screen.getByRole('slider')).toBeInTheDocument();
  });
});
