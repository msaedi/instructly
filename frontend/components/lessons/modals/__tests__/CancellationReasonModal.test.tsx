import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CancellationReasonModal } from '../CancellationReasonModal';
import type { Booking } from '@/features/shared/api/types';
import { useCancelLesson } from '@/hooks/useMyLessons';
import { useRouter } from 'next/navigation';
import { logger } from '@/lib/logger';

jest.mock('@/components/Modal', () => ({
  __esModule: true,
  default: ({ isOpen, children }: { isOpen: boolean; children?: React.ReactNode }) =>
    isOpen ? <div>{children}</div> : null,
}));

jest.mock('@/hooks/useMyLessons', () => ({
  useCancelLesson: jest.fn(),
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
const useRouterMock = useRouter as jest.Mock;

const baseLesson = {
  id: 'lesson-1',
  booking_date: '2025-01-10',
  start_time: '10:00:00',
  service_name: 'Guitar',
  instructor: { first_name: 'Jo', last_initial: 'Q' },
} as Booking;

describe('CancellationReasonModal', () => {
  const onClose = jest.fn();
  const onReschedule = jest.fn();
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
  });

  it('renders reasons and disables confirm until selected', () => {
    render(
      <CancellationReasonModal
        isOpen
        onClose={onClose}
        lesson={baseLesson}
        onReschedule={onReschedule}
      />
    );

    expect(screen.getByText(/please tell us why/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /confirm cancellation/i })).toBeDisabled();
    expect(screen.getByLabelText(/lesson was booked by mistake/i)).toBeInTheDocument();
  });

  it('submits cancellation with selected reason', async () => {
    const user = userEvent.setup();
    render(
      <CancellationReasonModal
        isOpen
        onClose={onClose}
        lesson={baseLesson}
        onReschedule={onReschedule}
      />
    );

    await user.click(screen.getByLabelText(/lesson was booked by mistake/i));
    await user.click(screen.getByRole('button', { name: /confirm cancellation/i }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        lessonId: baseLesson.id,
        reason: 'Lesson was booked by mistake',
      });
    });
  });

  it('shows reschedule option when more than 12 hours before the lesson', async () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-08T08:00:00Z'));
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

    render(
      <CancellationReasonModal
        isOpen
        onClose={onClose}
        lesson={baseLesson}
        onReschedule={onReschedule}
      />
    );

    await user.click(screen.getByRole('button', { name: /reschedule instead/i }));
    expect(onReschedule).toHaveBeenCalled();
    jest.useRealTimers();
  });

  it('shows pending state while cancelling', () => {
    useCancelLessonMock.mockReturnValue({
      mutateAsync,
      isSuccess: false,
      isPending: true,
    });

    render(
      <CancellationReasonModal
        isOpen
        onClose={onClose}
        lesson={baseLesson}
        onReschedule={onReschedule}
      />
    );

    expect(screen.getByRole('button', { name: /cancelling/i })).toBeDisabled();
  });

  it('renders success state and routes on done', async () => {
    useCancelLessonMock.mockReturnValue({
      mutateAsync,
      isSuccess: true,
      isPending: false,
    });

    const user = userEvent.setup();
    render(
      <CancellationReasonModal
        isOpen
        onClose={onClose}
        lesson={baseLesson}
        onReschedule={onReschedule}
      />
    );

    expect(screen.getByText(/your lesson has been cancelled/i)).toBeInTheDocument();
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
    const user = userEvent.setup();
    render(
      <CancellationReasonModal
        isOpen
        onClose={onClose}
        lesson={baseLesson}
        onReschedule={onReschedule}
      />
    );

    await user.click(screen.getByRole('button', { name: /contact support/i }));
    expect(logger.info).toHaveBeenCalledWith('Contact support clicked');
  });
});
