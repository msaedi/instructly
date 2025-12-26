import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { CancelWarningModal } from '@/components/lessons/modals/CancelWarningModal';
import type { Booking } from '@/features/shared/api/types';
import * as myLessonsModule from '@/hooks/useMyLessons';

// Mock the useMyLessons hook with new CancellationFeeResult interface
jest.mock('@/hooks/useMyLessons', () => ({
  calculateCancellationFee: jest.fn(() => ({
    hoursUntil: 72,
    window: 'free',
    lessonPrice: 53.57,
    platformFee: 6.43,
    creditAmount: 0,
    willReceiveCredit: false,
  }))
}));

// Mock the CancellationReasonModal component
jest.mock('@/components/lessons/modals/CancellationReasonModal', () => ({
  CancellationReasonModal: ({ isOpen, onClose, onReschedule }: { isOpen: boolean; onClose: () => void; onReschedule: () => void }) => {
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
    instructor_id: '01K2MAY484FQGFEQVN3VKGYZ59',
    student_id: '01K2MAY484FQGFEQVN3VKGYZ60',
    // minimal fields to satisfy generated shape when accessed in component/tests
    updated_at: '2025-12-25T15:00:00Z',
  } as unknown as Booking;

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
    // Mock a late cancellation scenario (12-24h window = credit)
    const calculateCancellationFee = myLessonsModule.calculateCancellationFee as jest.Mock;
    calculateCancellationFee.mockReturnValue({
      hoursUntil: 18,
      window: 'credit',
      lessonPrice: 53.57,
      platformFee: 6.43,
      creditAmount: 53.57,
      willReceiveCredit: true,
    });

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
    // Mock >24 hours until lesson to show free cancellation with reschedule option
    const calculateCancellationFee = myLessonsModule.calculateCancellationFee as jest.Mock;
    calculateCancellationFee.mockReturnValue({
      hoursUntil: 48,
      window: 'free',
      lessonPrice: 53.57,
      platformFee: 6.43,
      creditAmount: 0,
      willReceiveCredit: false,
    });

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
    // Mock the calculateCancellationFee to return free window (>24h)
    const calculateCancellationFee = myLessonsModule.calculateCancellationFee as jest.Mock;
    calculateCancellationFee.mockReturnValue({
      hoursUntil: 120, // 5 days = 120 hours
      window: 'free',
      lessonPrice: 53.57,
      platformFee: 6.43,
      creditAmount: 0,
      willReceiveCredit: false,
    });

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

  it('shows credit window for 12-24h cancellation', () => {
    const calculateCancellationFee = myLessonsModule.calculateCancellationFee as jest.Mock;
    calculateCancellationFee.mockReturnValue({
      hoursUntil: 18, // 18 hours = credit window
      window: 'credit',
      lessonPrice: 53.57,
      platformFee: 6.43,
      creditAmount: 53.57,
      willReceiveCredit: true,
    });

    render(
      <CancelWarningModal
        isOpen={true}
        onClose={mockOnClose}
        lesson={mockBooking}
        onReschedule={mockOnReschedule}
      />
    );

    // Shows credit message and time until lesson (18 hours = > 12 hours)
    expect(screen.getByText('> 12 hours')).toBeInTheDocument();
    expect(screen.getByText(/Credit: \$53\.57/)).toBeInTheDocument();
  });

  it('shows full charge for very late cancellation', () => {
    const calculateCancellationFee = myLessonsModule.calculateCancellationFee as jest.Mock;
    calculateCancellationFee.mockReturnValue({
      hoursUntil: 8, // 8 hours = full window
      window: 'full',
      lessonPrice: 53.57,
      platformFee: 6.43,
      creditAmount: 0,
      willReceiveCredit: false,
    });

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
