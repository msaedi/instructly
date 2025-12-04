import { fireEvent, render, screen } from '@testing-library/react';
import { MessageBubble } from '@/components/instructor/messages/components/MessageBubble';
import type { MessageWithAttachments } from '@/components/instructor/messages/types';

describe('MessageBubble', () => {
  const baseMessage: MessageWithAttachments = {
    id: 'msg1',
    text: 'Hello',
    sender: 'instructor',
    timestamp: 'Just now',
    createdAt: '2024-01-01T12:00:00Z',
  };

  describe('read indicators', () => {
    it('should show single check when not delivered', () => {
      const { container } = render(
        <MessageBubble
          message={baseMessage}
          isLastInstructor={true}
          showReadIndicator={true}
          readReceiptCount={0}
          hasDeliveredAt={false}
          isOwnMessage={true}
        />
      );

      // Should have single check icon (Check component from lucide-react)
      const checkIcons = container.querySelectorAll('svg[class*="lucide-check"]');
      // Should have Check icon, not CheckCheck
      expect(checkIcons.length).toBeGreaterThan(0);
    });

    it('should show double gray check when delivered but not read', () => {
      const { container } = render(
        <MessageBubble
          message={baseMessage}
          isLastInstructor={true}
          showReadIndicator={true}
          readReceiptCount={0}
          hasDeliveredAt={true}
          isOwnMessage={true}
        />
      );

      // Should have CheckCheck icon with white/60 color
      const checkCheckIcon = container.querySelector('svg[class*="lucide-check-check"]');
      expect(checkCheckIcon).toBeInTheDocument();
      expect(checkCheckIcon).toHaveClass('text-white/60');
    });

    it('should show double blue check when read', () => {
      const { container } = render(
        <MessageBubble
          message={baseMessage}
          isLastInstructor={true}
          showReadIndicator={true}
          readReceiptCount={1}
          hasDeliveredAt={true}
          isOwnMessage={true}
        />
      );

      // Should have CheckCheck icon with blue color
      const checkCheckIcon = container.querySelector('svg[class*="lucide-check-check"]');
      expect(checkCheckIcon).toBeInTheDocument();
      expect(checkCheckIcon).toHaveClass('text-blue-300');
    });

    it('should show "Read at" timestamp on last read message', () => {
      render(
        <MessageBubble
          message={baseMessage}
          isLastInstructor={true}
          showReadIndicator={true}
          readReceiptCount={1}
          hasDeliveredAt={true}
          readTimestamp="Read at 12:05 PM"
          isOwnMessage={true}
        />
      );

      expect(screen.getByText('Read at 12:05 PM')).toBeInTheDocument();
    });

    it('should not show read indicator on received messages', () => {
      const studentMessage: MessageWithAttachments = {
        ...baseMessage,
        sender: 'student',
      };

      render(
        <MessageBubble
          message={studentMessage}
          isLastInstructor={false}
          showReadIndicator={false}
          isOwnMessage={false}
        />
      );

      const container = screen.getByText('Hello').closest('div');
      const checkIcon = container?.querySelector('[class*="lucide-check"]');
      expect(checkIcon).not.toBeInTheDocument();
    });
  });

  describe('reactions', () => {
    it('should display reactions when present', () => {
      const messageWithReactions: MessageWithAttachments = {
        ...baseMessage,
        reactions: { '👍': 2, '❤️': 1 },
      };

      render(
        <MessageBubble
          message={messageWithReactions}
          isLastInstructor={true}
          isOwnMessage={false}
          onReactionClick={jest.fn()}
          onToggleReactionPicker={jest.fn()}
        />
      );

      // Should show thumbs up emoji with count
      expect(screen.getByText(/👍 2/)).toBeInTheDocument();

      // Should show heart emoji with count
      expect(screen.getByText(/❤️ 1/)).toBeInTheDocument();
    });

    it('should show reaction picker button on hover for other user messages', () => {
      const studentMessage: MessageWithAttachments = {
        ...baseMessage,
        sender: 'student',
      };

      render(
        <MessageBubble
          message={studentMessage}
          isLastInstructor={false}
          isOwnMessage={false}
          onReactionClick={jest.fn()}
          onToggleReactionPicker={jest.fn()}
          showReactionPicker={false}
        />
      );

      // Hovering the bubble should show the reaction button
      fireEvent.mouseEnter(screen.getByTestId('message-bubble'));
      const addButton = screen.getByRole('button', { name: /add reaction/i });
      expect(addButton).toBeInTheDocument();
    });

    it('should show reaction options when picker is open', () => {
      const studentMessage: MessageWithAttachments = {
        ...baseMessage,
        sender: 'student',
      };

      render(
        <MessageBubble
          message={studentMessage}
          isLastInstructor={false}
          isOwnMessage={false}
          onReactionClick={jest.fn()}
          onToggleReactionPicker={jest.fn()}
          showReactionPicker={true}
        />
      );

      expect(screen.getByText('👍')).toBeInTheDocument();
      expect(screen.getByText('❤️')).toBeInTheDocument();
      expect(screen.getByText('😊')).toBeInTheDocument();
      expect(screen.getByText('😮')).toBeInTheDocument();
      expect(screen.getByText('🎉')).toBeInTheDocument();
    });

    it('should not show reaction picker on own messages', () => {
      render(
        <MessageBubble
          message={baseMessage}
          isLastInstructor={true}
          isOwnMessage={true}
          onReactionClick={jest.fn()}
          onToggleReactionPicker={jest.fn()}
        />
      );

      // Should not have the reaction picker controls
      const addButton = screen.queryByRole('button', { name: /add reaction/i });
      expect(addButton).not.toBeInTheDocument();
    });

    it('should highlight current user reaction', () => {
      const messageWithReactions: MessageWithAttachments = {
        ...baseMessage,
        sender: 'student',
        reactions: { '👍': 1 },
        my_reactions: ['👍'],
      };

      render(
        <MessageBubble
          message={messageWithReactions}
          isLastInstructor={false}
          isOwnMessage={false}
          currentReaction="👍"
          onReactionClick={jest.fn()}
          onToggleReactionPicker={jest.fn()}
        />
      );

      // Find the reaction button
      const thumbsUpButton = screen.getByRole('button', { name: /👍 1/ });
      expect(thumbsUpButton).toHaveClass('bg-[#7E22CE]');
      expect(thumbsUpButton).toHaveClass('text-white');
    });
  });

  describe('message styling', () => {
    it('should style instructor messages with purple background', () => {
      render(
        <MessageBubble
          message={baseMessage}
          isLastInstructor={true}
          isOwnMessage={true}
        />
      );

      const messageContainer = screen.getByTestId('message-bubble');
      expect(messageContainer).toHaveClass('bg-[#7E22CE]');
      expect(messageContainer).toHaveClass('text-white');
    });

    it('should style student messages with gray background', () => {
      const studentMessage: MessageWithAttachments = {
        ...baseMessage,
        sender: 'student',
      };

      render(
        <MessageBubble
          message={studentMessage}
          isLastInstructor={false}
          isOwnMessage={false}
        />
      );

      const messageContainer = screen.getByTestId('message-bubble');
      expect(messageContainer).toHaveClass('bg-gray-100');
      expect(messageContainer).toHaveClass('text-gray-800');
    });

    it('should style platform messages with blue background', () => {
      const platformMessage: MessageWithAttachments = {
        ...baseMessage,
        sender: 'platform',
      };

      render(
        <MessageBubble
          message={platformMessage}
          isLastInstructor={false}
          isOwnMessage={false}
        />
      );

      const messageContainer = screen.getByTestId('message-bubble');
      expect(messageContainer).toHaveClass('bg-blue-100');
      expect(messageContainer).toHaveClass('text-blue-800');
    });
  });

  describe('attachments', () => {
    it('should render image attachments', () => {
      const messageWithImage: MessageWithAttachments = {
        ...baseMessage,
        attachments: [
          {
            name: 'photo.jpg',
            type: 'image/jpeg',
            dataUrl: 'data:image/jpeg;base64,/9j/4AAQ...',
          },
        ],
      };

      render(
        <MessageBubble
          message={messageWithImage}
          isLastInstructor={true}
          isOwnMessage={true}
        />
      );

      const image = screen.getByAltText('photo.jpg');
      expect(image).toBeInTheDocument();
      expect(image).toHaveAttribute('src', 'data:image/jpeg;base64,/9j/4AAQ...');
    });

    it('should render non-image attachments with paperclip icon', () => {
      const messageWithFile: MessageWithAttachments = {
        ...baseMessage,
        attachments: [
          {
            name: 'document.pdf',
            type: 'application/pdf',
            dataUrl: '',
          },
        ],
      };

      render(
        <MessageBubble
          message={messageWithFile}
          isLastInstructor={true}
          isOwnMessage={true}
        />
      );

      expect(screen.getByText('document.pdf')).toBeInTheDocument();
      // Paperclip icon should be present
      const container = screen.getByText('document.pdf').closest('div');
      const paperclipIcon = container?.querySelector('[class*="lucide-paperclip"]');
      expect(paperclipIcon).toBeInTheDocument();
    });
  });

  describe('sender name', () => {
    it('should show sender name when showSenderName is true', () => {
      render(
        <MessageBubble
          message={baseMessage}
          isLastInstructor={true}
          showSenderName={true}
          senderName="John Instructor"
          isOwnMessage={true}
        />
      );

      expect(screen.getByText('John Instructor')).toBeInTheDocument();
    });

    it('should not show sender name when showSenderName is false', () => {
      render(
        <MessageBubble
          message={baseMessage}
          isLastInstructor={true}
          showSenderName={false}
          senderName="John Instructor"
          isOwnMessage={true}
        />
      );

      expect(screen.queryByText('John Instructor')).not.toBeInTheDocument();
    });
  });
});
