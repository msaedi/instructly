import React from 'react';
import { render, screen } from '@testing-library/react';
import { SystemMessage, SystemMessageType } from '../SystemMessage';

// Mock the formatRelativeTimestamp function
jest.mock('../formatters', () => ({
  formatRelativeTimestamp: (date: string) => {
    if (!date) return '';
    return 'Just now';
  },
}));

describe('SystemMessage', () => {
  const baseProps = {
    id: 'msg-1',
    content: 'Booking confirmed',
    messageType: 'system_booking_confirmed' as SystemMessageType,
    createdAt: '2024-01-01T12:00:00Z',
  };

  it('renders system message with content', () => {
    render(<SystemMessage {...baseProps} />);

    expect(screen.getByText('Booking confirmed')).toBeInTheDocument();
  });

  it('renders timestamp', () => {
    render(<SystemMessage {...baseProps} />);

    expect(screen.getByText('Just now')).toBeInTheDocument();
  });

  it('renders emoji for booking_created type', () => {
    render(
      <SystemMessage
        {...baseProps}
        messageType="system_booking_created"
        content="Booking created"
      />
    );

    // Check that emoji is rendered (📅 for booking created)
    expect(screen.getByText('📅')).toBeInTheDocument();
    expect(screen.getByText('Booking created')).toBeInTheDocument();
  });

  it('renders emoji for booking_confirmed type', () => {
    render(
      <SystemMessage
        {...baseProps}
        messageType="system_booking_confirmed"
        content="Booking confirmed"
      />
    );

    expect(screen.getByText('✅')).toBeInTheDocument();
  });

  it('renders emoji for booking_cancelled type', () => {
    render(
      <SystemMessage
        {...baseProps}
        messageType="system_booking_cancelled"
        content="Booking cancelled"
      />
    );

    expect(screen.getByText('❌')).toBeInTheDocument();
  });

  it('renders emoji for booking_completed type', () => {
    render(
      <SystemMessage
        {...baseProps}
        messageType="system_booking_completed"
        content="Booking completed"
      />
    );

    expect(screen.getByText('🎉')).toBeInTheDocument();
  });

  it('renders emoji for booking_rescheduled type', () => {
    render(
      <SystemMessage
        {...baseProps}
        messageType="system_booking_rescheduled"
        content="Booking rescheduled"
      />
    );

    expect(screen.getByText('🔄')).toBeInTheDocument();
  });

  it('renders emoji for payment_received type', () => {
    render(
      <SystemMessage
        {...baseProps}
        messageType="system_payment_received"
        content="Payment received"
      />
    );

    expect(screen.getByText('💰')).toBeInTheDocument();
  });

  it('renders emoji for payment_refunded type', () => {
    render(
      <SystemMessage
        {...baseProps}
        messageType="system_payment_refunded"
        content="Payment refunded"
      />
    );

    expect(screen.getByText('💸')).toBeInTheDocument();
  });

  it('renders emoji for review_received type', () => {
    render(
      <SystemMessage
        {...baseProps}
        messageType="system_review_received"
        content="Review received"
      />
    );

    expect(screen.getByText('⭐')).toBeInTheDocument();
  });

  it('renders info emoji for generic system type', () => {
    render(
      <SystemMessage
        {...baseProps}
        messageType="system_generic"
        content="Generic message"
      />
    );

    expect(screen.getByText('ℹ️')).toBeInTheDocument();
  });

  it('renders info emoji for unknown system type', () => {
    render(
      <SystemMessage
        {...baseProps}
        messageType="unknown_type"
        content="Unknown type message"
      />
    );

    expect(screen.getByText('ℹ️')).toBeInTheDocument();
  });

  it('applies custom className when provided', () => {
    const { container } = render(
      <SystemMessage {...baseProps} className="custom-class" />
    );

    const wrapper = container.firstChild;
    expect(wrapper).toHaveClass('custom-class');
  });

  it('centers the message content', () => {
    const { container } = render(<SystemMessage {...baseProps} />);

    const wrapper = container.firstChild;
    expect(wrapper).toHaveClass('flex', 'justify-center');
  });

  it('renders with proper accessibility attributes', () => {
    render(<SystemMessage {...baseProps} />);

    // Emoji should have aria-hidden for accessibility
    const emoji = screen.getByText('✅');
    expect(emoji).toHaveAttribute('aria-hidden', 'true');
  });

  it('handles empty timestamp gracefully', () => {
    render(<SystemMessage {...baseProps} createdAt="" />);

    // Should still render the message
    expect(screen.getByText('Booking confirmed')).toBeInTheDocument();
  });

  it('renders bookingId when provided', () => {
    render(<SystemMessage {...baseProps} bookingId="booking-123" />);

    // bookingId is passed but not displayed in the current implementation
    // This test ensures the prop doesn't cause issues
    expect(screen.getByText('Booking confirmed')).toBeInTheDocument();
  });
});
