import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RescheduleModal } from '../RescheduleModal';
import type { Booking } from '@/features/shared/api/types';
import { toast } from 'sonner';

// Track the onTimeSelected callback captured from the mock
let capturedOnTimeSelected: ((selection: {
  date: string;
  time: string;
  duration: number;
}) => void) | null = null;
let capturedOnOpenChat: (() => void) | null = null;

// Mock sonner toast
jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
  },
}));

// Mock next/navigation
const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

// Mock useAuth
jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 'user-1', first_name: 'Student' },
  }),
}));

// Mock RescheduleTimeSelectionModal to capture callbacks
jest.mock('../RescheduleTimeSelectionModal', () => {
  return function MockRescheduleTimeSelection({
    isOpen,
    onTimeSelected,
    onOpenChat,
  }: {
    isOpen: boolean;
    onClose: () => void;
    onTimeSelected: (selection: { date: string; time: string; duration: number }) => void;
    onOpenChat: () => void;
    instructor: unknown;
    currentLesson: unknown;
  }) {
    capturedOnTimeSelected = onTimeSelected;
    capturedOnOpenChat = onOpenChat;
    return isOpen ? (
      <div data-testid="time-selection-modal">Time Selection</div>
    ) : null;
  };
});

// Mock ChatModal
jest.mock('@/components/chat/ChatModal', () => ({
  ChatModal: ({
    isOpen,
    onClose,
  }: {
    isOpen: boolean;
    onClose: () => void;
  }) =>
    isOpen ? (
      <div data-testid="chat-modal">
        <button data-testid="close-chat" onClick={onClose}>
          Close Chat
        </button>
      </div>
    ) : null,
}));

// Mock the dynamic import of bookings service.
// We use a getter so we can make it throw to simulate import failure.
const rescheduleBookingImperativeMock = jest.fn();
let throwOnAccess = false;
jest.mock('@/src/api/services/bookings', () => ({
  get rescheduleBookingImperative() {
    if (throwOnAccess) {
      throw new Error('Failed to load module');
    }
    return rescheduleBookingImperativeMock;
  },
}));

// Mock the react-query client import (used inside the success path)
jest.mock('@/lib/react-query/queryClient', () => ({
  queryClient: {
    invalidateQueries: jest.fn().mockResolvedValue(undefined),
  },
  queryKeys: {
    bookings: {
      all: ['bookings', 'all'],
      history: () => ['bookings', 'history'],
    },
  },
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
  },
}));

const baseLesson = {
  id: 'booking-1',
  booking_date: '2026-03-20',
  start_time: '10:00:00',
  end_time: '11:00:00',
  duration_minutes: 60,
  hourly_rate: 80,
  service_name: 'Piano',
  instructor_id: 'inst-1',
  instructor_service_id: 'is-1',
  instructor: { first_name: 'Alex', last_initial: 'B', id: 'inst-1' },
} as Booking;

const defaultSelection = { date: '2026-03-25', time: '2:00pm', duration: 60 };

describe('RescheduleModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    lesson: baseLesson,
  };

  beforeEach(() => {
    jest.clearAllMocks();
    capturedOnTimeSelected = null;
    capturedOnOpenChat = null;
    throwOnAccess = false;

    // Default: dynamic import resolves with a working mock
    rescheduleBookingImperativeMock.mockResolvedValue({ id: 'new-booking-1' });
  });

  describe('dynamic import .catch() — network error (line 128-130)', () => {
    it('shows network error toast when module access throws during destructuring', async () => {
      // The .catch() on line 128 fires when the dynamic import's .then()
      // promise is rejected. We simulate a module load failure by making
      // the getter for `rescheduleBookingImperative` throw. This causes
      // the destructuring `{ rescheduleBookingImperative }` in the .then()
      // callback to throw synchronously BEFORE the inner try/catch,
      // rejecting the promise and propagating to .catch().
      throwOnAccess = true;

      render(<RescheduleModal {...defaultProps} />);

      expect(capturedOnTimeSelected).not.toBeNull();
      capturedOnTimeSelected!(defaultSelection);

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          'Network error while rescheduling. Please try again.'
        );
      });
    });
  });

  describe('outer try/catch — synchronous parsing error (line 131-133)', () => {
    it('shows unexpected error toast when time parsing throws inside the try block', () => {
      render(<RescheduleModal {...defaultProps} />);

      expect(capturedOnTimeSelected).not.toBeNull();

      // The outer catch on line 131 catches synchronous errors from lines 60-70
      // (time parsing) and the dynamic import() call on line 73.
      //
      // selection.time is accessed at line 47 (before try) and line 61 (inside try).
      // We use a counter-based getter that returns a valid string on the first
      // access (line 47) but throws on the second access (line 61, inside try).
      let accessCount = 0;
      const throwingSelection = {
        date: '2026-03-25',
        get time(): string {
          accessCount++;
          if (accessCount > 1) {
            throw new Error('Simulated parsing failure');
          }
          return '2:00pm';
        },
        duration: 60,
      };

      capturedOnTimeSelected!(throwingSelection);

      expect(toast.error).toHaveBeenCalledWith(
        'Unexpected error while rescheduling.'
      );
    });
  });

  describe('API error handling in inner catch', () => {
    it('shows payment method required toast for payment_method_required error', async () => {
      rescheduleBookingImperativeMock.mockRejectedValue(
        new Error('payment_method_required')
      );

      render(<RescheduleModal {...defaultProps} />);

      capturedOnTimeSelected!(defaultSelection);

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          expect.stringContaining('payment method is required')
        );
      });

      expect(defaultProps.onClose).toHaveBeenCalled();
      expect(mockPush).toHaveBeenCalledWith('/student/settings?tab=payment');
    });

    it('shows payment failed toast for payment_confirmation_failed error', async () => {
      rescheduleBookingImperativeMock.mockRejectedValue(
        new Error('payment_confirmation_failed')
      );

      render(<RescheduleModal {...defaultProps} />);

      capturedOnTimeSelected!(defaultSelection);

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          expect.stringContaining("couldn't process your payment")
        );
      });

      // Modal should stay open for retry (onClose NOT called)
      expect(defaultProps.onClose).not.toHaveBeenCalled();
    });

    it('shows student conflict toast for 409 + student conflict', async () => {
      rescheduleBookingImperativeMock.mockRejectedValue(
        new Error('409 conflict: student already have a booking at that time')
      );

      render(<RescheduleModal {...defaultProps} />);

      capturedOnTimeSelected!(defaultSelection);

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          'You have another booking at that time. Please pick another time.'
        );
      });
    });

    it('shows instructor conflict toast for 409 without student keyword', async () => {
      rescheduleBookingImperativeMock.mockRejectedValue(
        new Error('409 conflict: instructor not available')
      );

      render(<RescheduleModal {...defaultProps} />);

      capturedOnTimeSelected!(defaultSelection);

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          'That time is no longer available. Please pick another time.'
        );
      });
    });

    it('shows generic error message for non-Error rejections', async () => {
      // Reject with a non-Error value (string) — tests the `err instanceof Error` check
      rescheduleBookingImperativeMock.mockRejectedValue('something broke');

      render(<RescheduleModal {...defaultProps} />);

      capturedOnTimeSelected!(defaultSelection);

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          'Unable to reschedule. Please try again.'
        );
      });
    });
  });

  describe('success path', () => {
    it('shows success toast and navigates on successful reschedule', async () => {
      render(<RescheduleModal {...defaultProps} />);

      capturedOnTimeSelected!(defaultSelection);

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Rescheduled successfully');
      });

      expect(defaultProps.onClose).toHaveBeenCalled();
      expect(mockPush).toHaveBeenCalledWith('/student/lessons/new-booking-1');
    });

    it('navigates to /student/lessons when result has no id', async () => {
      rescheduleBookingImperativeMock.mockResolvedValue({});

      render(<RescheduleModal {...defaultProps} />);

      capturedOnTimeSelected!(defaultSelection);

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/student/lessons');
      });
    });
  });

  describe('time parsing edge cases', () => {
    it('correctly converts 12:00pm to 12:00 (not 24:00)', async () => {
      render(<RescheduleModal {...defaultProps} />);

      capturedOnTimeSelected!({ date: '2026-03-25', time: '12:00pm', duration: 60 });

      await waitFor(() => {
        expect(rescheduleBookingImperativeMock).toHaveBeenCalledWith(
          'booking-1',
          expect.objectContaining({ start_time: '12:00' })
        );
      });
    });

    it('correctly converts 12:00am to 00:00 (midnight)', async () => {
      render(<RescheduleModal {...defaultProps} />);

      capturedOnTimeSelected!({ date: '2026-03-25', time: '12:00am', duration: 60 });

      await waitFor(() => {
        expect(rescheduleBookingImperativeMock).toHaveBeenCalledWith(
          'booking-1',
          expect.objectContaining({ start_time: '00:00' })
        );
      });
    });
  });

  describe('chat modal integration', () => {
    it('opens chat modal and closes both modals when chat is dismissed', async () => {
      const user = userEvent.setup();

      render(<RescheduleModal {...defaultProps} />);

      expect(screen.getByTestId('time-selection-modal')).toBeInTheDocument();
      expect(screen.queryByTestId('chat-modal')).not.toBeInTheDocument();

      // Open chat
      expect(capturedOnOpenChat).not.toBeNull();
      capturedOnOpenChat!();

      // Chat modal should appear, time selection should hide
      expect(await screen.findByTestId('chat-modal')).toBeInTheDocument();
      expect(screen.queryByTestId('time-selection-modal')).not.toBeInTheDocument();

      // Close chat — should also close the reschedule modal
      await user.click(screen.getByTestId('close-chat'));

      expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
    });
  });
});
