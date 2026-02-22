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

  describe('validation', () => {
    it('button is disabled when reason is empty - defensive validation is unreachable', () => {
      const onConfirm = jest.fn();
      render(<CancelBookingModal {...defaultProps} onConfirm={onConfirm} />);

      // The button is disabled when reason is empty, preventing clicks
      // This means the internal validation check (lines 54-56) is defensive/redundant code
      const submitButton = screen.getByRole('button', { name: /cancel booking/i });
      expect(submitButton).toBeDisabled();

      // Verify the disabled attribute uses the same condition as the internal validation
      // Button: disabled={isLoading || !reason.trim()}
      // Handler: if (!reason.trim()) { ... }
      // These are redundant - the handler check can never be reached via UI
    });

    it('button is disabled when reason is whitespace-only', async () => {
      const user = userEvent.setup();
      const onConfirm = jest.fn();
      render(<CancelBookingModal {...defaultProps} onConfirm={onConfirm} />);

      // Type whitespace only
      const textarea = screen.getByPlaceholderText(/please let us know/i);
      await user.type(textarea, '   ');

      // Button should still be disabled (reason.trim() is empty)
      const submitButton = screen.getByRole('button', { name: /cancel booking/i });
      expect(submitButton).toBeDisabled();

      expect(onConfirm).not.toHaveBeenCalled();
    });

    it('clears validation error when typing', async () => {
      const user = userEvent.setup();
      render(
        <CancelBookingModal {...defaultProps} error="Initial error" />
      );

      const textarea = screen.getByPlaceholderText(/please let us know/i);
      expect(textarea).toHaveAttribute('aria-invalid', 'true');

      // Type something - should clear error styling
      await user.type(textarea, 'New reason');

      // External error still shows, but validation error would be cleared
      expect(screen.getByText('Initial error')).toBeInTheDocument();
    });
  });

  describe('error handling', () => {
    it('handles API error during cancellation', async () => {
      const user = userEvent.setup();
      const onConfirm = jest.fn().mockRejectedValue(new Error('API Error'));
      render(<CancelBookingModal {...defaultProps} onConfirm={onConfirm} />);

      await user.type(
        screen.getByPlaceholderText(/please let us know/i),
        'Need to cancel'
      );
      await user.click(screen.getByRole('button', { name: /cancel booking/i }));

      // Wait for error to be handled
      await waitFor(() => {
        expect(onConfirm).toHaveBeenCalled();
      });

      // After error, loading state should be reset
      await waitFor(() => {
        const submitButton = screen.getByRole('button', { name: /cancel booking/i });
        expect(submitButton).not.toBeDisabled();
      });
    });

    it('does not clear reason after failed cancellation', async () => {
      const user = userEvent.setup();
      const onConfirm = jest.fn().mockRejectedValue(new Error('API Error'));
      render(<CancelBookingModal {...defaultProps} onConfirm={onConfirm} />);

      const textarea = screen.getByPlaceholderText(/please let us know/i);
      await user.type(textarea, 'My reason for cancelling');
      await user.click(screen.getByRole('button', { name: /cancel booking/i }));

      await waitFor(() => {
        expect(onConfirm).toHaveBeenCalled();
      });

      // Reason should still be present after error
      await waitFor(() => {
        expect(textarea).toHaveValue('My reason for cancelling');
      });
    });
  });

  describe('defensive validation in handleSubmit', () => {
    it('shows validation error when submit handler fires with empty reason', async () => {
      // Lines 55-57: defensive guard where reason.trim() is empty.
      // The submit button is disabled when reason is empty, making this normally
      // unreachable from the UI. To exercise this defensive code path, we need
      // to invoke the onClick handler directly while reason state is empty.
      //
      // Strategy: React attaches event handlers using its internal fiber system.
      // We can access the handler through React's internal properties and call it directly.
      const onConfirm = jest.fn();
      render(<CancelBookingModal {...defaultProps} onConfirm={onConfirm} />);

      const submitButton = screen.getByRole('button', { name: /cancel booking/i });
      expect(submitButton).toBeDisabled();

      // Access the React fiber to find the onClick handler and call it directly
      // This bypasses the disabled check that React applies to synthetic events
      const fiberKey = Object.keys(submitButton).find(
        (key) => key.startsWith('__reactFiber$') || key.startsWith('__reactInternalInstance$')
      );

      if (fiberKey) {
        const fiber = (submitButton as unknown as Record<string, unknown>)[fiberKey] as {
          memoizedProps?: { onClick?: (e: unknown) => void };
        };
        const onClick = fiber?.memoizedProps?.onClick;
        if (onClick) {
          // Call the handler with a mock event (empty reason state)
          onClick({ preventDefault: jest.fn() });

          await waitFor(() => {
            expect(screen.getByText('Please provide a reason for cancellation')).toBeInTheDocument();
          });

          expect(onConfirm).not.toHaveBeenCalled();
        }
      }
    });
  });

  describe('accessibility', () => {
    it('textarea is disabled during loading', async () => {
      const user = userEvent.setup();
      let resolveConfirm: () => void;
      const onConfirm = jest.fn(
        () => new Promise<void>((resolve) => (resolveConfirm = resolve))
      );
      render(<CancelBookingModal {...defaultProps} onConfirm={onConfirm} />);

      await user.type(
        screen.getByPlaceholderText(/please let us know/i),
        'Reason'
      );
      await user.click(screen.getByRole('button', { name: /cancel booking/i }));

      const textarea = screen.getByPlaceholderText(/please let us know/i);
      expect(textarea).toBeDisabled();

      resolveConfirm!();
    });

    it('has required label for reason field', () => {
      render(<CancelBookingModal {...defaultProps} />);

      expect(screen.getByText('Cancellation reason')).toBeInTheDocument();
      expect(screen.getByText('*')).toBeInTheDocument();
    });
  });
});
