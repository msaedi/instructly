import React, { useCallback, useMemo, useState } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import PaymentConfirmation from '../PaymentConfirmation';
import { PricingPreviewContext } from '../../hooks/usePricingPreview';
import { PaymentMethod, PAYMENT_STATUS, type BookingPayment } from '../../types';
import { BookingType } from '@/features/shared/types/booking';
import type { PricingPreviewResponse } from '@/lib/api/pricing';

const applyCreditCommitMock = jest.fn();

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingFloors: () => ({ floors: null, config: { student_fee_pct: 0.12 }, isLoading: false, error: null }),
  usePricingConfig: () => ({ config: { student_fee_pct: 0.12 }, isLoading: false, error: null }),
}));

jest.mock('@/features/shared/api/client', () => ({
  protectedApi: {
    getBooking: jest.fn().mockResolvedValue({ data: null, status: 200 }),
    getBookings: jest.fn().mockResolvedValue({ data: { items: [] }, status: 200 }),
    cancelBooking: jest.fn().mockResolvedValue({ data: null, status: 200 }),
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

jest.mock('@/components/referrals/CheckoutApplyReferral', () => ({
  __esModule: true,
  default: () => <div data-testid="mock-referral" />,
}));

jest.mock('../PaymentMethodSelection', () => ({
  __esModule: true,
  default: () => <div data-testid="mock-method-selection" />,
}));

jest.mock('../PaymentProcessing', () => ({
  __esModule: true,
  default: () => <div data-testid="mock-processing" />,
}));

jest.mock('../PaymentSuccess', () => ({
  __esModule: true,
  default: () => <div data-testid="mock-success" />,
}));

jest.mock('@/components/forms/PlacesAutocompleteInput', () => {
  type MockProps = React.ComponentPropsWithoutRef<'input'> & {
    value?: string;
    onValueChange?: (value: string) => void;
    inputClassName?: string;
    onSelectSuggestion?: (value: string) => void;
    containerClassName?: string;
    suggestionScope?: 'default' | 'us' | 'global';
    inputProps?: unknown;
  };

  const MockPlacesAutocompleteInput = React.forwardRef<HTMLInputElement, MockProps>(
    (
      {
        onValueChange,
        value,
        inputClassName,
        className,
        onChange,
        onSelectSuggestion: _ignored,
        containerClassName: _containerClassName,
        suggestionScope: _suggestionScope,
        inputProps: _inputProps,
        ...rest
      },
      ref,
    ) => (
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

const PREVIEW_NO_CREDIT: PricingPreviewResponse = {
  base_price_cents: 22500,
  student_fee_cents: 2700,
  instructor_platform_fee_cents: 0,
  credit_applied_cents: 0,
  student_pay_cents: 25200,
  application_fee_cents: 0,
  top_up_transfer_cents: 0,
  instructor_tier_pct: 0.12,
  line_items: [{ label: 'Service & Support fee (12%)', amount_cents: 2700 }],
};

const PREVIEW_WITH_CREDIT: PricingPreviewResponse = {
  ...PREVIEW_NO_CREDIT,
  credit_applied_cents: 4500,
  student_pay_cents: 20700,
  line_items: [
    { label: 'Service & Support fee (12%)', amount_cents: 2700 },
    { label: 'Credit', amount_cents: -4500 },
  ],
};

const PREVIEW_BY_CREDIT: Record<number, PricingPreviewResponse> = {
  0: PREVIEW_NO_CREDIT,
  4500: PREVIEW_WITH_CREDIT,
};

const BASE_BOOKING: BookingPayment & { metadata?: Record<string, unknown> } = {
  bookingId: 'booking-1',
  instructorId: 'inst-1',
  instructorName: 'Jordan Instructor',
  lessonType: 'Lesson',
  date: new Date('2025-05-06T12:00:00Z'),
  startTime: '02:00 PM',
  endTime: '03:30 PM',
  duration: 90,
  location: '123 Main St',
  basePrice: 225,
  totalAmount: 252,
  bookingType: BookingType.STANDARD,
  paymentStatus: PAYMENT_STATUS.SCHEDULED,
  creditsAvailable: 0,
  creditsApplied: 0,
  cardAmount: 252,
  metadata: {
    modality: 'in_person',
  },
};

function CreditsSliderHarness() {
  const [preview, setPreview] = useState<PricingPreviewResponse | null>(PREVIEW_NO_CREDIT);

  const applyCredit = useCallback(
    async (creditCents: number) => {
      applyCreditCommitMock(creditCents);
      const normalized = Math.max(0, Math.round(creditCents));
      const next = PREVIEW_BY_CREDIT[normalized] ?? PREVIEW_NO_CREDIT;
      setPreview(next);
      return next;
    },
    [],
  );

  const controller = useMemo(() => ({
    preview,
    loading: false,
    error: null,
    lastAppliedCreditCents: preview?.credit_applied_cents ?? 0,
    requestPricingPreview: async () => preview,
    applyCredit,
    reset: () => undefined,
    bookingId: 'booking-1',
  }), [applyCredit, preview]);

  return (
    <PricingPreviewContext.Provider value={controller}>
      <PaymentConfirmation
        booking={BASE_BOOKING}
        paymentMethod={PaymentMethod.MIXED}
        cardLast4="4242"
        onConfirm={jest.fn()}
        onBack={jest.fn()}
        onChangePaymentMethod={jest.fn()}
        onCreditToggle={jest.fn()}
        onCreditAmountChange={(amount) => {
          void applyCredit(Math.round(amount * 100));
        }}
        availableCredits={100}
        creditsUsed={(preview?.credit_applied_cents ?? 0) / 100}
        creditEarliestExpiry={null}
        referralAppliedCents={0}
        referralActive={false}
        floorViolationMessage={null}
        onClearFloorViolation={jest.fn()}
      />
    </PricingPreviewContext.Provider>
  );
}

describe('Credits slider commit behaviour', () => {
  beforeEach(() => {
    applyCreditCommitMock.mockClear();
  });

  it('debounces credit commits until slider release and keeps the applied amount', async () => {
    render(<CreditsSliderHarness />);

    fireEvent.click(screen.getByText('Available Credits'));

    const slider = await screen.findByRole('slider');

    fireEvent.change(slider, { target: { value: '10' } });
    fireEvent.change(slider, { target: { value: '25' } });
    fireEvent.change(slider, { target: { value: '45' } });

    expect(applyCreditCommitMock).not.toHaveBeenCalled();

    fireEvent.mouseUp(slider);

    await waitFor(() => expect(applyCreditCommitMock).toHaveBeenCalledTimes(1));
    expect(applyCreditCommitMock).toHaveBeenCalledWith(4500);

    expect((slider as HTMLInputElement).value).toBe('45');

    await waitFor(() => {
      expect(screen.getByText('-$45.00')).toBeInTheDocument();
      expect(screen.getByText('$207.00')).toBeInTheDocument();
    });
  });
});
