import { render, screen } from '@testing-library/react';
import { act } from 'react-dom/test-utils';
import PaymentProcessing from '../PaymentProcessing';
import { BookingType } from '../../types';

describe('PaymentProcessing', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  it('renders last-minute messaging', () => {
    render(
      <PaymentProcessing amount={120} bookingType={BookingType.LAST_MINUTE} />
    );

    expect(screen.getByText('Processing Payment')).toBeInTheDocument();
    expect(screen.getByText('Charging $120.00 to your card')).toBeInTheDocument();
    expect(screen.getByText('Processing payment')).toBeInTheDocument();
  });

  it('renders standard booking messaging', () => {
    render(
      <PaymentProcessing amount={80} bookingType={BookingType.STANDARD} />
    );

    expect(screen.getByText('Authorizing Payment')).toBeInTheDocument();
    expect(screen.getByText('Authorizing $80.00 for your lesson')).toBeInTheDocument();
    expect(screen.getByText('Authorizing card')).toBeInTheDocument();
  });

  it('advances progress steps over time', () => {
    render(
      <PaymentProcessing amount={50} bookingType={BookingType.STANDARD} />
    );

    expect(screen.queryAllByText('✓')).toHaveLength(0);

    act(() => {
      jest.advanceTimersByTime(1500);
    });

    expect(screen.queryAllByText('✓').length).toBeGreaterThan(0);
  });

  it('calls onTimeout after 30 seconds', () => {
    const onTimeout = jest.fn();
    render(
      <PaymentProcessing amount={50} bookingType={BookingType.STANDARD} onTimeout={onTimeout} />
    );

    act(() => {
      jest.advanceTimersByTime(30000);
    });

    expect(onTimeout).toHaveBeenCalled();
  });

  it('renders secure payment notice', () => {
    render(
      <PaymentProcessing amount={50} bookingType={BookingType.STANDARD} />
    );

    expect(screen.getByText('Secure payment processed by Stripe')).toBeInTheDocument();
    expect(screen.getByText("Please don't close this window")).toBeInTheDocument();
  });
});
