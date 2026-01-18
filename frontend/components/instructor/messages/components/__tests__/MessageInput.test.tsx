import { render, screen, fireEvent } from '@testing-library/react';
import { MessageInput, type MessageInputProps } from '../MessageInput';

describe('MessageInput', () => {
  const defaultProps: MessageInputProps = {
    messageText: '',
    pendingAttachments: [],
    isSendDisabled: false,
    typingUserName: null,
    messageDisplay: 'inbox',
    hasUpcomingBookings: true,
    onMessageChange: jest.fn(),
    onKeyPress: jest.fn(),
    onSend: jest.fn(),
    onAttachmentAdd: jest.fn(),
    onAttachmentRemove: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('inbox view', () => {
    it('renders textarea for message input', () => {
      render(<MessageInput {...defaultProps} />);

      expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
    });

    it('renders attachment button', () => {
      render(<MessageInput {...defaultProps} />);

      expect(screen.getByRole('button', { name: /attach file/i })).toBeInTheDocument();
    });

    it('renders send button', () => {
      render(<MessageInput {...defaultProps} />);

      const sendButton = screen.getByRole('button', { name: '' });
      expect(sendButton).toBeInTheDocument();
    });

    it('displays current message text', () => {
      render(<MessageInput {...defaultProps} messageText="Hello there" />);

      const textarea = screen.getByPlaceholderText('Type your message...');
      expect(textarea).toHaveValue('Hello there');
    });

    it('calls onMessageChange when typing', () => {
      const onMessageChange = jest.fn();
      render(<MessageInput {...defaultProps} onMessageChange={onMessageChange} />);

      const textarea = screen.getByPlaceholderText('Type your message...');
      fireEvent.change(textarea, { target: { value: 'New message' } });

      expect(onMessageChange).toHaveBeenCalledWith('New message');
    });

    it('renders textarea that accepts keyboard input', () => {
      render(<MessageInput {...defaultProps} />);

      const textarea = screen.getByPlaceholderText('Type your message...');
      // Verify textarea is enabled and can receive input
      expect(textarea).toBeEnabled();
      expect(textarea).toHaveAttribute('rows', '1');
    });

    it('calls onSend when clicking send button', () => {
      const onSend = jest.fn();
      render(<MessageInput {...defaultProps} onSend={onSend} />);

      const sendButtons = screen.getAllByRole('button');
      const sendButton = sendButtons[sendButtons.length - 1]!; // Last button is send
      fireEvent.click(sendButton);

      expect(onSend).toHaveBeenCalled();
    });

    it('disables send button when isSendDisabled is true', () => {
      render(<MessageInput {...defaultProps} isSendDisabled={true} />);

      const sendButtons = screen.getAllByRole('button');
      const sendButton = sendButtons[sendButtons.length - 1];
      expect(sendButton).toBeDisabled();
    });
  });

  describe('typing indicator', () => {
    it('shows typing indicator when typingUserName is set', () => {
      render(<MessageInput {...defaultProps} typingUserName="John" />);

      expect(screen.getByText('John is typing...')).toBeInTheDocument();
    });

    it('does not show typing indicator when null', () => {
      render(<MessageInput {...defaultProps} />);

      expect(screen.queryByText(/is typing/)).not.toBeInTheDocument();
    });
  });

  describe('attachments', () => {
    const mockFiles: File[] = [
      new File(['content1'], 'file1.pdf', { type: 'application/pdf' }),
      new File(['content2'], 'image.jpg', { type: 'image/jpeg' }),
    ];

    it('displays pending attachments', () => {
      render(<MessageInput {...defaultProps} pendingAttachments={mockFiles} />);

      expect(screen.getByText('file1.pdf')).toBeInTheDocument();
      expect(screen.getByText('image.jpg')).toBeInTheDocument();
    });

    it('calls onAttachmentRemove when clicking remove button', () => {
      const onAttachmentRemove = jest.fn();
      render(
        <MessageInput
          {...defaultProps}
          pendingAttachments={mockFiles}
          onAttachmentRemove={onAttachmentRemove}
        />
      );

      const removeButtons = screen.getAllByRole('button', { name: /remove attachment/i });
      fireEvent.click(removeButtons[0]!);

      expect(onAttachmentRemove).toHaveBeenCalledWith(0);
    });
  });

  describe('archived view', () => {
    it('shows read-only message for archived', () => {
      render(<MessageInput {...defaultProps} messageDisplay="archived" />);

      expect(screen.getByText('Archived messages are read-only.')).toBeInTheDocument();
    });

    it('does not render input elements', () => {
      render(<MessageInput {...defaultProps} messageDisplay="archived" />);

      expect(screen.queryByPlaceholderText('Type your message...')).not.toBeInTheDocument();
    });
  });

  describe('trash view', () => {
    it('shows read-only message for trash', () => {
      render(<MessageInput {...defaultProps} messageDisplay="trash" />);

      expect(screen.getByText('Trashed messages are read-only.')).toBeInTheDocument();
    });
  });

  describe('no upcoming bookings', () => {
    it('shows view-only message when no upcoming bookings', () => {
      render(<MessageInput {...defaultProps} hasUpcomingBookings={false} />);

      expect(screen.getByText('This lesson has ended. Chat is view-only.')).toBeInTheDocument();
    });

    it('does not render input when no upcoming bookings', () => {
      render(<MessageInput {...defaultProps} hasUpcomingBookings={false} />);

      expect(screen.queryByPlaceholderText('Type your message...')).not.toBeInTheDocument();
    });
  });
});
