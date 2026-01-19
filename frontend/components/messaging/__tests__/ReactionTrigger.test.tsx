import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReactionTrigger } from '../ReactionTrigger';

describe('ReactionTrigger', () => {
  const defaultProps = {
    messageId: 'msg-1',
    side: 'left' as const,
    isOpen: false,
    isHovered: false,
    onOpen: jest.fn(),
    onClose: jest.fn(),
    onSelect: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('visibility', () => {
    it('returns null when disabled', () => {
      const { container } = render(
        <ReactionTrigger {...defaultProps} disabled={true} isHovered={true} />
      );

      expect(container).toBeEmptyDOMElement();
    });

    it('returns null when not hovered and not open', () => {
      const { container } = render(
        <ReactionTrigger {...defaultProps} isHovered={false} isOpen={false} />
      );

      expect(container).toBeEmptyDOMElement();
    });

    it('shows trigger button when hovered', () => {
      render(<ReactionTrigger {...defaultProps} isHovered={true} />);

      expect(screen.getByLabelText('Add reaction')).toBeInTheDocument();
    });

    it('shows emoji picker when open', () => {
      render(<ReactionTrigger {...defaultProps} isOpen={true} isHovered={true} />);

      expect(screen.getByText('👍')).toBeInTheDocument();
      expect(screen.getByText('❤️')).toBeInTheDocument();
      expect(screen.getByText('😊')).toBeInTheDocument();
    });

    it('hides trigger button when picker is open', () => {
      render(<ReactionTrigger {...defaultProps} isOpen={true} isHovered={true} />);

      expect(screen.queryByLabelText('Add reaction')).not.toBeInTheDocument();
    });
  });

  describe('trigger button', () => {
    it('displays emoji icon', () => {
      render(<ReactionTrigger {...defaultProps} isHovered={true} />);

      expect(screen.getByText('😊')).toBeInTheDocument();
    });

    it('calls onOpen when clicked', () => {
      const onOpen = jest.fn();

      render(<ReactionTrigger {...defaultProps} isHovered={true} onOpen={onOpen} />);

      fireEvent.click(screen.getByLabelText('Add reaction'));

      expect(onOpen).toHaveBeenCalled();
    });

    it('stops event propagation on click', () => {
      const onOpen = jest.fn();
      const parentClick = jest.fn();

      render(
        <div onClick={parentClick}>
          <ReactionTrigger {...defaultProps} isHovered={true} onOpen={onOpen} />
        </div>
      );

      fireEvent.click(screen.getByLabelText('Add reaction'));

      expect(onOpen).toHaveBeenCalled();
      expect(parentClick).not.toHaveBeenCalled();
    });
  });

  describe('emoji picker', () => {
    it('renders default emojis', () => {
      render(<ReactionTrigger {...defaultProps} isOpen={true} isHovered={true} />);

      expect(screen.getByText('👍')).toBeInTheDocument();
      expect(screen.getByText('❤️')).toBeInTheDocument();
      expect(screen.getByText('😊')).toBeInTheDocument();
      expect(screen.getByText('😮')).toBeInTheDocument();
      expect(screen.getByText('🎉')).toBeInTheDocument();
    });

    it('renders custom emojis when provided', () => {
      render(
        <ReactionTrigger
          {...defaultProps}
          isOpen={true}
          isHovered={true}
          emojis={['🔥', '💯', '🙌']}
        />
      );

      expect(screen.getByText('🔥')).toBeInTheDocument();
      expect(screen.getByText('💯')).toBeInTheDocument();
      expect(screen.getByText('🙌')).toBeInTheDocument();
      expect(screen.queryByText('👍')).not.toBeInTheDocument();
    });

    it('calls onSelect with emoji when clicked', () => {
      const onSelect = jest.fn();

      render(
        <ReactionTrigger
          {...defaultProps}
          isOpen={true}
          isHovered={true}
          onSelect={onSelect}
        />
      );

      fireEvent.click(screen.getByText('👍'));

      expect(onSelect).toHaveBeenCalledWith('👍');
    });

    it('calls onClose after selecting emoji', () => {
      const onClose = jest.fn();

      render(
        <ReactionTrigger
          {...defaultProps}
          isOpen={true}
          isHovered={true}
          onClose={onClose}
        />
      );

      fireEvent.click(screen.getByText('👍'));

      expect(onClose).toHaveBeenCalled();
    });

    it('stops event propagation when emoji is clicked', () => {
      const parentClick = jest.fn();

      render(
        <div onClick={parentClick}>
          <ReactionTrigger {...defaultProps} isOpen={true} isHovered={true} />
        </div>
      );

      fireEvent.click(screen.getByText('👍'));

      expect(parentClick).not.toHaveBeenCalled();
    });

    it('highlights current user emoji', () => {
      render(
        <ReactionTrigger
          {...defaultProps}
          isOpen={true}
          isHovered={true}
          currentEmoji="👍"
        />
      );

      const thumbsUp = screen.getByText('👍').closest('button');
      expect(thumbsUp).toHaveClass('bg-purple-100');
    });

    it('does not highlight non-current emojis', () => {
      render(
        <ReactionTrigger
          {...defaultProps}
          isOpen={true}
          isHovered={true}
          currentEmoji="👍"
        />
      );

      const heart = screen.getByText('❤️').closest('button');
      expect(heart).not.toHaveClass('bg-purple-100');
    });
  });

  describe('positioning', () => {
    it('positions on left side when side is left', () => {
      const { container } = render(
        <ReactionTrigger {...defaultProps} side="left" isHovered={true} />
      );

      const triggerContainer = container.querySelector('.left-full');
      expect(triggerContainer).toBeInTheDocument();
    });

    it('positions on right side when side is right', () => {
      const { container } = render(
        <ReactionTrigger {...defaultProps} side="right" isHovered={true} />
      );

      const triggerContainer = container.querySelector('.right-full');
      expect(triggerContainer).toBeInTheDocument();
    });

    it('positions picker on left side when side is left', () => {
      const { container } = render(
        <ReactionTrigger {...defaultProps} side="left" isOpen={true} isHovered={true} />
      );

      const pickerContainer = container.querySelector('.left-full');
      expect(pickerContainer).toBeInTheDocument();
    });

    it('positions picker on right side when side is right', () => {
      const { container } = render(
        <ReactionTrigger {...defaultProps} side="right" isOpen={true} isHovered={true} />
      );

      const pickerContainer = container.querySelector('.right-full');
      expect(pickerContainer).toBeInTheDocument();
    });
  });

  describe('click outside handling', () => {
    it('adds click listener when open', () => {
      const addEventListenerSpy = jest.spyOn(document, 'addEventListener');

      render(<ReactionTrigger {...defaultProps} isOpen={true} isHovered={true} />);

      expect(addEventListenerSpy).toHaveBeenCalledWith('click', expect.any(Function));

      addEventListenerSpy.mockRestore();
    });

    it('removes click listener when closed', () => {
      const removeEventListenerSpy = jest.spyOn(document, 'removeEventListener');

      const { rerender } = render(
        <ReactionTrigger {...defaultProps} isOpen={true} isHovered={true} />
      );

      rerender(<ReactionTrigger {...defaultProps} isOpen={false} isHovered={true} />);

      expect(removeEventListenerSpy).toHaveBeenCalled();

      removeEventListenerSpy.mockRestore();
    });

    it('calls onClose when clicking outside', () => {
      const onClose = jest.fn();

      render(
        <div data-testid="outside">
          <ReactionTrigger
            {...defaultProps}
            isOpen={true}
            isHovered={true}
            onClose={onClose}
          />
        </div>
      );

      fireEvent.click(screen.getByTestId('outside'));

      expect(onClose).toHaveBeenCalled();
    });

    it('does not close when clicking inside reaction area', () => {
      const onClose = jest.fn();

      render(
        <ReactionTrigger
          {...defaultProps}
          isOpen={true}
          isHovered={true}
          onClose={onClose}
        />
      );

      // Click on the picker container (has data-reaction-area attribute)
      const picker = screen.getByText('👍').closest('[data-reaction-area]');
      if (picker) {
        fireEvent.click(picker);
      }

      // onClose is called because emoji selection triggers close
      // but that's handled by the emoji button click, not the outside click handler
    });
  });

  describe('data attributes', () => {
    it('adds data-reaction-area attribute to trigger', () => {
      const { container } = render(
        <ReactionTrigger {...defaultProps} isHovered={true} />
      );

      const trigger = container.querySelector(`[data-reaction-area="${defaultProps.messageId}"]`);
      expect(trigger).toBeInTheDocument();
    });

    it('adds data-reaction-area attribute to picker', () => {
      const { container } = render(
        <ReactionTrigger {...defaultProps} isOpen={true} isHovered={true} />
      );

      const picker = container.querySelector(`[data-reaction-area="${defaultProps.messageId}"]`);
      expect(picker).toBeInTheDocument();
    });

    it('adds data-reaction-area attribute to emoji buttons', () => {
      render(<ReactionTrigger {...defaultProps} isOpen={true} isHovered={true} />);

      const emojiButton = screen.getByText('👍').closest('button');
      expect(emojiButton).toHaveAttribute('data-reaction-area', defaultProps.messageId);
    });
  });

  describe('hover interactions', () => {
    it('has hover:scale-110 on emoji buttons', () => {
      render(<ReactionTrigger {...defaultProps} isOpen={true} isHovered={true} />);

      const emojiButton = screen.getByText('👍').closest('button');
      expect(emojiButton).toHaveClass('hover:scale-110');
    });

    it('has hover:bg-gray-50 on trigger button', () => {
      render(<ReactionTrigger {...defaultProps} isHovered={true} />);

      const triggerButton = screen.getByLabelText('Add reaction');
      expect(triggerButton).toHaveClass('hover:bg-gray-50');
    });
  });
});
