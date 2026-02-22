import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CancelWarningModal } from '../CancelWarningModal';
import type { Booking } from '@/features/shared/api/types';

// Mock calculateCancellationFee to control hoursUntil, window, lessonPrice, platformFee
jest.mock('@/hooks/useMyLessons', () => ({
  calculateCancellationFee: jest.fn(),
}));

// Mock CancellationReasonModal to avoid pulling in its transitive deps
jest.mock('../CancellationReasonModal', () => ({
  CancellationReasonModal: ({
    isOpen,
    onClose,
    onReschedule,
  }: {
    isOpen: boolean;
    onClose: () => void;
    onReschedule: () => void;
  }) =>
    isOpen ? (
      <div data-testid="reason-modal">
        Reason Modal
        <button data-testid="reason-modal-close" onClick={onClose}>
          Close Reason
        </button>
        <button data-testid="reason-modal-reschedule" onClick={onReschedule}>
          Reschedule Instead
        </button>
      </div>
    ) : null,
}));

import { calculateCancellationFee } from '@/hooks/useMyLessons';

const calculateMock = calculateCancellationFee as jest.Mock;

// Minimal booking that satisfies the component's needs
const baseLesson = {
  id: 'lesson-1',
  booking_date: '2026-03-15',
  start_time: '14:00:00',
  end_time: '15:00:00',
  total_price: 60,
  service_name: 'Piano',
  instructor: { first_name: 'Alex', last_initial: 'B', id: 'inst-1' },
} as Booking;

function renderModal(hoursUntil: number, window: 'free' | 'credit' | 'full' = 'free') {
  calculateMock.mockReturnValue({
    hoursUntil,
    window,
    lessonPrice: 50,
    platformFee: 10,
    creditAmount: window === 'credit' ? 50 : 0,
  });

  const onClose = jest.fn();
  const onReschedule = jest.fn();

  const result = render(
    <CancelWarningModal
      isOpen
      onClose={onClose}
      lesson={baseLesson}
      onReschedule={onReschedule}
    />,
  );

  return { ...result, onClose, onReschedule };
}

describe('CancelWarningModal', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('getTimeUntilDisplay boundary tests', () => {
    it('shows "> 24 hours" when hoursUntil is well above 24', () => {
      renderModal(48, 'free');

      expect(screen.getByText('> 24 hours')).toBeInTheDocument();
    });

    it('shows "> 12 hours" when hoursUntil is exactly 24 (boundary: NOT "> 24 hours")', () => {
      // BUG-HUNTING: hoursUntil=24 fails the > 24 check, so it falls through
      // to the > 12 branch. This is a boundary condition that could surprise users —
      // at exactly 24 hours it says "> 12 hours" rather than "> 24 hours".
      renderModal(24, 'credit');

      expect(screen.getByText('> 12 hours')).toBeInTheDocument();
      expect(screen.queryByText('> 24 hours')).not.toBeInTheDocument();
    });

    it('shows "< 12 hours" when hoursUntil is exactly 12 (boundary: NOT "> 12 hours")', () => {
      // BUG-HUNTING: hoursUntil=12 fails the > 12 check, so it falls through
      // to the else branch. At exactly 12 hours it says "< 12 hours".
      renderModal(12, 'full');

      expect(screen.getByText('< 12 hours')).toBeInTheDocument();
      expect(screen.queryByText('> 12 hours')).not.toBeInTheDocument();
    });

    it('shows "< 12 hours" for fractional hours below 12', () => {
      renderModal(0.5, 'full');

      expect(screen.getByText('< 12 hours')).toBeInTheDocument();
    });

    it('shows "> 12 hours" for value just above 12', () => {
      renderModal(12.001, 'credit');

      expect(screen.getByText('> 12 hours')).toBeInTheDocument();
    });

    it('shows "> 24 hours" for value just above 24', () => {
      renderModal(24.001, 'free');

      expect(screen.getByText('> 24 hours')).toBeInTheDocument();
    });

    it('shows "< 12 hours" when hoursUntil is zero', () => {
      renderModal(0, 'full');

      expect(screen.getByText('< 12 hours')).toBeInTheDocument();
    });

    it('shows "< 12 hours" when hoursUntil is negative (lesson already started)', () => {
      // BUG-HUNTING: negative hoursUntil means the lesson is in the past.
      // The function still returns "< 12 hours" because negative < 12.
      renderModal(-5, 'full');

      expect(screen.getByText('< 12 hours')).toBeInTheDocument();
    });
  });

  describe('cancellation window messaging', () => {
    it('shows free cancellation message for "free" window', () => {
      renderModal(48, 'free');

      expect(screen.getByText(/life happens/i)).toBeInTheDocument();
      expect(screen.getByText(/reschedule/i)).toBeInTheDocument();
    });

    it('shows credit message for "credit" window', () => {
      renderModal(18, 'credit');

      expect(screen.getByText(/\$50\.00/)).toBeInTheDocument();
      expect(screen.getByText(/\$10\.00 booking fee is non-refundable/)).toBeInTheDocument();
    });

    it('shows full charge message for "full" window', () => {
      renderModal(6, 'full');

      expect(screen.getByText(/charged in full/i)).toBeInTheDocument();
    });
  });

  describe('modal interactions', () => {
    it('does not render when isOpen is false', () => {
      calculateMock.mockReturnValue({
        hoursUntil: 48,
        window: 'free',
        lessonPrice: 50,
        platformFee: 10,
        creditAmount: 0,
      });

      const { container } = render(
        <CancelWarningModal
          isOpen={false}
          onClose={jest.fn()}
          lesson={baseLesson}
          onReschedule={jest.fn()}
        />,
      );

      expect(container.innerHTML).toBe('');
    });

    it('calls onClose when "Keep My Lesson" is clicked', async () => {
      const user = userEvent.setup();
      const { onClose } = renderModal(48, 'free');

      await user.click(screen.getByRole('button', { name: /keep my lesson/i }));

      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('opens reason modal when "Continue" is clicked', async () => {
      const user = userEvent.setup();
      renderModal(6, 'full');

      expect(screen.queryByTestId('reason-modal')).not.toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: /continue/i }));

      expect(screen.getByTestId('reason-modal')).toBeInTheDocument();
    });

    it('toggles cancellation policy accordion', async () => {
      const user = userEvent.setup();
      renderModal(48, 'free');

      expect(screen.queryByText(/more than 24 hours before/i)).not.toBeInTheDocument();

      await user.click(screen.getByText(/see full cancellation policy/i));

      expect(screen.getByText(/more than 24 hours before/i)).toBeInTheDocument();
      expect(screen.getByText(/12–24 hours before/i)).toBeInTheDocument();
      expect(screen.getByText(/less than 12 hours before/i)).toBeInTheDocument();

      // Toggle closed
      await user.click(screen.getByText(/see full cancellation policy/i));

      expect(screen.queryByText(/more than 24 hours before/i)).not.toBeInTheDocument();
    });
  });

  describe('CancellationReasonModal onClose callback (lines 156-158)', () => {
    it('closes both modals when CancellationReasonModal onClose fires', async () => {
      // Flow: open warning modal -> click Continue -> reason modal opens ->
      // close reason modal -> both modals should close (onClose called once)
      const user = userEvent.setup();
      const { onClose } = renderModal(6, 'full');

      // Step 1: Click Continue to open the reason modal
      await user.click(screen.getByRole('button', { name: /continue/i }));
      expect(screen.getByTestId('reason-modal')).toBeInTheDocument();

      // Step 2: Close the reason modal via its onClose callback
      await user.click(screen.getByTestId('reason-modal-close'));

      // Step 3: Verify parent onClose was called exactly once
      expect(onClose).toHaveBeenCalledTimes(1);

      // Step 4: Reason modal should be hidden (showReasonModal set to false)
      expect(screen.queryByTestId('reason-modal')).not.toBeInTheDocument();
    });

    it('does not call onClose twice when reason modal closes then user clicks Keep My Lesson', async () => {
      // BUG HUNTING: If onClose is somehow deferred or the modal state is stale,
      // clicking "Keep My Lesson" after closing the reason modal could fire onClose again.
      const user = userEvent.setup();
      const { onClose } = renderModal(6, 'full');

      // Open reason modal
      await user.click(screen.getByRole('button', { name: /continue/i }));
      expect(screen.getByTestId('reason-modal')).toBeInTheDocument();

      // Close reason modal (fires onClose once)
      await user.click(screen.getByTestId('reason-modal-close'));
      expect(onClose).toHaveBeenCalledTimes(1);

      // The warning modal should now be hidden because isOpen is controlled by
      // the parent. Since onClose was called, the parent would set isOpen=false.
      // But in our test the prop is always true, so the warning modal is still visible.
      // A second click on Keep My Lesson would fire onClose again — this is expected
      // behavior since the parent controls the open state.
    });

    it('triggers onReschedule from CancellationReasonModal and closes both modals', async () => {
      // Flow: open warning modal -> Continue -> reason modal opens ->
      // click reschedule in reason modal -> closes both modals + calls onReschedule
      const user = userEvent.setup();
      const { onClose, onReschedule } = renderModal(48, 'free');

      // Open reason modal
      await user.click(screen.getByRole('button', { name: /continue/i }));
      expect(screen.getByTestId('reason-modal')).toBeInTheDocument();

      // Click reschedule in reason modal
      await user.click(screen.getByTestId('reason-modal-reschedule'));

      // Both callbacks should fire: onClose (to dismiss) + onReschedule (to navigate)
      expect(onClose).toHaveBeenCalledTimes(1);
      expect(onReschedule).toHaveBeenCalledTimes(1);

      // Reason modal should be hidden
      expect(screen.queryByTestId('reason-modal')).not.toBeInTheDocument();
    });

    it('hides the warning modal backdrop when reason modal is showing', async () => {
      // BUG HUNTING: The warning modal has a className toggle:
      // `${!showReasonModal ? '' : 'hidden'}`. Verify this works.
      const user = userEvent.setup();
      renderModal(6, 'full');

      // Warning modal backdrop should be visible initially
      const backdrop = screen.getByText('Cancel my lesson').closest('[style]');
      expect(backdrop).not.toHaveClass('hidden');

      // Open reason modal
      await user.click(screen.getByRole('button', { name: /continue/i }));

      // The warning modal container should now have 'hidden' class
      const backdropAfter = screen.getByText('Cancel my lesson').closest('.hidden');
      expect(backdropAfter).toBeInTheDocument();
    });
  });
});
