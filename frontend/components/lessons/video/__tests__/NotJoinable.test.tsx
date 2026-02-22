import { render, screen } from '@testing-library/react';
import { NotJoinable } from '../NotJoinable';
import type { NotJoinableReason } from '../NotJoinable';

describe('NotJoinable', () => {
  const reasons: Array<{ reason: NotJoinableReason; message: string }> = [
    { reason: 'in-person', message: 'This is an in-person lesson. Video is not available.' },
    { reason: 'cancelled', message: 'This lesson was cancelled.' },
    { reason: 'not-available', message: 'Video is not available for this lesson.' },
  ];

  it.each(reasons)(
    'shows correct message for "$reason" reason',
    ({ reason, message }) => {
      render(<NotJoinable reason={reason} userRole="student" />);

      expect(screen.getByText(message)).toBeInTheDocument();
    },
  );

  it('links to /student/lessons for student role', () => {
    render(<NotJoinable reason="cancelled" userRole="student" />);

    const link = screen.getByRole('link', { name: /back to my lessons/i });
    expect(link).toHaveAttribute('href', '/student/lessons');
  });

  it('links to /instructor/bookings for instructor role', () => {
    render(<NotJoinable reason="cancelled" userRole="instructor" />);

    const link = screen.getByRole('link', { name: /back to my lessons/i });
    expect(link).toHaveAttribute('href', '/instructor/bookings');
  });

  it('always shows "Back to My Lessons" link text', () => {
    render(<NotJoinable reason="not-available" userRole="student" />);

    expect(screen.getByRole('link', { name: /back to my lessons/i })).toBeInTheDocument();
  });
});
