import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import type { Booking } from '@/features/shared/api/types';

jest.mock('@/hooks/useCountdown', () => ({
  useCountdown: jest.fn(),
}));

import { useCountdown } from '@/hooks/useCountdown';
import { PreLessonWaiting } from '../PreLessonWaiting';

const mockUseCountdown = useCountdown as jest.Mock;

const baseBooking = {
  service_name: 'Guitar Lesson',
  join_opens_at: '2025-01-01T10:00:00Z',
  join_closes_at: '2025-01-01T10:30:00Z',
} as unknown as Booking;

const defaultProps = {
  booking: baseBooking,
  userName: 'Alice',
  otherPartyName: 'Bob',
  otherPartyRole: 'instructor' as const,
  onJoin: jest.fn(),
  isJoining: false,
  joinError: null,
};

/** Helper to configure the two useCountdown calls (opens, then closes). */
function mockCountdowns(
  opens: { secondsLeft: number; isExpired: boolean; formatted: string },
  closes: { secondsLeft: number; isExpired: boolean; formatted: string }
) {
  mockUseCountdown
    .mockReturnValueOnce(opens)
    .mockReturnValueOnce(closes);
}

describe('PreLessonWaiting', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows countdown when window has not opened yet', () => {
    mockCountdowns(
      { secondsLeft: 300, isExpired: false, formatted: '05:00' },
      { secondsLeft: 1800, isExpired: false, formatted: '30:00' }
    );

    render(<PreLessonWaiting {...defaultProps} />);

    expect(screen.getByText('Join opens in')).toBeInTheDocument();
    expect(screen.getByText('05:00')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Join Lesson' })).not.toBeInTheDocument();
  });

  it('shows Join button when window is open', () => {
    mockCountdowns(
      { secondsLeft: 0, isExpired: true, formatted: '00:00' },
      { secondsLeft: 600, isExpired: false, formatted: '10:00' }
    );

    render(<PreLessonWaiting {...defaultProps} />);

    expect(screen.getByRole('button', { name: 'Join Lesson' })).toBeInTheDocument();
    expect(screen.getByText(/Window closes in 10:00/)).toBeInTheDocument();
    expect(screen.queryByText('Join opens in')).not.toBeInTheDocument();
  });

  it('shows closed message when window has closed', () => {
    mockCountdowns(
      { secondsLeft: 0, isExpired: true, formatted: '00:00' },
      { secondsLeft: 0, isExpired: true, formatted: '00:00' }
    );

    render(<PreLessonWaiting {...defaultProps} />);

    expect(screen.getByText('Join window has closed.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Join Lesson' })).not.toBeInTheDocument();
  });

  it('calls onJoin when Join button is clicked', () => {
    const onJoin = jest.fn();
    mockCountdowns(
      { secondsLeft: 0, isExpired: true, formatted: '00:00' },
      { secondsLeft: 600, isExpired: false, formatted: '10:00' }
    );

    render(<PreLessonWaiting {...defaultProps} onJoin={onJoin} />);

    fireEvent.click(screen.getByRole('button', { name: 'Join Lesson' }));
    expect(onJoin).toHaveBeenCalledTimes(1);
  });

  it('shows spinner and hides Join button when isJoining is true', () => {
    mockCountdowns(
      { secondsLeft: 0, isExpired: true, formatted: '00:00' },
      { secondsLeft: 600, isExpired: false, formatted: '10:00' }
    );

    render(<PreLessonWaiting {...defaultProps} isJoining={true} />);

    expect(screen.getByText('Connecting...')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Join Lesson' })).not.toBeInTheDocument();
  });

  it('shows join error with alert role', () => {
    mockCountdowns(
      { secondsLeft: 0, isExpired: true, formatted: '00:00' },
      { secondsLeft: 600, isExpired: false, formatted: '10:00' }
    );

    render(
      <PreLessonWaiting {...defaultProps} joinError="Unable to connect" />
    );

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Unable to connect');
  });

  it('renders the booking service name as a heading', () => {
    mockCountdowns(
      { secondsLeft: 300, isExpired: false, formatted: '05:00' },
      { secondsLeft: 1800, isExpired: false, formatted: '30:00' }
    );

    render(<PreLessonWaiting {...defaultProps} />);

    expect(
      screen.getByRole('heading', { name: 'Guitar Lesson' })
    ).toBeInTheDocument();
  });

  it('shows instructor label when otherPartyRole is instructor', () => {
    mockCountdowns(
      { secondsLeft: 300, isExpired: false, formatted: '05:00' },
      { secondsLeft: 1800, isExpired: false, formatted: '30:00' }
    );

    render(
      <PreLessonWaiting
        {...defaultProps}
        otherPartyRole="instructor"
        otherPartyName="Bob"
      />
    );

    expect(screen.getByText('Your instructor: Bob')).toBeInTheDocument();
  });

  it('shows student label when otherPartyRole is student', () => {
    mockCountdowns(
      { secondsLeft: 300, isExpired: false, formatted: '05:00' },
      { secondsLeft: 1800, isExpired: false, formatted: '30:00' }
    );

    render(
      <PreLessonWaiting
        {...defaultProps}
        otherPartyRole="student"
        otherPartyName="Charlie"
      />
    );

    expect(screen.getByText('Your student: Charlie')).toBeInTheDocument();
  });

  it('shows the current user name', () => {
    mockCountdowns(
      { secondsLeft: 300, isExpired: false, formatted: '05:00' },
      { secondsLeft: 1800, isExpired: false, formatted: '30:00' }
    );

    render(<PreLessonWaiting {...defaultProps} userName="Alice" />);

    expect(screen.getByText('Joining as Alice')).toBeInTheDocument();
  });
});
