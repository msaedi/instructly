import React from 'react';
import { render, screen } from '@testing-library/react';

jest.mock('next/link', () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => (
    <a {...props}>{props.children as React.ReactNode}</a>
  ),
}));

jest.mock('@/hooks/useCountdown', () => ({
  useCountdown: jest.fn(),
}));

jest.mock('@/components/ui/button.utils', () => ({
  buttonVariants: () => 'mock-button-class',
}));

import { useCountdown } from '@/hooks/useCountdown';
import { JoinLessonButton } from '../JoinLessonButton';

const mockUseCountdown = useCountdown as jest.Mock;

const expired = { secondsLeft: 0, isExpired: true, formatted: '00:00' };
const notExpired = { secondsLeft: 300, isExpired: false, formatted: '05:00' };

/** Helper to configure the two useCountdown calls (opens, then closes). */
function mockCountdowns(
  opens: { secondsLeft: number; isExpired: boolean; formatted: string },
  closes: { secondsLeft: number; isExpired: boolean; formatted: string }
) {
  mockUseCountdown
    .mockReturnValueOnce(opens)
    .mockReturnValueOnce(closes);
}

describe('JoinLessonButton', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('returns null when joinOpensAt is null', () => {
    mockCountdowns(expired, expired);

    const { container } = render(
      <JoinLessonButton
        bookingId="01ABC"
        joinOpensAt={null}
        joinClosesAt={null}
      />
    );

    expect(container.innerHTML).toBe('');
  });

  it('returns null when joinOpensAt is undefined', () => {
    mockCountdowns(expired, expired);

    const { container } = render(
      <JoinLessonButton
        bookingId="01ABC"
        joinOpensAt={undefined}
        joinClosesAt={undefined}
      />
    );

    expect(container.innerHTML).toBe('');
  });

  it('returns null when both countdowns are expired (window closed)', () => {
    mockCountdowns(expired, expired);

    const { container } = render(
      <JoinLessonButton
        bookingId="01ABC"
        joinOpensAt="2025-01-01T10:00:00Z"
        joinClosesAt="2025-01-01T10:30:00Z"
      />
    );

    expect(container.innerHTML).toBe('');
  });

  it('returns null when window has not opened yet', () => {
    mockCountdowns(notExpired, notExpired);

    const { container } = render(
      <JoinLessonButton
        bookingId="01ABC"
        joinOpensAt="2025-01-01T10:00:00Z"
        joinClosesAt="2025-01-01T10:30:00Z"
      />
    );

    expect(container.innerHTML).toBe('');
  });

  it('renders "Join Lesson" link when window is open', () => {
    mockCountdowns(expired, notExpired);

    render(
      <JoinLessonButton
        bookingId="01ABC"
        joinOpensAt="2025-01-01T10:00:00Z"
        joinClosesAt="2025-01-01T10:30:00Z"
      />
    );

    expect(screen.getByText('Join Lesson')).toBeInTheDocument();
  });

  it('link href points to /lessons/${bookingId}', () => {
    mockCountdowns(expired, notExpired);

    render(
      <JoinLessonButton
        bookingId="01BOOKING123"
        joinOpensAt="2025-01-01T10:00:00Z"
        joinClosesAt="2025-01-01T10:30:00Z"
      />
    );

    const link = screen.getByText('Join Lesson').closest('a');
    expect(link).toHaveAttribute('href', '/lessons/01BOOKING123');
  });

  it('has data-testid="join-lesson-button"', () => {
    mockCountdowns(expired, notExpired);

    render(
      <JoinLessonButton
        bookingId="01ABC"
        joinOpensAt="2025-01-01T10:00:00Z"
        joinClosesAt="2025-01-01T10:30:00Z"
      />
    );

    expect(screen.getByTestId('join-lesson-button')).toBeInTheDocument();
  });
});
