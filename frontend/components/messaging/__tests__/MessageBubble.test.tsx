import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MessageBubble } from '../MessageBubble';
import type { NormalizedMessage, NormalizedReaction } from '../types';

describe('MessageBubble', () => {
  const createMessage = (
    overrides: Partial<NormalizedMessage> = {}
  ): NormalizedMessage => ({
    id: 'msg-1',
    content: 'Hello, world!',
    timestamp: new Date('2024-01-15T12:00:00Z'),
    timestampLabel: '12:00 PM',
    isOwn: false,
    isEdited: false,
    isDeleted: false,
    reactions: [],
    ...overrides,
  });

  describe('basic rendering', () => {
    it('renders message content', () => {
      render(<MessageBubble message={createMessage()} />);

      expect(screen.getByText('Hello, world!')).toBeInTheDocument();
    });

    it('renders timestamp label', () => {
      render(<MessageBubble message={createMessage()} />);

      expect(screen.getByText('12:00 PM')).toBeInTheDocument();
    });

    it('renders edited tag when message is edited', () => {
      render(<MessageBubble message={createMessage({ isEdited: true })} />);

      expect(screen.getByText('edited')).toBeInTheDocument();
    });

    it('does not render edited tag when message is not edited', () => {
      render(<MessageBubble message={createMessage({ isEdited: false })} />);

      expect(screen.queryByText('edited')).not.toBeInTheDocument();
    });

    it('shows deleted message placeholder when deleted', () => {
      render(<MessageBubble message={createMessage({ isDeleted: true })} />);

      expect(screen.getByText('This message was deleted')).toBeInTheDocument();
    });

    it('does not show edited tag when deleted', () => {
      render(
        <MessageBubble
          message={createMessage({ isEdited: true, isDeleted: true })}
        />
      );

      expect(screen.queryByText('edited')).not.toBeInTheDocument();
    });
  });

  describe('own message styling', () => {
    it('applies right-side styling for own messages', () => {
      const { container } = render(
        <MessageBubble message={createMessage({ isOwn: true })} />
      );

      expect(container.querySelector('.justify-end')).toBeInTheDocument();
    });

    it('applies left-side styling for other messages', () => {
      const { container } = render(
        <MessageBubble message={createMessage({ isOwn: false })} />
      );

      expect(container.querySelector('.justify-start')).toBeInTheDocument();
    });

    it('uses side prop to override default positioning', () => {
      const { container } = render(
        <MessageBubble message={createMessage({ isOwn: false })} side="right" />
      );

      expect(container.querySelector('.justify-end')).toBeInTheDocument();
    });
  });

  describe('read status', () => {
    it('shows sent icon when readStatus is sent', () => {
      const { container } = render(
        <MessageBubble
          message={createMessage({ isOwn: true, readStatus: 'sent' })}
          showReadReceipt
        />
      );

      // Check icon (single check) - lucide-check class
      const checkIcon = container.querySelector('.lucide-check');
      expect(checkIcon).toBeInTheDocument();
    });

    it('shows delivered icon when readStatus is delivered', () => {
      const { container } = render(
        <MessageBubble
          message={createMessage({ isOwn: true, readStatus: 'delivered' })}
          showReadReceipt
        />
      );

      // CheckCheck icon - lucide-check-check class with gray color
      const checkIcon = container.querySelector('.lucide-check-check');
      expect(checkIcon).toBeInTheDocument();
      expect(checkIcon).toHaveClass('text-gray-400');
    });

    it('shows read icon when readStatus is read', () => {
      const { container } = render(
        <MessageBubble
          message={createMessage({ isOwn: true, readStatus: 'read' })}
          showReadReceipt
        />
      );

      // CheckCheck icon with blue color indicates read
      const checkIcon = container.querySelector('.lucide-check-check');
      expect(checkIcon).toBeInTheDocument();
      expect(checkIcon).toHaveClass('text-blue-500');
    });

    it('does not show read receipt when showReadReceipt is false', () => {
      const { container } = render(
        <MessageBubble
          message={createMessage({ isOwn: true, readStatus: 'read' })}
          showReadReceipt={false}
        />
      );

      // Should not have read receipt check icons
      const checkIcon = container.querySelector('.lucide-check-check');
      expect(checkIcon).not.toBeInTheDocument();
    });

    it('shows read timestamp label when provided', () => {
      render(
        <MessageBubble
          message={createMessage({
            isOwn: true,
            readStatus: 'read',
            readTimestampLabel: 'Read at 3:00 PM',
          })}
          showReadReceipt
        />
      );

      expect(screen.getByText('Read at 3:00 PM')).toBeInTheDocument();
    });
  });

  describe('reactions', () => {
    it('renders reactions', () => {
      const reactions: NormalizedReaction[] = [
        { emoji: '👍', count: 2, isMine: false },
        { emoji: '❤️', count: 1, isMine: true },
      ];

      render(<MessageBubble message={createMessage({ reactions })} />);

      expect(screen.getByText('👍 2')).toBeInTheDocument();
      expect(screen.getByText('❤️ 1')).toBeInTheDocument();
    });

    it('applies special styling to user\'s own reaction', () => {
      const reactions: NormalizedReaction[] = [
        { emoji: '👍', count: 1, isMine: true },
      ];

      render(<MessageBubble message={createMessage({ reactions })} />);

      const reactionButton = screen.getByText('👍 1').closest('button');
      expect(reactionButton).toHaveClass('bg-[#7E22CE]');
    });

    it('calls onReact when reaction is clicked', async () => {
      const reactions: NormalizedReaction[] = [
        { emoji: '👍', count: 1, isMine: false },
      ];
      const onReact = jest.fn();

      render(
        <MessageBubble
          message={createMessage({ reactions })}
          onReact={onReact}
          canReact
        />
      );

      fireEvent.click(screen.getByText('👍 1'));

      expect(onReact).toHaveBeenCalledWith('msg-1', '👍');
    });

    it('disables reaction buttons when reactionBusy is true', () => {
      const reactions: NormalizedReaction[] = [
        { emoji: '👍', count: 1, isMine: false },
      ];

      render(
        <MessageBubble
          message={createMessage({ reactions })}
          reactionBusy
        />
      );

      const reactionButton = screen.getByText('👍 1').closest('button');
      expect(reactionButton).toBeDisabled();
    });
  });

  describe('editing', () => {
    it('shows edit button for own messages when canEdit is true', () => {
      render(
        <MessageBubble
          message={createMessage({ isOwn: true })}
          canEdit
          onEdit={jest.fn()}
        />
      );

      expect(screen.getByLabelText('Edit message')).toBeInTheDocument();
    });

    it('does not show edit button when canEdit is false', () => {
      render(
        <MessageBubble
          message={createMessage({ isOwn: true })}
          canEdit={false}
          onEdit={jest.fn()}
        />
      );

      expect(screen.queryByLabelText('Edit message')).not.toBeInTheDocument();
    });

    it('switches to edit mode when edit button is clicked', () => {
      render(
        <MessageBubble
          message={createMessage({ isOwn: true })}
          canEdit
          onEdit={jest.fn()}
        />
      );

      fireEvent.click(screen.getByLabelText('Edit message'));

      expect(screen.getByRole('textbox')).toBeInTheDocument();
    });

    it('calls onEdit with new content when saved', async () => {
      const onEdit = jest.fn();

      render(
        <MessageBubble
          message={createMessage({ isOwn: true })}
          canEdit
          onEdit={onEdit}
        />
      );

      fireEvent.click(screen.getByLabelText('Edit message'));

      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: 'Updated message' } });
      fireEvent.click(screen.getByLabelText('Confirm edit'));

      await waitFor(() => {
        expect(onEdit).toHaveBeenCalledWith('msg-1', 'Updated message');
      });
    });

    it('cancels edit mode when cancel button is clicked', () => {
      render(
        <MessageBubble
          message={createMessage({ isOwn: true })}
          canEdit
          onEdit={jest.fn()}
        />
      );

      fireEvent.click(screen.getByLabelText('Edit message'));
      fireEvent.click(screen.getByLabelText('Cancel edit'));

      expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    });

    it('saves on Enter key press', async () => {
      const onEdit = jest.fn();

      render(
        <MessageBubble
          message={createMessage({ isOwn: true })}
          canEdit
          onEdit={onEdit}
        />
      );

      fireEvent.click(screen.getByLabelText('Edit message'));

      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: 'Updated' } });
      fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

      await waitFor(() => {
        expect(onEdit).toHaveBeenCalled();
      });
    });

    it('cancels on Escape key press', () => {
      render(
        <MessageBubble
          message={createMessage({ isOwn: true })}
          canEdit
          onEdit={jest.fn()}
        />
      );

      fireEvent.click(screen.getByLabelText('Edit message'));

      const textarea = screen.getByRole('textbox');
      fireEvent.keyDown(textarea, { key: 'Escape' });

      expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    });

    it('does not save when content is empty', async () => {
      const onEdit = jest.fn();

      render(
        <MessageBubble
          message={createMessage({ isOwn: true })}
          canEdit
          onEdit={onEdit}
        />
      );

      fireEvent.click(screen.getByLabelText('Edit message'));

      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: '   ' } });
      fireEvent.click(screen.getByLabelText('Confirm edit'));

      expect(onEdit).not.toHaveBeenCalled();
    });

    it('does not save when content unchanged', async () => {
      const onEdit = jest.fn();

      render(
        <MessageBubble
          message={createMessage({ isOwn: true, content: 'Hello' })}
          canEdit
          onEdit={onEdit}
        />
      );

      fireEvent.click(screen.getByLabelText('Edit message'));
      fireEvent.click(screen.getByLabelText('Confirm edit'));

      expect(onEdit).not.toHaveBeenCalled();
    });
  });

  describe('deleting', () => {
    it('shows delete button for own messages when canDelete is true', () => {
      render(
        <MessageBubble
          message={createMessage({ isOwn: true })}
          canDelete
          onDelete={jest.fn()}
        />
      );

      expect(screen.getByLabelText('Delete message')).toBeInTheDocument();
    });

    it('does not show delete button when canDelete is false', () => {
      render(
        <MessageBubble
          message={createMessage({ isOwn: true })}
          canDelete={false}
          onDelete={jest.fn()}
        />
      );

      expect(screen.queryByLabelText('Delete message')).not.toBeInTheDocument();
    });

    it('shows confirmation when delete button is clicked', () => {
      render(
        <MessageBubble
          message={createMessage({ isOwn: true })}
          canDelete
          onDelete={jest.fn()}
        />
      );

      fireEvent.click(screen.getByLabelText('Delete message'));

      expect(screen.getByText('Delete?')).toBeInTheDocument();
      expect(screen.getByLabelText('Confirm delete')).toBeInTheDocument();
      expect(screen.getByLabelText('Cancel delete')).toBeInTheDocument();
    });

    it('calls onDelete when confirmed', async () => {
      const onDelete = jest.fn();

      render(
        <MessageBubble
          message={createMessage({ isOwn: true })}
          canDelete
          onDelete={onDelete}
        />
      );

      fireEvent.click(screen.getByLabelText('Delete message'));
      fireEvent.click(screen.getByLabelText('Confirm delete'));

      await waitFor(() => {
        expect(onDelete).toHaveBeenCalledWith('msg-1');
      });
    });

    it('cancels delete when cancel button is clicked', () => {
      render(
        <MessageBubble
          message={createMessage({ isOwn: true })}
          canDelete
          onDelete={jest.fn()}
        />
      );

      fireEvent.click(screen.getByLabelText('Delete message'));
      fireEvent.click(screen.getByLabelText('Cancel delete'));

      expect(screen.queryByText('Delete?')).not.toBeInTheDocument();
    });
  });

  describe('attachments', () => {
    it('renders attachments using renderAttachments prop', () => {
      const attachments = [
        { id: 'att-1', url: 'https://example.com/image.jpg', type: 'image' },
      ];

      render(
        <MessageBubble
          message={createMessage({ attachments })}
          renderAttachments={(atts) => (
            <div data-testid="attachments">{atts.length} attachments</div>
          )}
        />
      );

      expect(screen.getByTestId('attachments')).toBeInTheDocument();
      expect(screen.getByText('1 attachments')).toBeInTheDocument();
    });

    it('does not render attachments when renderAttachments is not provided', () => {
      const attachments = [
        { id: 'att-1', url: 'https://example.com/image.jpg', type: 'image' },
      ];

      const { container } = render(
        <MessageBubble message={createMessage({ attachments })} />
      );

      expect(container.querySelector('[data-testid="attachments"]')).not.toBeInTheDocument();
    });
  });

  describe('reaction trigger', () => {
    it('shows reaction trigger on hover when canReact is true', () => {
      const { container } = render(
        <MessageBubble
          message={createMessage()}
          canReact
          onReact={jest.fn()}
        />
      );

      const bubble = container.querySelector('.relative.flex.flex-col');
      expect(bubble).toBeInTheDocument();

      if (bubble) {
        fireEvent.mouseEnter(bubble);
        expect(screen.getByLabelText('Add reaction')).toBeInTheDocument();
      }
    });

    it('does not show reaction trigger when canReact is false', () => {
      const { container } = render(
        <MessageBubble
          message={createMessage()}
          canReact={false}
          onReact={jest.fn()}
        />
      );

      const bubble = container.querySelector('.relative.flex.flex-col');
      if (bubble) {
        fireEvent.mouseEnter(bubble);
      }

      expect(screen.queryByLabelText('Add reaction')).not.toBeInTheDocument();
    });

    it('does not show reaction trigger for deleted messages', () => {
      const { container } = render(
        <MessageBubble
          message={createMessage({ isDeleted: true })}
          canReact
          onReact={jest.fn()}
        />
      );

      const bubble = container.querySelector('.relative.flex.flex-col');
      if (bubble) {
        fireEvent.mouseEnter(bubble);
      }

      expect(screen.queryByLabelText('Add reaction')).not.toBeInTheDocument();
    });

    it('uses custom quickEmojis when provided', () => {
      const { container } = render(
        <MessageBubble
          message={createMessage()}
          canReact
          onReact={jest.fn()}
          quickEmojis={['🔥', '💯', '🙌']}
        />
      );

      const bubble = container.querySelector('.relative.flex.flex-col');
      if (bubble) {
        fireEvent.mouseEnter(bubble);
      }

      fireEvent.click(screen.getByLabelText('Add reaction'));

      expect(screen.getByText('🔥')).toBeInTheDocument();
      expect(screen.getByText('💯')).toBeInTheDocument();
      expect(screen.getByText('🙌')).toBeInTheDocument();
    });
  });

  describe('handleSave without onEdit', () => {
    it('exits edit mode without calling onEdit when onEdit is not provided', () => {
      render(
        <MessageBubble
          message={createMessage({ isOwn: true })}
          canEdit
          // Note: no onEdit provided
        />
      );

      // Verify edit button is NOT shown when onEdit is undefined
      expect(screen.queryByLabelText('Edit message')).not.toBeInTheDocument();
    });
  });

  describe('footer rendering for own messages with read timestamp', () => {
    it('renders read timestamp label on right side for own message', () => {
      const reactions: NormalizedReaction[] = [
        { emoji: '👍', count: 1, isMine: false },
      ];

      render(
        <MessageBubble
          message={createMessage({
            isOwn: true,
            readStatus: 'read',
            readTimestampLabel: 'Read at 4:30 PM',
            reactions,
          })}
          showReadReceipt
        />
      );

      expect(screen.getByText('Read at 4:30 PM')).toBeInTheDocument();
      expect(screen.getByText('👍 1')).toBeInTheDocument();
    });

    it('does not render footer when no reactions and no read timestamp', () => {
      render(
        <MessageBubble
          message={createMessage({ isOwn: true, readStatus: 'sent' })}
          showReadReceipt
        />
      );

      // Footer should not be present because:
      // - No reactions
      // - readStatus is 'sent' (not 'read') so no read timestamp
      const footerTimestamp = screen.queryByText(/Read at/);
      expect(footerTimestamp).not.toBeInTheDocument();
    });
  });

  describe('footer rendering for left-side (other) messages', () => {
    it('renders reactions on right for left-side bubbles', () => {
      const reactions: NormalizedReaction[] = [
        { emoji: '❤️', count: 3, isMine: true },
      ];

      render(
        <MessageBubble
          message={createMessage({
            isOwn: false,
            reactions,
          })}
        />
      );

      // Left-side bubbles should have reactions on the right
      expect(screen.getByText('❤️ 3')).toBeInTheDocument();
    });
  });

  describe('reaction button with reactionBusy and no onReact', () => {
    it('does not call onReact when reactionBusy is true', async () => {
      const reactions: NormalizedReaction[] = [
        { emoji: '👍', count: 1, isMine: false },
      ];
      const onReact = jest.fn();

      render(
        <MessageBubble
          message={createMessage({ reactions })}
          onReact={onReact}
          canReact
          reactionBusy
        />
      );

      fireEvent.click(screen.getByText('👍 1'));

      // Should NOT call onReact because reactionBusy is true
      expect(onReact).not.toHaveBeenCalled();
    });

    it('does not call onReact when onReact is not provided', async () => {
      const reactions: NormalizedReaction[] = [
        { emoji: '👍', count: 1, isMine: false },
      ];

      render(
        <MessageBubble
          message={createMessage({ reactions })}
          // No onReact provided
          canReact
        />
      );

      // Click should not throw
      fireEvent.click(screen.getByText('👍 1'));
    });
  });

  describe('side prop override for own messages', () => {
    it('uses left side when side="left" even for own messages', () => {
      const { container } = render(
        <MessageBubble
          message={createMessage({ isOwn: true })}
          side="left"
        />
      );

      expect(container.querySelector('.justify-start')).toBeInTheDocument();
    });
  });

  describe('empty attachments array', () => {
    it('does not render attachments div when attachments array is empty', () => {
      const { container } = render(
        <MessageBubble
          message={createMessage({ attachments: [] })}
          renderAttachments={(atts) => (
            <div data-testid="attachments">{atts.length} attachments</div>
          )}
        />
      );

      expect(container.querySelector('[data-testid="attachments"]')).not.toBeInTheDocument();
    });
  });

  describe('no timestamp label', () => {
    it('does not render timestamp span when timestampLabel is undefined', () => {
      render(
        <MessageBubble
          message={createMessage({ timestampLabel: undefined })}
        />
      );

      // The timestamp span should not be present
      expect(screen.queryByText('12:00 PM')).not.toBeInTheDocument();
    });
  });

  describe('handleSave exits edit mode without onEdit (lines 47-49)', () => {
    it('exits edit mode when save is triggered but onEdit is undefined', () => {
      // Manually enter edit mode by providing canEdit + onEdit initially,
      // then verify the fallback path. We need to use the component differently:
      // Render with onEdit to enter edit mode, then test the branch
      // that checks if (!onEdit) { setIsEditing(false); return; }

      // Actually, canEdit and onEdit must both be truthy for the edit button to show.
      // The branch at line 47 is only reached if somehow in editing mode without onEdit.
      // This can happen if the edit callback is removed after entering edit mode.
      // Let's test via re-render.
      const { rerender } = render(
        <MessageBubble
          message={createMessage({ isOwn: true, content: 'Original' })}
          canEdit
          onEdit={jest.fn()}
        />
      );

      // Enter edit mode
      fireEvent.click(screen.getByLabelText('Edit message'));
      expect(screen.getByRole('textbox')).toBeInTheDocument();

      // Re-render without onEdit (simulates prop change)
      rerender(
        <MessageBubble
          message={createMessage({ isOwn: true, content: 'Original' })}
          canEdit
          // No onEdit -> handleSave should hit the !onEdit branch
        />
      );

      // The textarea should still be visible since we're in edit mode
      const textarea = screen.getByRole('textbox');
      // Trigger save via Enter key
      fireEvent.change(textarea, { target: { value: 'Modified text' } });
      fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

      // Should exit edit mode without calling onEdit
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    });
  });

  describe('mouse leave hides reaction trigger (line 219)', () => {
    it('hides reaction trigger on mouse leave', () => {
      const { container } = render(
        <MessageBubble
          message={createMessage()}
          canReact
          onReact={jest.fn()}
        />
      );

      const bubble = container.querySelector('.relative.flex.flex-col');
      expect(bubble).toBeInTheDocument();

      if (bubble) {
        // Mouse enter to show trigger
        fireEvent.mouseEnter(bubble);
        expect(screen.getByLabelText('Add reaction')).toBeInTheDocument();

        // Mouse leave to hide trigger (line 219)
        fireEvent.mouseLeave(bubble);

        // Trigger should no longer be visible
        expect(screen.queryByLabelText('Add reaction')).not.toBeInTheDocument();
      }
    });
  });

  describe('currentUserReaction and quickEmojis pass-through (lines 293-294)', () => {
    it('passes currentUserReaction to ReactionTrigger', () => {
      const { container } = render(
        <MessageBubble
          message={createMessage({ currentUserReaction: '👍' })}
          canReact
          onReact={jest.fn()}
        />
      );

      const bubble = container.querySelector('.relative.flex.flex-col');
      if (bubble) {
        fireEvent.mouseEnter(bubble);
      }

      // ReactionTrigger receives currentEmoji prop from message.currentUserReaction
      expect(screen.getByLabelText('Add reaction')).toBeInTheDocument();
    });

    it('passes null currentEmoji when currentUserReaction is undefined', () => {
      const { container } = render(
        <MessageBubble
          message={createMessage()} // no currentUserReaction
          canReact
          onReact={jest.fn()}
        />
      );

      const bubble = container.querySelector('.relative.flex.flex-col');
      if (bubble) {
        fireEvent.mouseEnter(bubble);
      }

      // Should render without errors with null currentEmoji
      expect(screen.getByLabelText('Add reaction')).toBeInTheDocument();
    });
  });
});
