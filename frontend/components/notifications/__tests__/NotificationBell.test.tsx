/**
 * @jest-environment jsdom
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { NotificationItem } from '@/features/shared/api/notifications';

// Mock useNotifications hook
const mockMarkAsRead = { mutate: jest.fn(), isPending: false };
const mockMarkAllAsRead = { mutate: jest.fn(), isPending: false };
const mockDeleteNotification = { mutate: jest.fn(), isPending: false };
const mockClearAll = { mutate: jest.fn(), isPending: false };

const mockUseNotifications = jest.fn(() => ({
  notifications: [] as NotificationItem[],
  unreadCount: 0,
  isLoading: false,
  error: null as Error | null,
  markAsRead: mockMarkAsRead,
  markAllAsRead: mockMarkAllAsRead,
  deleteNotification: mockDeleteNotification,
  clearAll: mockClearAll,
}));

jest.mock('@/features/shared/hooks/useNotifications', () => ({
  useNotifications: () => mockUseNotifications(),
}));

// Mock cn utility
jest.mock('@/lib/utils', () => ({
  cn: (...classes: (string | boolean | undefined)[]) => classes.filter(Boolean).join(' '),
}));

// Mock NotificationItem component
jest.mock('../NotificationItem', () => ({
  NotificationItem: ({ notification, onRead, onDelete }: {
    notification: NotificationItem;
    onRead: () => void;
    onDelete: () => void;
  }) => (
    <div data-testid={`notification-${notification.id}`} data-notification-item="true" tabIndex={0}>
      <span>{notification.title}</span>
      <button onClick={onRead}>Mark Read</button>
      <button onClick={onDelete}>Delete</button>
    </div>
  ),
}));

import { NotificationBell } from '../NotificationBell';

const createNotification = (overrides: Partial<NotificationItem> = {}): NotificationItem => ({
  id: '01K2GY3VEVJWKZDVH5HMNXEVRD',
  title: 'Test Notification',
  body: 'This is a test',
  category: 'info',
  type: 'info',
  created_at: '2024-01-15T10:00:00Z',
  read_at: null,
  data: null,
  ...overrides,
});

describe('NotificationBell', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseNotifications.mockReturnValue({
      notifications: [],
      unreadCount: 0,
      isLoading: false,
      error: null,
      markAsRead: mockMarkAsRead,
      markAllAsRead: mockMarkAllAsRead,
      deleteNotification: mockDeleteNotification,
      clearAll: mockClearAll,
    });
  });

  describe('rendering', () => {
    it('renders the bell button', () => {
      render(<NotificationBell />);

      const button = screen.getByRole('button', { name: 'Notifications' });
      expect(button).toBeInTheDocument();
    });

    it('shows badge when there are unread notifications', () => {
      mockUseNotifications.mockReturnValue({
        notifications: [],
        unreadCount: 5,
        isLoading: false,
        error: null,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
        clearAll: mockClearAll,
      });

      render(<NotificationBell />);

      expect(screen.getByText('5')).toBeInTheDocument();
    });

    it('shows 9+ when unread count exceeds 9', () => {
      mockUseNotifications.mockReturnValue({
        notifications: [],
        unreadCount: 15,
        isLoading: false,
        error: null,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
        clearAll: mockClearAll,
      });

      render(<NotificationBell />);

      expect(screen.getByText('9+')).toBeInTheDocument();
    });

    it('does not show badge when unread count is 0', () => {
      render(<NotificationBell />);

      expect(screen.queryByText('0')).not.toBeInTheDocument();
    });
  });

  describe('dropdown behavior', () => {
    it('opens dropdown when bell is clicked', async () => {
      const user = userEvent.setup();
      render(<NotificationBell />);

      await user.click(screen.getByRole('button', { name: 'Notifications' }));

      expect(screen.getByRole('menu')).toBeInTheDocument();
      expect(screen.getByText('Notifications', { selector: 'h3' })).toBeInTheDocument();
    });

    it('closes dropdown when clicked again', async () => {
      const user = userEvent.setup();
      render(<NotificationBell />);

      const button = screen.getByRole('button', { name: 'Notifications' });
      await user.click(button);
      expect(screen.getByRole('menu')).toBeInTheDocument();

      await user.click(button);
      expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    });

    it('closes dropdown when clicking outside', async () => {
      const user = userEvent.setup();
      render(
        <div>
          <div data-testid="outside">Outside</div>
          <NotificationBell />
        </div>
      );

      await user.click(screen.getByRole('button', { name: 'Notifications' }));
      expect(screen.getByRole('menu')).toBeInTheDocument();

      // Click outside - use mouseDown as that's what the component listens for
      fireEvent.mouseDown(screen.getByTestId('outside'));

      expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    });
  });

  describe('controlled mode', () => {
    it('uses controlled isOpen and onOpenChange props', async () => {
      const user = userEvent.setup();
      const onOpenChange = jest.fn();

      render(<NotificationBell isOpen={false} onOpenChange={onOpenChange} />);

      await user.click(screen.getByRole('button', { name: 'Notifications' }));

      expect(onOpenChange).toHaveBeenCalledWith(true);
    });

    it('respects controlled isOpen=true', () => {
      const onOpenChange = jest.fn();

      render(<NotificationBell isOpen={true} onOpenChange={onOpenChange} />);

      expect(screen.getByRole('menu')).toBeInTheDocument();
    });
  });

  describe('loading state', () => {
    it('shows loading message when loading', async () => {
      const user = userEvent.setup();
      mockUseNotifications.mockReturnValue({
        notifications: [],
        unreadCount: 0,
        isLoading: true,
        error: null,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
        clearAll: mockClearAll,
      });

      render(<NotificationBell />);
      await user.click(screen.getByRole('button', { name: 'Notifications' }));

      expect(screen.getByText('Loading notifications...')).toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('shows error message when there is an error', async () => {
      const user = userEvent.setup();
      mockUseNotifications.mockReturnValue({
        notifications: [],
        unreadCount: 0,
        isLoading: false,
        error: new Error('Failed to load'),
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
        clearAll: mockClearAll,
      });

      render(<NotificationBell />);
      await user.click(screen.getByRole('button', { name: 'Notifications' }));

      expect(screen.getByText('Failed to load')).toBeInTheDocument();
    });
  });

  describe('empty state', () => {
    it('shows empty message when no notifications', async () => {
      const user = userEvent.setup();
      render(<NotificationBell />);
      await user.click(screen.getByRole('button', { name: 'Notifications' }));

      expect(screen.getByText('No notifications yet.')).toBeInTheDocument();
    });
  });

  describe('notification list', () => {
    it('renders notifications', async () => {
      const user = userEvent.setup();
      const notifications = [
        createNotification({ id: 'n1', title: 'First notification' }),
        createNotification({ id: 'n2', title: 'Second notification' }),
      ];

      mockUseNotifications.mockReturnValue({
        notifications,
        unreadCount: 2,
        isLoading: false,
        error: null,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
        clearAll: mockClearAll,
      });

      render(<NotificationBell />);
      await user.click(screen.getByRole('button', { name: /Notifications \(2 unread\)/ }));

      expect(screen.getByText('First notification')).toBeInTheDocument();
      expect(screen.getByText('Second notification')).toBeInTheDocument();
    });
  });

  describe('mark all as read', () => {
    it('shows mark all read button when there are unread notifications', async () => {
      const user = userEvent.setup();
      mockUseNotifications.mockReturnValue({
        notifications: [createNotification()],
        unreadCount: 1,
        isLoading: false,
        error: null,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
        clearAll: mockClearAll,
      });

      render(<NotificationBell />);
      await user.click(screen.getByRole('button', { name: /Notifications/ }));

      const markAllButton = screen.getByText('Mark all read');
      expect(markAllButton).toBeInTheDocument();

      await user.click(markAllButton);
      expect(mockMarkAllAsRead.mutate).toHaveBeenCalled();
    });

    it('does not show mark all read button when no unread notifications', async () => {
      const user = userEvent.setup();
      mockUseNotifications.mockReturnValue({
        notifications: [createNotification({ read_at: '2024-01-15T11:00:00Z' })],
        unreadCount: 0,
        isLoading: false,
        error: null,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
        clearAll: mockClearAll,
      });

      render(<NotificationBell />);
      await user.click(screen.getByRole('button', { name: 'Notifications' }));

      expect(screen.queryByText('Mark all read')).not.toBeInTheDocument();
    });
  });

  describe('clear all', () => {
    it('shows clear all button when there are notifications', async () => {
      const user = userEvent.setup();
      mockUseNotifications.mockReturnValue({
        notifications: [createNotification()],
        unreadCount: 0,
        isLoading: false,
        error: null,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
        clearAll: mockClearAll,
      });

      render(<NotificationBell />);
      await user.click(screen.getByRole('button', { name: 'Notifications' }));

      const clearButton = screen.getByText('Clear all');
      expect(clearButton).toBeInTheDocument();

      await user.click(clearButton);
      expect(mockClearAll.mutate).toHaveBeenCalled();
    });
  });

  describe('keyboard navigation', () => {
    it('closes dropdown on Escape key', async () => {
      const user = userEvent.setup();
      render(<NotificationBell />);

      await user.click(screen.getByRole('button', { name: 'Notifications' }));
      const menu = screen.getByRole('menu');
      expect(menu).toBeInTheDocument();

      // Press Escape on the menu (which has the keydown handler)
      fireEvent.keyDown(menu, { key: 'Escape' });

      expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    });

    it('navigates between items with arrow keys', async () => {
      const user = userEvent.setup();
      const notifications = [
        createNotification({ id: 'n1', title: 'First' }),
        createNotification({ id: 'n2', title: 'Second' }),
      ];

      mockUseNotifications.mockReturnValue({
        notifications,
        unreadCount: 2,
        isLoading: false,
        error: null,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
        clearAll: mockClearAll,
      });

      render(<NotificationBell />);
      await user.click(screen.getByRole('button', { name: /Notifications/ }));

      const menu = screen.getByRole('menu');

      // Focus the menu and press arrow down
      fireEvent.keyDown(menu, { key: 'ArrowDown' });

      // First item should be focused
      expect(document.activeElement).toHaveAttribute('data-notification-item', 'true');
    });
  });

  describe('accessibility', () => {
    it('has proper aria attributes on button', () => {
      render(<NotificationBell />);

      const button = screen.getByRole('button', { name: 'Notifications' });
      expect(button).toHaveAttribute('aria-expanded', 'false');
      expect(button).toHaveAttribute('aria-haspopup', 'menu');
    });

    it('updates aria-expanded when opened', async () => {
      const user = userEvent.setup();
      render(<NotificationBell />);

      const button = screen.getByRole('button', { name: 'Notifications' });
      await user.click(button);

      expect(button).toHaveAttribute('aria-expanded', 'true');
    });

    it('includes unread count in aria-label when present', () => {
      mockUseNotifications.mockReturnValue({
        notifications: [],
        unreadCount: 3,
        isLoading: false,
        error: null,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
        clearAll: mockClearAll,
      });

      render(<NotificationBell />);

      expect(screen.getByRole('button', { name: 'Notifications (3 unread)' })).toBeInTheDocument();
    });

    it('menu has proper aria-live attribute', async () => {
      const user = userEvent.setup();
      render(<NotificationBell />);
      await user.click(screen.getByRole('button', { name: 'Notifications' }));

      const menu = screen.getByRole('menu');
      expect(menu).toHaveAttribute('aria-live', 'polite');
    });
  });

  describe('containerRef prop', () => {
    it('accepts a container ref', async () => {
      const user = userEvent.setup();
      const containerRef = React.createRef<HTMLDivElement>();

      render(
        <div ref={containerRef}>
          <NotificationBell containerRef={containerRef} />
        </div>
      );

      await user.click(screen.getByRole('button', { name: 'Notifications' }));

      expect(screen.getByRole('menu')).toBeInTheDocument();
    });
  });

  describe('className prop', () => {
    it('applies custom className', () => {
      render(<NotificationBell className="custom-class" />);

      const container = screen.getByRole('button', { name: 'Notifications' }).parentElement;
      expect(container).toHaveClass('custom-class');
    });
  });
});
