/**
 * @jest-environment jsdom
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { NotificationItem as NotificationItemType } from '@/features/shared/api/notifications';

// Mock next/navigation
const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

// Mock cn utility
jest.mock('@/lib/utils', () => ({
  cn: (...classes: (string | boolean | undefined)[]) => classes.filter(Boolean).join(' '),
}));

// Mock formatRelativeTimestamp
jest.mock('@/components/messaging/formatters', () => ({
  formatRelativeTimestamp: jest.fn((_date: string) => '5 minutes ago'),
}));

// Mock NotificationIcon
jest.mock('../NotificationIcon', () => ({
  NotificationIcon: ({ category }: { category: string }) => (
    <div data-testid="notification-icon">{category}</div>
  ),
}));

import { NotificationItem } from '../NotificationItem';

const createNotification = (overrides: Partial<NotificationItemType> = {}): NotificationItemType => ({
  id: '01K2GY3VEVJWKZDVH5HMNXEVRD',
  title: 'New Message',
  body: 'You have a new message from John',
  category: 'message',
  type: 'message',
  created_at: '2024-01-15T10:00:00Z',
  read_at: null,
  data: null,
  ...overrides,
});

describe('NotificationItem', () => {
  const mockOnRead = jest.fn();
  const mockOnDelete = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('rendering', () => {
    it('renders notification title', () => {
      render(
        <NotificationItem
          notification={createNotification()}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      expect(screen.getByText('New Message')).toBeInTheDocument();
    });

    it('renders notification body', () => {
      render(
        <NotificationItem
          notification={createNotification({ body: 'Test body content' })}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      expect(screen.getByText('Test body content')).toBeInTheDocument();
    });

    it('does not render body if not provided', () => {
      render(
        <NotificationItem
          notification={createNotification({ body: undefined })}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      expect(screen.queryByText('You have a new message from John')).not.toBeInTheDocument();
    });

    it('renders timestamp', () => {
      render(
        <NotificationItem
          notification={createNotification()}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      expect(screen.getByText('5 minutes ago')).toBeInTheDocument();
    });

    it('renders notification icon with correct category', () => {
      render(
        <NotificationItem
          notification={createNotification({ category: 'booking' })}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      expect(screen.getByTestId('notification-icon')).toHaveTextContent('booking');
    });

    it('shows unread indicator for unread notifications', () => {
      const { container } = render(
        <NotificationItem
          notification={createNotification({ read_at: null })}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      // Look for the blue dot indicator
      const unreadDot = container.querySelector('.bg-blue-500');
      expect(unreadDot).toBeInTheDocument();
    });

    it('does not show unread indicator for read notifications', () => {
      const { container } = render(
        <NotificationItem
          notification={createNotification({ read_at: '2024-01-15T11:00:00Z' })}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      const unreadDot = container.querySelector('.bg-blue-500');
      expect(unreadDot).not.toBeInTheDocument();
    });

    it('applies unread styling to container', () => {
      const { container } = render(
        <NotificationItem
          notification={createNotification({ read_at: null })}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      const item = container.querySelector('[role="menuitem"]');
      expect(item).toHaveClass('bg-blue-50/40');
    });

    it('applies bold styling to unread title', () => {
      render(
        <NotificationItem
          notification={createNotification({ read_at: null })}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      const title = screen.getByText('New Message');
      expect(title).toHaveClass('font-medium');
    });
  });

  describe('interactions', () => {
    it('calls onRead when unread notification is clicked', async () => {
      const user = userEvent.setup();

      render(
        <NotificationItem
          notification={createNotification({ read_at: null })}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      await user.click(screen.getByRole('menuitem'));

      expect(mockOnRead).toHaveBeenCalled();
    });

    it('does not call onRead when read notification is clicked', async () => {
      const user = userEvent.setup();

      render(
        <NotificationItem
          notification={createNotification({ read_at: '2024-01-15T11:00:00Z' })}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      await user.click(screen.getByRole('menuitem'));

      expect(mockOnRead).not.toHaveBeenCalled();
    });

    it('navigates to URL when notification has data.url', async () => {
      const user = userEvent.setup();

      render(
        <NotificationItem
          notification={createNotification({
            data: { url: '/student/lessons/123' },
          })}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      await user.click(screen.getByRole('menuitem'));

      expect(mockPush).toHaveBeenCalledWith('/student/lessons/123');
    });

    it('does not navigate when url is not a string', async () => {
      const user = userEvent.setup();

      render(
        <NotificationItem
          notification={createNotification({
            data: { url: 123 },
          })}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      await user.click(screen.getByRole('menuitem'));

      expect(mockPush).not.toHaveBeenCalled();
    });
  });

  describe('delete button', () => {
    it('shows delete button on hover', async () => {
      const user = userEvent.setup();

      render(
        <NotificationItem
          notification={createNotification()}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      const item = screen.getByRole('menuitem');
      await user.hover(item);

      expect(screen.getByRole('button', { name: 'Delete notification' })).toBeInTheDocument();
    });

    it('hides delete button when not hovered', () => {
      render(
        <NotificationItem
          notification={createNotification()}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      expect(screen.queryByRole('button', { name: 'Delete notification' })).not.toBeInTheDocument();
    });

    it('calls onDelete when delete button is clicked', async () => {
      const user = userEvent.setup();

      render(
        <NotificationItem
          notification={createNotification()}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      const item = screen.getByRole('menuitem');
      // Trigger mouse enter to show delete button
      fireEvent.mouseEnter(item);

      const deleteButton = screen.getByRole('button', { name: 'Delete notification' });
      await user.click(deleteButton);

      expect(mockOnDelete).toHaveBeenCalled();
    });

    it('stops propagation when delete is clicked', async () => {
      const user = userEvent.setup();

      render(
        <NotificationItem
          notification={createNotification({
            data: { url: '/some/path' },
            read_at: null,
          })}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      const item = screen.getByRole('menuitem');
      fireEvent.mouseEnter(item);

      const deleteButton = screen.getByRole('button', { name: 'Delete notification' });
      await user.click(deleteButton);

      // onRead should not be called because click was on delete button
      // (stopPropagation prevents the parent click handler)
      expect(mockOnRead).not.toHaveBeenCalled();
    });
  });

  describe('keyboard interaction', () => {
    it('triggers click on Enter key', () => {
      render(
        <NotificationItem
          notification={createNotification({ read_at: null })}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      const item = screen.getByRole('menuitem');
      fireEvent.keyDown(item, { key: 'Enter' });

      expect(mockOnRead).toHaveBeenCalled();
    });

    it('triggers click on Space key', () => {
      render(
        <NotificationItem
          notification={createNotification({ read_at: null })}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      const item = screen.getByRole('menuitem');
      fireEvent.keyDown(item, { key: ' ' });

      expect(mockOnRead).toHaveBeenCalled();
    });

    it('does not trigger on other keys', () => {
      render(
        <NotificationItem
          notification={createNotification({ read_at: null })}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      const item = screen.getByRole('menuitem');
      fireEvent.keyDown(item, { key: 'Tab' });

      expect(mockOnRead).not.toHaveBeenCalled();
    });
  });

  describe('accessibility', () => {
    it('has proper role and tabIndex', () => {
      render(
        <NotificationItem
          notification={createNotification()}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      const item = screen.getByRole('menuitem');
      expect(item).toHaveAttribute('tabindex', '0');
      expect(item).toHaveAttribute('data-notification-item', 'true');
    });

    it('has proper aria-label', () => {
      render(
        <NotificationItem
          notification={createNotification({ read_at: null })}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      expect(screen.getByLabelText('New Message (unread)')).toBeInTheDocument();
    });

    it('has proper aria-label for read notification', () => {
      render(
        <NotificationItem
          notification={createNotification({ read_at: '2024-01-15T11:00:00Z' })}
          onRead={mockOnRead}
          onDelete={mockOnDelete}
        />
      );

      expect(screen.getByLabelText('New Message')).toBeInTheDocument();
    });
  });
});
