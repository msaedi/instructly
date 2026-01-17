import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CancelBookingModal } from '../CancelBookingModal';
import type { Booking } from '@/types/booking';

// Mock the logger
jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
  },
}));

// Mock the formatting functions
jest.mock('@/lib/timezone/formatBookingTime', () => ({
  formatBookingDate: jest.fn(() => 'Wednesday, January 15, 2025'),
  formatBookingTimeRange: jest.fn(() => '2:00 PM - 3:00 PM'),
}));

describe('CancelBookingModal', () => {
  const mockBooking: Booking = {
    id: '01K2MAY484FQGFEQVN3VKGYZ58',
    booking_date: '2025-01-15',
    start_time: '14:00:00',
    end_time: '15:00:00',
    status: 'CONFIRMED',
    total_price: 60,
    instructor_id: '01K2MAY484FQGFEQVN3VKGYZ59',
    student_id: '01K2MAY484FQGFEQVN3VKGYZ60',
    service_name: 'Piano Lesson',
    hourly_rate: 60,
    duration_minutes: 60,
    instructor_service_id: '01K2MAY484FQGFEQVN3VKGYZ61',
    updated_at: '2025-01-10T15:00:00Z',
    instructor: {
      id: '01K2MAY484FQGFEQVN3VKGYZ59',
      first_name: 'John',
      last_initial: 'D',
    },
  } as Booking;

  const defaultProps = {
    booking: mockBooking,
    isOpen: true,
    onClose: jest.fn(),
    onConfirm: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders when open with booking', () => {
    render(<CancelBookingModal {...defaultProps} />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Booking Details')).toBeInTheDocument();
  });

  it('does not render when isOpen is false', () => {
    render(<CancelBookingModal {...defaultProps} isOpen={false} />);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('does not render when booking is null', () => {
    render(<CancelBookingModal {...defaultProps} booking={null} />);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('displays booking details correctly', () => {
    render(<CancelBookingModal {...defaultProps} />);

    expect(screen.getByText('Wednesday, January 15, 2025')).toBeInTheDocument();
    expect(screen.getByText('2:00 PM - 3:00 PM')).toBeInTheDocument();
    expect(screen.getByText('Piano Lesson')).toBeInTheDocument();
    expect(screen.getByText('John D.')).toBeInTheDocument();
  });

  it('displays unknown instructor when instructor is missing', () => {
    const bookingWithoutInstructor = { ...mockBooking, instructor: undefined };
    render(
      <CancelBookingModal {...defaultProps} booking={bookingWithoutInstructor} />
    );

    expect(screen.getByText('Unknown Instructor')).toBeInTheDocument();
  });

  it('shows cancellation policy warning', () => {
    render(<CancelBookingModal {...defaultProps} />);

    expect(screen.getByText('Cancellation Policy')).toBeInTheDocument();
    expect(
      screen.getByText(/cancellations may be subject to/i)
    ).toBeInTheDocument();
  });

  it('disables submit button when reason is empty', () => {
    render(<CancelBookingModal {...defaultProps} />);

    const submitButton = screen.getByRole('button', { name: /cancel booking/i });
    expect(submitButton).toBeDisabled();
  });

  it('enables submit button when reason is provided', async () => {
    const user = userEvent.setup();
    render(<CancelBookingModal {...defaultProps} />);

    await user.type(
      screen.getByPlaceholderText(/please let us know/i),
      'Schedule conflict'
    );

    const submitButton = screen.getByRole('button', { name: /cancel booking/i });
    expect(submitButton).not.toBeDisabled();
  });

  it('calls onConfirm with reason on successful submission', async () => {
    const user = userEvent.setup();
    const onConfirm = jest.fn().mockResolvedValue(undefined);
    render(<CancelBookingModal {...defaultProps} onConfirm={onConfirm} />);

    await user.type(
      screen.getByPlaceholderText(/please let us know/i),
      'Schedule conflict'
    );
    await user.click(screen.getByRole('button', { name: /cancel booking/i }));

    await waitFor(() => {
      expect(onConfirm).toHaveBeenCalledWith('Schedule conflict');
    });
  });

  it('shows loading state during submission', async () => {
    const user = userEvent.setup();
    let resolveConfirm: () => void;
    const onConfirm = jest.fn(
      () => new Promise<void>((resolve) => (resolveConfirm = resolve))
    );
    render(<CancelBookingModal {...defaultProps} onConfirm={onConfirm} />);

    await user.type(
      screen.getByPlaceholderText(/please let us know/i),
      'Schedule conflict'
    );
    await user.click(screen.getByRole('button', { name: /cancel booking/i }));

    expect(screen.getByText(/cancelling/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /keep booking/i })).toBeDisabled();

    resolveConfirm!();
  });

  it('clears reason after successful cancellation', async () => {
    const user = userEvent.setup();
    const onConfirm = jest.fn().mockResolvedValue(undefined);
    render(<CancelBookingModal {...defaultProps} onConfirm={onConfirm} />);

    const textArea = screen.getByPlaceholderText(/please let us know/i);
    await user.type(textArea, 'Schedule conflict');
    await user.click(screen.getByRole('button', { name: /cancel booking/i }));

    await waitFor(() => {
      expect(textArea).toHaveValue('');
    });
  });

  it('calls onClose when Keep Booking button is clicked', async () => {
    const user = userEvent.setup();
    render(<CancelBookingModal {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: /keep booking/i }));

    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
  });

  it('prevents closing modal while loading', async () => {
    const user = userEvent.setup();
    let resolveConfirm: () => void;
    const onConfirm = jest.fn(
      () => new Promise<void>((resolve) => (resolveConfirm = resolve))
    );
    const onClose = jest.fn();
    render(
      <CancelBookingModal
        {...defaultProps}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    await user.type(
      screen.getByPlaceholderText(/please let us know/i),
      'Schedule conflict'
    );
    await user.click(screen.getByRole('button', { name: /cancel booking/i }));

    // Try to close while loading
    const keepButton = screen.getByRole('button', { name: /keep booking/i });
    await user.click(keepButton);

    expect(onClose).not.toHaveBeenCalled();

    resolveConfirm!();
  });

  it('displays external error when provided', () => {
    render(
      <CancelBookingModal
        {...defaultProps}
        error="Server error: Unable to cancel booking"
      />
    );

    expect(
      screen.getByText('Server error: Unable to cancel booking')
    ).toBeInTheDocument();
  });

  it('has proper aria attributes for accessibility', () => {
    render(<CancelBookingModal {...defaultProps} error="Some error" />);

    const textarea = screen.getByPlaceholderText(/please let us know/i);
    expect(textarea).toHaveAttribute('aria-invalid', 'true');
    expect(textarea).toHaveAttribute('aria-describedby', 'error-message');
  });

  it('resets state on close', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<CancelBookingModal {...defaultProps} />);

    // Type in textarea and trigger error
    await user.type(
      screen.getByPlaceholderText(/please let us know/i),
      'test'
    );

    // Close modal
    await user.click(screen.getByRole('button', { name: /keep booking/i }));
    rerender(<CancelBookingModal {...defaultProps} isOpen={false} />);
    rerender(<CancelBookingModal {...defaultProps} isOpen={true} />);

    // Check state is reset
    expect(screen.getByPlaceholderText(/please let us know/i)).toHaveValue('');
  });
});
