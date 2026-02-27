import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CancellationConfirmationModal } from '../CancellationConfirmationModal';
import type { Booking } from '@/features/shared/api/types';
import { useCancelLesson, calculateCancellationFee } from '@/hooks/useMyLessons';
import { useRouter } from 'next/navigation';
import { logger } from '@/lib/logger';

jest.mock('@/components/Modal', () => ({
  __esModule: true,
  default: ({ isOpen, title, footer, children }: { isOpen: boolean; title?: string; footer?: React.ReactNode; children?: React.ReactNode }) =>
    isOpen ? (
      <div>
        {title && <div>{title}</div>}
        <div>{children}</div>
        <div>{footer}</div>
      </div>
    ) : null,
}));

jest.mock('@/hooks/useMyLessons', () => ({
  useCancelLesson: jest.fn(),
  calculateCancellationFee: jest.fn(),
}));

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
  },
}));

const useCancelLessonMock = useCancelLesson as jest.Mock;
const calculateCancellationFeeMock = calculateCancellationFee as jest.Mock;
const useRouterMock = useRouter as jest.Mock;

const baseLesson = {
  id: 'lesson-1',
  booking_date: '2025-01-10',
  start_time: '10:00:00',
  service_name: 'Piano',
  instructor: { first_name: 'Jane', last_initial: 'D' },
} as Booking;

describe('CancellationConfirmationModal', () => {
  const onClose = jest.fn();
  const reason = 'My schedule changed';
  const mutateAsync = jest.fn();
  const push = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    useRouterMock.mockReturnValue({ push });
    useCancelLessonMock.mockReturnValue({
      mutateAsync,
      isSuccess: false,
      isPending: false,
    });
    calculateCancellationFeeMock.mockReturnValue({
      window: 'credit',
      lessonPrice: 50,
      platformFee: 5,
      willReceiveCredit: true,
    });
  });

  it('renders the confirmation summary and reason', () => {
    render(
      <CancellationConfirmationModal
        isOpen
        onClose={onClose}
        lesson={baseLesson}
        reason={reason}
      />
    );

    expect(screen.getByRole('button', { name: /confirm cancellation/i })).toBeInTheDocument();
    expect(screen.getByText(/Reason for cancellation/i)).toBeInTheDocument();
    expect(screen.getByText(reason)).toBeInTheDocument();
    expect(
      screen.getByText((content) =>
        content.includes('Your lesson price') &&
        content.includes('50.00') &&
        content.includes('added as credit')
      )
    ).toBeInTheDocument();
  });

  it('calls onClose when Keep Lesson is clicked', async () => {
    const user = userEvent.setup();
    render(
      <CancellationConfirmationModal
        isOpen
        onClose={onClose}
        lesson={baseLesson}
        reason={reason}
      />
    );

    await user.click(screen.getByRole('button', { name: /keep lesson/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it('submits cancellation when confirmed', async () => {
    const user = userEvent.setup();
    render(
      <CancellationConfirmationModal
        isOpen
        onClose={onClose}
        lesson={baseLesson}
        reason={reason}
      />
    );

    await user.click(screen.getByRole('button', { name: /confirm cancellation/i }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({ lessonId: baseLesson.id, reason });
    });
  });

  it('shows pending state and disables actions', () => {
    useCancelLessonMock.mockReturnValue({
      mutateAsync,
      isSuccess: false,
      isPending: true,
    });

    render(
      <CancellationConfirmationModal
        isOpen
        onClose={onClose}
        lesson={baseLesson}
        reason={reason}
      />
    );

    expect(screen.getByRole('button', { name: /cancelling/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /keep lesson/i })).toBeDisabled();
  });

  it('renders success state and routes to lessons on done', async () => {
    useCancelLessonMock.mockReturnValue({
      mutateAsync,
      isSuccess: true,
      isPending: false,
    });
    calculateCancellationFeeMock.mockReturnValue({
      window: 'free',
      lessonPrice: 50,
      platformFee: 5,
      willReceiveCredit: false,
    });

    const user = userEvent.setup();
    render(
      <CancellationConfirmationModal
        isOpen
        onClose={onClose}
        lesson={baseLesson}
        reason={reason}
      />
    );

    expect(screen.getByText(/Cancellation confirmed/i)).toBeInTheDocument();
    expect(screen.getByText(/No charges were made/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /done/i }));
    expect(onClose).toHaveBeenCalled();
    expect(push).toHaveBeenCalledWith('/student/lessons');
  });

  it('logs when contact support is clicked in success state', async () => {
    useCancelLessonMock.mockReturnValue({
      mutateAsync,
      isSuccess: true,
      isPending: false,
    });
    calculateCancellationFeeMock.mockReturnValue({
      window: 'credit',
      lessonPrice: 50,
      platformFee: 5,
      willReceiveCredit: true,
    });

    const user = userEvent.setup();
    render(
      <CancellationConfirmationModal
        isOpen
        onClose={onClose}
        lesson={baseLesson}
        reason={reason}
      />
    );

    await user.click(screen.getByRole('button', { name: /contact support/i }));
    expect(logger.info).toHaveBeenCalledWith('Contact support clicked');
  });

  it('renders full charge messaging when within full charge window', () => {
    calculateCancellationFeeMock.mockReturnValue({
      window: 'full',
      lessonPrice: 50,
      platformFee: 5,
      willReceiveCredit: false,
    });

    render(
      <CancellationConfirmationModal
        isOpen
        onClose={onClose}
        lesson={baseLesson}
        reason={reason}
      />
    );

    expect(
      screen.getByText((content) =>
        content.includes('The full amount') && content.includes('55.00')
      )
    ).toBeInTheDocument();
    expect(screen.getByText(/no credit or refund/i)).toBeInTheDocument();
  });

  it('logs an error when cancellation fails', async () => {
    const error = new Error('Cancellation failed');
    useCancelLessonMock.mockReturnValue({
      mutateAsync: jest.fn().mockRejectedValue(error),
      isSuccess: false,
      isPending: false,
    });

    const user = userEvent.setup();
    render(
      <CancellationConfirmationModal
        isOpen
        onClose={onClose}
        lesson={baseLesson}
        reason={reason}
      />
    );

    await user.click(screen.getByRole('button', { name: /confirm cancellation/i }));
    expect(logger.error).toHaveBeenCalledWith('Failed to cancel lesson', error);
  });

  it('renders "Instructor" fallback when lesson.instructor is null', () => {
    const lessonNoInstructor = {
      ...baseLesson,
      instructor: null,
    } as unknown as Booking;

    render(
      <CancellationConfirmationModal
        isOpen
        onClose={onClose}
        lesson={lessonNoInstructor}
        reason={reason}
      />
    );

    // Should show "Instructor" fallback instead of instructor name
    expect(screen.getByText(/Instructor$/)).toBeInTheDocument();
  });

  it('renders success state with credit info when willReceiveCredit is true', () => {
    useCancelLessonMock.mockReturnValue({
      mutateAsync,
      isSuccess: true,
      isPending: false,
    });
    calculateCancellationFeeMock.mockReturnValue({
      window: 'credit',
      lessonPrice: 75,
      platformFee: 8,
      willReceiveCredit: true,
    });

    render(
      <CancellationConfirmationModal
        isOpen
        onClose={onClose}
        lesson={baseLesson}
        reason={reason}
      />
    );

    // Should show credit issued amount
    expect(screen.getByText(/Credit issued/)).toBeInTheDocument();
    expect(screen.getByText(/\$75\.00/)).toBeInTheDocument();
    // Should show non-refundable fee
    expect(screen.getByText(/\$8\.00.*non-refundable/)).toBeInTheDocument();
    // Should show auto-apply message
    expect(screen.getByText(/credit will be applied.*next booking/i)).toBeInTheDocument();
  });

  it('renders success state with "full amount charged" when willReceiveCredit is false and window is "full"', () => {
    useCancelLessonMock.mockReturnValue({
      mutateAsync,
      isSuccess: true,
      isPending: false,
    });
    calculateCancellationFeeMock.mockReturnValue({
      window: 'full',
      lessonPrice: 60,
      platformFee: 6,
      willReceiveCredit: false,
    });

    render(
      <CancellationConfirmationModal
        isOpen
        onClose={onClose}
        lesson={baseLesson}
        reason={reason}
      />
    );

    // Should show "The full amount has been charged"
    expect(screen.getByText('The full amount has been charged.')).toBeInTheDocument();
    // Should NOT show credit info
    expect(screen.queryByText(/credit issued/i)).not.toBeInTheDocument();
  });

  it('renders success state with "Instructor" fallback when instructor is null', () => {
    useCancelLessonMock.mockReturnValue({
      mutateAsync,
      isSuccess: true,
      isPending: false,
    });
    calculateCancellationFeeMock.mockReturnValue({
      window: 'free',
      lessonPrice: 40,
      platformFee: 4,
      willReceiveCredit: false,
    });

    const lessonNoInstructor = {
      ...baseLesson,
      instructor: null,
    } as unknown as Booking;

    render(
      <CancellationConfirmationModal
        isOpen
        onClose={onClose}
        lesson={lessonNoInstructor}
        reason={reason}
      />
    );

    // In the success state, it should show "Instructor" fallback
    expect(screen.getByText(/Piano with Instructor$/)).toBeInTheDocument();
  });

  it('does not render fee info section when window is "free" in confirmation dialog', () => {
    calculateCancellationFeeMock.mockReturnValue({
      window: 'free',
      lessonPrice: 50,
      platformFee: 5,
      willReceiveCredit: false,
    });

    render(
      <CancellationConfirmationModal
        isOpen
        onClose={onClose}
        lesson={baseLesson}
        reason={reason}
      />
    );

    // Should not show the credit or full charge fee sections
    expect(screen.queryByText(/added as credit/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/full amount/i)).not.toBeInTheDocument();
  });

  it('does not render when isOpen is false', () => {
    render(
      <CancellationConfirmationModal
        isOpen={false}
        onClose={onClose}
        lesson={baseLesson}
        reason={reason}
      />
    );

    expect(screen.queryByText(/confirm cancellation/i)).not.toBeInTheDocument();
  });
});
