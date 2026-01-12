import { render, screen, fireEvent } from '@testing-library/react';
import { NotificationBell } from '@/components/notifications/NotificationBell';

const mockMarkAsRead = jest.fn();
const mockMarkAllAsRead = jest.fn();

jest.mock('@/features/shared/hooks/useNotifications', () => ({
  useNotifications: () => ({
    notifications: [
      {
        id: 'notif-1',
        title: 'New booking',
        body: 'Sarah booked a lesson',
        category: 'lesson_updates',
        type: 'booking_confirmed',
        data: { url: '/instructor/dashboard' },
        read_at: null,
        created_at: '2024-01-01T00:00:00Z',
      },
    ],
    unreadCount: 2,
    total: 1,
    isLoading: false,
    error: null,
    markAsRead: { mutate: mockMarkAsRead },
    markAllAsRead: { mutate: mockMarkAllAsRead, isPending: false },
    deleteNotification: { mutate: jest.fn() },
    clearAll: { mutate: jest.fn(), isPending: false },
    refetch: jest.fn(),
  }),
}));

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
  }),
}));

describe('NotificationBell', () => {
  it('shows unread badge', () => {
    render(<NotificationBell />);

    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('opens and renders notifications', () => {
    render(<NotificationBell />);

    const button = screen.getByRole('button', { name: /notifications/i });
    fireEvent.click(button);

    expect(screen.getByText('Notifications')).toBeInTheDocument();
    expect(screen.getByText('New booking')).toBeInTheDocument();
  });
});
