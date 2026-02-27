import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
    expect(screen.getByRole('timer')).toHaveTextContent('05:00');
    expect(screen.queryByRole('button', { name: 'Join video lesson' })).not.toBeInTheDocument();
  });

  it('shows Join button when window is open', () => {
    mockCountdowns(
      { secondsLeft: 0, isExpired: true, formatted: '00:00' },
      { secondsLeft: 600, isExpired: false, formatted: '10:00' }
    );

    render(<PreLessonWaiting {...defaultProps} />);

    expect(screen.getByRole('button', { name: 'Join video lesson' })).toBeInTheDocument();
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
    expect(screen.queryByRole('button', { name: 'Join video lesson' })).not.toBeInTheDocument();
  });

  it('calls onJoin when Join button is clicked', () => {
    const onJoin = jest.fn();
    mockCountdowns(
      { secondsLeft: 0, isExpired: true, formatted: '00:00' },
      { secondsLeft: 600, isExpired: false, formatted: '10:00' }
    );

    render(<PreLessonWaiting {...defaultProps} onJoin={onJoin} />);

    fireEvent.click(screen.getByRole('button', { name: 'Join video lesson' }));
    expect(onJoin).toHaveBeenCalledTimes(1);
  });

  it('supports keyboard activation for the Join button', async () => {
    const user = userEvent.setup();
    const onJoin = jest.fn();
    mockCountdowns(
      { secondsLeft: 0, isExpired: true, formatted: '00:00' },
      { secondsLeft: 600, isExpired: false, formatted: '10:00' }
    );

    render(<PreLessonWaiting {...defaultProps} onJoin={onJoin} />);

    const joinButton = screen.getByRole('button', { name: 'Join video lesson' });
    joinButton.focus();
    await user.keyboard('{Enter}');

    expect(onJoin).toHaveBeenCalledTimes(1);
  });

  it('keeps Join button mounted and busy when isJoining is true', () => {
    mockCountdowns(
      { secondsLeft: 0, isExpired: true, formatted: '00:00' },
      { secondsLeft: 600, isExpired: false, formatted: '10:00' }
    );

    render(<PreLessonWaiting {...defaultProps} isJoining={true} />);

    const joinButton = screen.getByRole('button', { name: 'Join video lesson' });
    expect(joinButton).toBeInTheDocument();
    expect(joinButton).toBeDisabled();
    expect(joinButton).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByText('Connecting...')).toBeInTheDocument();
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

  describe('CountdownPill urgency colors', () => {
    it('shows red pill when join window closes within 60 seconds', () => {
      mockCountdowns(
        { secondsLeft: 0, isExpired: true, formatted: '00:00' },
        { secondsLeft: 45, isExpired: false, formatted: '00:45' }
      );

      render(<PreLessonWaiting {...defaultProps} />);

      const pill = screen.getByText(/Window closes in 00:45/);
      expect(pill.className).toContain('bg-red-100');
      expect(pill.className).toContain('text-red-700');
      // Should NOT have gray or amber styles
      expect(pill.className).not.toContain('bg-gray-100');
      expect(pill.className).not.toContain('bg-amber-100');
    });

    it('shows red pill at the exact 60-second boundary', () => {
      mockCountdowns(
        { secondsLeft: 0, isExpired: true, formatted: '00:00' },
        { secondsLeft: 60, isExpired: false, formatted: '01:00' }
      );

      render(<PreLessonWaiting {...defaultProps} />);

      const pill = screen.getByText(/Window closes in 01:00/);
      expect(pill.className).toContain('bg-red-100');
    });

    it('shows amber pill when join window closes within 5 minutes (but > 60s)', () => {
      mockCountdowns(
        { secondsLeft: 0, isExpired: true, formatted: '00:00' },
        { secondsLeft: 180, isExpired: false, formatted: '03:00' }
      );

      render(<PreLessonWaiting {...defaultProps} />);

      const pill = screen.getByText(/Window closes in 03:00/);
      expect(pill.className).toContain('bg-amber-100');
      expect(pill.className).toContain('text-amber-700');
      // Should NOT have gray or red styles
      expect(pill.className).not.toContain('bg-gray-100');
      expect(pill.className).not.toContain('bg-red-100');
    });

    it('shows amber pill at the exact 300-second boundary', () => {
      mockCountdowns(
        { secondsLeft: 0, isExpired: true, formatted: '00:00' },
        { secondsLeft: 300, isExpired: false, formatted: '05:00' }
      );

      render(<PreLessonWaiting {...defaultProps} />);

      const pill = screen.getByText(/Window closes in 05:00/);
      expect(pill.className).toContain('bg-amber-100');
    });

    it('shows gray pill when more than 5 minutes remain', () => {
      mockCountdowns(
        { secondsLeft: 0, isExpired: true, formatted: '00:00' },
        { secondsLeft: 600, isExpired: false, formatted: '10:00' }
      );

      render(<PreLessonWaiting {...defaultProps} />);

      const pill = screen.getByText(/Window closes in 10:00/);
      expect(pill.className).toContain('bg-gray-100');
      expect(pill.className).toContain('text-gray-700');
    });
  });
});
