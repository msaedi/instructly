/**
 * Tests for PaymentConfirmation promo code handling and CTA states
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import PaymentConfirmation from '../PaymentConfirmation';
import { PaymentMethod, PAYMENT_STATUS, type PaymentStatus } from '../../types';
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

jest.mock('@/src/api/services/bookings', () => ({
  fetchBookingsList: jest.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50, pages: 1 }),
}));

jest.mock('@/components/forms/PlacesAutocompleteInput', () => {
  type MockProps = React.ComponentPropsWithoutRef<'input'> & {
    value?: string;
    onValueChange?: (value: string) => void;
    inputClassName?: string;
    containerClassName?: string;
    onSelectSuggestion?: (suggestion: unknown) => void;
  };

  const MockPlacesAutocompleteInput = React.forwardRef<HTMLInputElement, MockProps>(
    ({
      onValueChange,
      value,
      inputClassName,
      className,
      onChange,
      placeholder,
      disabled,
      ...rest
    }, ref) => (
      <input
        ref={ref}
        placeholder={placeholder}
        disabled={disabled}
        className={inputClassName ?? className}
        value={value ?? ''}
        onChange={(event) => {
          onValueChange?.(event.target.value);
          onChange?.(event);
        }}
        {...rest}
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

describe('PaymentConfirmation promo code functionality', () => {
  let fetchMock: jest.SpyInstance;

  const flushTimers = async () => {
    await act(async () => {
      jest.advanceTimersByTime(300);
      await Promise.resolve();
    });
  };

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

  it('shows promo code input and apply button in payment section (no saved card)', async () => {
    // Without cardLast4, the payment section should be expanded and show promo code input
    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
      />,
    );

    await flushTimers();

    // Payment section should be expanded by default when no saved card
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/enter promo code/i)).toBeInTheDocument();
    });

    const applyButton = screen.getByRole('button', { name: /apply/i });
    expect(applyButton).toBeInTheDocument();
  });

  it('disables apply button when promo code is empty', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
      />,
    );

    await flushTimers();

    // Payment section should be expanded by default when no saved card
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/enter promo code/i)).toBeInTheDocument();
    });

    // Apply button should be disabled when no promo code entered
    const applyButton = screen.getByRole('button', { name: /apply/i });
    expect(applyButton).toBeDisabled();
  });

  it('applies promo code and shows remove button', async () => {
    const onPromoStatusChange = jest.fn();

    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
        onPromoStatusChange={onPromoStatusChange}
      />,
    );

    await flushTimers();

    // Payment section should be expanded by default when no saved card
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/enter promo code/i)).toBeInTheDocument();
    });

    // Enter and apply promo code
    const promoInput = screen.getByPlaceholderText(/enter promo code/i);
    fireEvent.change(promoInput, { target: { value: 'DISCOUNT20' } });

    const applyButton = screen.getByRole('button', { name: /apply/i });
    fireEvent.click(applyButton);

    await waitFor(() => {
      expect(onPromoStatusChange).toHaveBeenCalledWith(true);
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /remove/i })).toBeInTheDocument();
    });
  });

  it('removes promo code when clicking remove button', async () => {
    const onPromoStatusChange = jest.fn();

    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
        onPromoStatusChange={onPromoStatusChange}
        promoApplied={true}
      />,
    );

    await flushTimers();

    // Payment section should be expanded by default when no saved card
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /remove/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /remove/i }));

    await waitFor(() => {
      expect(onPromoStatusChange).toHaveBeenCalledWith(false);
    });
  });

  it('shows referral block message when referral is active (no promo input shown)', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
        referralAppliedCents={2000}
        referralActive={true}
      />,
    );

    await flushTimers();

    // When referral is active, the promo input is replaced with a message
    // Payment section should be expanded by default when no saved card
    await waitFor(() => {
      expect(screen.getByText(/referral credit applied/i)).toBeInTheDocument();
    });

    // Promo code input should not be shown
    expect(screen.queryByPlaceholderText(/enter promo code/i)).not.toBeInTheDocument();
  });

  it('enables apply button when typing promo code', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
      />,
    );

    await flushTimers();

    // Payment section should be expanded by default when no saved card
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/enter promo code/i)).toBeInTheDocument();
    });

    // Apply button should be disabled initially
    const applyButton = screen.getByRole('button', { name: /apply/i });
    expect(applyButton).toBeDisabled();

    // Type a promo code to enable the button
    const promoInput = screen.getByPlaceholderText(/enter promo code/i);
    fireEvent.change(promoInput, { target: { value: 'DISCOUNT10' } });

    await waitFor(() => {
      expect(applyButton).not.toBeDisabled();
    });
  });
});

describe('PaymentConfirmation CTA button states', () => {
  let fetchMock: jest.SpyInstance;

  const flushTimers = async () => {
    await act(async () => {
      jest.advanceTimersByTime(300);
      await Promise.resolve();
    });
  };

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

  it('shows "Book now!" label when no blocking conditions', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
      />,
    );

    await flushTimers();

    const button = await screen.findByRole('button', { name: /book now/i });
    expect(button).not.toBeDisabled();
  });

  it('shows "Price must meet minimum" when floor violation exists', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
        floorViolationMessage="Minimum price is $50"
      />,
    );

    await flushTimers();

    const button = await screen.findByRole('button', { name: /price must meet minimum/i });
    expect(button).toBeDisabled();
  });

  it('calls onConfirm when clicking enabled CTA', async () => {
    const onConfirm = jest.fn();

    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={onConfirm}
        onBack={jest.fn()}
      />,
    );

    await flushTimers();

    const button = await screen.findByRole('button', { name: /book now/i });
    fireEvent.click(button);

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('does not call onConfirm when clicking disabled CTA', async () => {
    const onConfirm = jest.fn();

    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={onConfirm}
        onBack={jest.fn()}
        floorViolationMessage="Minimum price is $50"
      />,
    );

    await flushTimers();

    const button = await screen.findByRole('button', { name: /price must meet minimum/i });
    fireEvent.click(button);

    expect(onConfirm).not.toHaveBeenCalled();
  });
});

describe('PaymentConfirmation payment method accordion', () => {
  let fetchMock: jest.SpyInstance;

  const flushTimers = async () => {
    await act(async () => {
      jest.advanceTimersByTime(300);
      await Promise.resolve();
    });
  };

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

  it('shows collapsed card info when user has saved card', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
        cardLast4="4242"
        cardBrand="Visa"
      />,
    );

    await flushTimers();

    // Should show last 4 digits in collapsed state
    expect(screen.getByText(/•••• 4242/)).toBeInTheDocument();
  });

  it('expands payment method section on click', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
        cardLast4="4242"
        cardBrand="Visa"
      />,
    );

    await flushTimers();

    // Click to expand
    fireEvent.click(screen.getByText('Payment Method'));

    await waitFor(() => {
      expect(screen.getByText(/visa ending in 4242/i)).toBeInTheDocument();
    });
  });

  it('shows change button for saved card', async () => {
    const onChangePaymentMethod = jest.fn();

    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
        cardLast4="4242"
        cardBrand="Visa"
        onChangePaymentMethod={onChangePaymentMethod}
      />,
    );

    await flushTimers();

    // Expand payment section
    fireEvent.click(screen.getByText('Payment Method'));

    await waitFor(() => {
      const changeButtons = screen.getAllByRole('button', { name: /change/i });
      expect(changeButtons.length).toBeGreaterThan(0);
    });

    const changeButtons = screen.getAllByRole('button', { name: /change/i });
    fireEvent.click(changeButtons[0] as HTMLElement);

    expect(onChangePaymentMethod).toHaveBeenCalled();
  });

  it('shows default badge for default card', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
        cardLast4="4242"
        cardBrand="Visa"
        isDefaultCard={true}
      />,
    );

    await flushTimers();

    // Expand payment section
    fireEvent.click(screen.getByText('Payment Method'));

    await waitFor(() => {
      expect(screen.getByText(/default/i)).toBeInTheDocument();
    });
  });
});

describe('PaymentConfirmation mixed payment display', () => {
  let fetchMock: jest.SpyInstance;

  const flushTimers = async () => {
    await act(async () => {
      jest.advanceTimersByTime(300);
      await Promise.resolve();
    });
  };

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

  it('shows credits and card amounts for MIXED payment', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking({ totalAmount: 100 })}
        paymentMethod={PaymentMethod.MIXED}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
        creditsUsed={30}
        availableCredits={50}
      />,
    );

    await flushTimers();

    // Payment section is expanded by default with no saved card
    // Look for the credits/card breakdown which appears when MIXED
    await waitFor(() => {
      expect(screen.getByText(/credits: \$30\.00/i)).toBeInTheDocument();
    });
  });

  it('shows "Using platform credits" for CREDITS payment method', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking({ totalAmount: 50 })}
        paymentMethod={PaymentMethod.CREDITS}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
        creditsUsed={50}
        availableCredits={100}
      />,
    );

    await flushTimers();

    // Payment section is expanded by default with no saved card
    await waitFor(() => {
      expect(screen.getByText(/using platform credits/i)).toBeInTheDocument();
    });
  });
});

describe('PaymentConfirmation booking summary display', () => {
  let fetchMock: jest.SpyInstance;

  const flushTimers = async () => {
    await act(async () => {
      jest.advanceTimersByTime(300);
      await Promise.resolve();
    });
  };

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

  it('displays instructor name in booking summary', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking({ instructorName: 'John Smith' })}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
      />,
    );

    await flushTimers();

    expect(screen.getByText('John Smith')).toBeInTheDocument();
  });

  it('displays lesson duration in summary', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking({ duration: 90 })}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
      />,
    );

    await flushTimers();

    expect(screen.getByText(/lesson \(90 min\)/i)).toBeInTheDocument();
  });

  it('displays formatted date in summary', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking({ date: new Date('2025-12-25T10:00:00Z') })}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
      />,
    );

    await flushTimers();

    expect(screen.getByText(/december 25, 2025/i)).toBeInTheDocument();
  });

  it('shows cancellation policy section', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
      />,
    );

    await flushTimers();

    expect(screen.getByText(/cancellation policy/i)).toBeInTheDocument();
    expect(screen.getByText(/more than 24 hours before your lesson/i)).toBeInTheDocument();
    expect(screen.getByText(/full refund/i)).toBeInTheDocument();
  });

  it('displays "Online" for online lessons in summary', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking({ location: 'Online', metadata: { modality: 'remote' } })}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
      />,
    );

    await flushTimers();

    const onlineTexts = screen.getAllByText('Online');
    expect(onlineTexts.length).toBeGreaterThan(0);
  });

  it('displays physical location for in-person lessons', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking({
          location: '123 Main St, New York',
          metadata: { modality: 'in_person' },
        })}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
      />,
    );

    await flushTimers();

    // The location should be displayed in the booking summary section
    const locationElements = screen.getAllByText('123 Main St, New York');
    expect(locationElements.length).toBeGreaterThan(0);
  });
});

describe('PaymentConfirmation referral credit display', () => {
  let fetchMock: jest.SpyInstance;

  const flushTimers = async () => {
    await act(async () => {
      jest.advanceTimersByTime(300);
      await Promise.resolve();
    });
  };

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

  it('displays referral credit line in payment details when referral amount is positive', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking({ totalAmount: 100 })}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
        referralAppliedCents={2000}
        referralActive={true}
      />,
    );

    await flushTimers();

    // The "Referral credit" line item appears in payment details section on the right
    // It shows when referralCreditAmount > 0
    // Note: There may be two elements - one in payment section (promo area) and one in payment details
    const referralTexts = screen.getAllByText(/referral credit/i);
    expect(referralTexts.length).toBeGreaterThan(0);
  });

  it('shows referral block message in promo section when referral is active', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
        referralAppliedCents={2000}
        referralActive={true}
      />,
    );

    await flushTimers();

    // Payment section is expanded by default with no saved card
    // The promo section shows a block message when referral is active
    await waitFor(() => {
      expect(screen.getByText(/referral credit applied/i)).toBeInTheDocument();
    });
  });
});

describe('PaymentConfirmation edit lesson button', () => {
  let fetchMock: jest.SpyInstance;

  const flushTimers = async () => {
    await act(async () => {
      jest.advanceTimersByTime(300);
      await Promise.resolve();
    });
  };

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

  it('shows edit lesson button', async () => {
    render(
      <PaymentConfirmation
        booking={createBooking()}
        paymentMethod={PaymentMethod.CREDIT_CARD}
        onConfirm={jest.fn()}
        onBack={jest.fn()}
      />,
    );

    await flushTimers();

    const editButton = screen.getByRole('button', { name: /edit lesson/i });
    expect(editButton).toBeInTheDocument();
  });
});
