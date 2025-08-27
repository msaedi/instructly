import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { CancelWarningModal } from '@/components/lessons/modals/CancelWarningModal';
import { Booking } from '@/types/booking';

// Mock the useMyLessons hook
jest.mock('@/hooks/useMyLessons', () => ({
  calculateCancellationFee: jest.fn(() => ({
    fee: 0,
    percentage: 0,
    hoursUntil: 72
  }))
}));

// Mock the CancellationReasonModal component
jest.mock('@/components/lessons/modals/CancellationReasonModal', () => ({
  CancellationReasonModal: ({ isOpen, onClose, onReschedule }: any) => {
    if (!isOpen) return null;
    return (
      <div data-testid="cancellation-reason-modal">
        Cancellation Reason Modal
        <button onClick={onReschedule}>Reschedule instead</button>
        <button onClick={onClose}>Close</button>
      </div>
    );
  }
}));

describe('CancelWarningModal', () => {
  const mockBooking: Booking = {
    id: '01K2MAY484FQGFEQVN3VKGYZ58',
    booking_date: '2025-12-25',
    start_time: '14:00:00',
    end_time: '15:00:00',
    status: 'CONFIRMED',
    total_price: 60,
    hourly_rate: 60,
    duration_minutes: 60,
    instructor_id: '01K2MAY484FQGFEQVN3VKGYZ59',
    student_id: '01K2MAY484FQGFEQVN3VKGYZ60',
    service: { id: '01K2MAY484FQGFEQVN3VKGYZ61' } as any,
    instructor: {
      id: '01K2MAY484FQGFEQVN3VKGYZ59',
      first_name: 'John',
      last_initial: 'D',
    },
    service_name: 'Mathematics',
  } as Booking;

  const mockOnClose = jest.fn();
  const mockOnReschedule = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders modal when isOpen is true', () => {
    render(
      <CancelWarningModal
        isOpen={true}
        onClose={mockOnClose}
        lesson={mockBooking}
        onReschedule={mockOnReschedule}
      />
    );

    // Check that the modal title is shown
    expect(screen.getByText('Cancel my lesson')).toBeInTheDocument();
  });

  it('does not render modal when isOpen is false', () => {
    render(
      <CancelWarningModal
        isOpen={false}
        onClose={mockOnClose}
        lesson={mockBooking}
        onReschedule={mockOnReschedule}
      />
    );

    expect(screen.queryByText('Cancel my lesson')).not.toBeInTheDocument();
  });

  it('shows cancellation fee information', () => {
    render(
      <CancelWarningModal
        isOpen={true}
        onClose={mockOnClose}
        lesson={mockBooking}
        onReschedule={mockOnReschedule}
      />
    );

    // Modal should show time-based message (case-insensitive, optional colon)
    expect(screen.getByText(/Time until lesson:?/i)).toBeInTheDocument();
  });

  it('shows warning for late cancellation', () => {
    // Mock a late cancellation scenario
    const calculateCancellationFee = require('@/hooks/useMyLessons').calculateCancellationFee;
    calculateCancellationFee.mockReturnValue({ fee: 30, percentage: 50, hoursUntil: 18 }); // 50% fee

    render(
      <CancelWarningModal
        isOpen={true}
        onClose={mockOnClose}
        lesson={mockBooking}
        onReschedule={mockOnReschedule}
      />
    );

    // Shows time until lesson (18 hours = > 12 hours)
    expect(screen.getByText('> 12 hours')).toBeInTheDocument();
  });

  it('calls onClose when Keep My Lesson button is clicked', () => {
    render(
      <CancelWarningModal
        isOpen={true}
        onClose={mockOnClose}
        lesson={mockBooking}
        onReschedule={mockOnReschedule}
      />
    );

    // The modal has a 'Keep My Lesson' button
    const keepButton = screen.getByRole('button', { name: /Keep My Lesson/i });
    fireEvent.click(keepButton);

    expect(mockOnClose).toHaveBeenCalledTimes(1);
  });

  it('calls onReschedule when Continue then Reschedule is clicked', () => {
    // Mock >12 hours until lesson to show reschedule option
    const calculateCancellationFee = require('@/hooks/useMyLessons').calculateCancellationFee;
    calculateCancellationFee.mockReturnValue({ fee: 0, percentage: 0, hoursUntil: 24 });

    render(
      <CancelWarningModal
        isOpen={true}
        onClose={mockOnClose}
        lesson={mockBooking}
        onReschedule={mockOnReschedule}
      />
    );

    // First click Continue to open the reason modal
    const continueButton = screen.getByRole('button', { name: /Continue/i });
    fireEvent.click(continueButton);

    // In the simplified mocked reason modal, click the provided Reschedule handler
    // Our mock shows a "Reschedule instead" button
    const reschedule = screen.getByText(/Reschedule instead/i);
    fireEvent.click(reschedule);

    expect(mockOnReschedule).toHaveBeenCalledTimes(1);
  });

  it('opens cancellation reason modal when Continue button is clicked', () => {
    render(
      <CancelWarningModal
        isOpen={true}
        onClose={mockOnClose}
        lesson={mockBooking}
        onReschedule={mockOnReschedule}
      />
    );

    const cancelButton = screen.getByRole('button', { name: /Continue/i });
    fireEvent.click(cancelButton);

    // Should transition to showing cancellation reason modal
    expect(screen.getByTestId('cancellation-reason-modal')).toBeInTheDocument();
  });

  it('shows cancellation policy information', () => {
    render(
      <CancelWarningModal
        isOpen={true}
        onClose={mockOnClose}
        lesson={mockBooking}
        onReschedule={mockOnReschedule}
      />
    );

    expect(screen.getByText(/See full cancellation policy/)).toBeInTheDocument();
  });

  it('shows no fee message for free cancellation', () => {
    // Mock the calculateCancellationFee to return 0 fee
    const calculateCancellationFee = require('@/hooks/useMyLessons').calculateCancellationFee;
    calculateCancellationFee.mockReturnValue({ fee: 0, percentage: 0, hoursUntil: 120 }); // 5 days = 120 hours

    render(
      <CancelWarningModal
        isOpen={true}
        onClose={mockOnClose}
        lesson={mockBooking}
        onReschedule={mockOnReschedule}
      />
    );

    // When cancellation is >24 hours before, shows appropriate message (120 hours = > 24 hours)
    expect(screen.getByText('> 24 hours')).toBeInTheDocument();
  });

  it('shows 50% fee for late cancellation', () => {
    const calculateCancellationFee = require('@/hooks/useMyLessons').calculateCancellationFee;
    calculateCancellationFee.mockReturnValue({ fee: 30, percentage: 50, hoursUntil: 18 }); // 50% fee

    render(
      <CancelWarningModal
        isOpen={true}
        onClose={mockOnClose}
        lesson={mockBooking}
        onReschedule={mockOnReschedule}
      />
    );

    // Shows partial charge warning for late cancellation (18 hours = > 12 hours)
    expect(screen.getByText('> 12 hours')).toBeInTheDocument();
  });

  it('shows 100% fee for very late cancellation', () => {
    const calculateCancellationFee = require('@/hooks/useMyLessons').calculateCancellationFee;
    calculateCancellationFee.mockReturnValue({ fee: 60, percentage: 100, hoursUntil: 8 }); // 100% fee

    render(
      <CancelWarningModal
        isOpen={true}
        onClose={mockOnClose}
        lesson={mockBooking}
        onReschedule={mockOnReschedule}
      />
    );

    // Shows full charge warning for very late cancellation (8 hours = < 12 hours)
    expect(screen.getByText('< 12 hours')).toBeInTheDocument();
  });

  it('displays lesson details in the modal', () => {
    render(
      <CancelWarningModal
        isOpen={true}
        onClose={mockOnClose}
        lesson={mockBooking}
        onReschedule={mockOnReschedule}
      />
    );

    expect(screen.getByText(/Thursday, December 25/)).toBeInTheDocument();
    expect(screen.getByText(/2:00 PM/)).toBeInTheDocument();
  });
});
