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
      expect(screen.getByLabelText('Type a message')).toBeInTheDocument();
    });

    it('renders attachment button', () => {
      render(<MessageInput {...defaultProps} />);

      expect(screen.getByRole('button', { name: /attach file/i })).toBeInTheDocument();
    });

    it('renders send button', () => {
      render(<MessageInput {...defaultProps} />);

      const sendButton = screen.getByRole('button', { name: /send message/i });
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

      const sendButton = screen.getByRole('button', { name: /send message/i });
      fireEvent.click(sendButton);

      expect(onSend).toHaveBeenCalled();
    });

    it('disables send button when isSendDisabled is true', () => {
      render(<MessageInput {...defaultProps} isSendDisabled={true} />);

      const sendButton = screen.getByRole('button', { name: /send message/i });
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

    it('triggers file input when clicking attach button', () => {
      render(<MessageInput {...defaultProps} />);

      const attachButton = screen.getByRole('button', { name: /attach file/i });
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      const clickSpy = jest.spyOn(fileInput, 'click');

      fireEvent.click(attachButton);

      expect(clickSpy).toHaveBeenCalled();
      clickSpy.mockRestore();
    });

    it('calls onAttachmentAdd when files are selected', () => {
      const onAttachmentAdd = jest.fn();
      render(<MessageInput {...defaultProps} onAttachmentAdd={onAttachmentAdd} />);

      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      const testFile = new File(['test content'], 'test.txt', { type: 'text/plain' });

      // Create a mock FileList-like object
      const mockFileList = {
        0: testFile,
        length: 1,
        item: (index: number) => (index === 0 ? testFile : null),
      } as unknown as FileList;

      fireEvent.change(fileInput, { target: { files: mockFileList } });

      expect(onAttachmentAdd).toHaveBeenCalledWith(mockFileList);
    });

    it('clears file input value after selecting files', () => {
      const onAttachmentAdd = jest.fn();
      render(<MessageInput {...defaultProps} onAttachmentAdd={onAttachmentAdd} />);

      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      const testFile = new File(['test content'], 'test.txt', { type: 'text/plain' });

      // Create a mock FileList-like object
      const mockFileList = {
        0: testFile,
        length: 1,
        item: (index: number) => (index === 0 ? testFile : null),
      } as unknown as FileList;

      // Set value to simulate file selection
      Object.defineProperty(fileInput, 'value', {
        writable: true,
        value: 'C:\\fakepath\\test.txt',
      });

      fireEvent.change(fileInput, { target: { files: mockFileList } });

      // Value should be cleared
      expect(fileInput.value).toBe('');
    });

    it('supports multiple file selection', () => {
      render(<MessageInput {...defaultProps} />);

      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      expect(fileInput).toHaveAttribute('multiple');
      expect(fileInput).toHaveAttribute('aria-label', 'Attach file');
    });

    it('hides the file input element', () => {
      render(<MessageInput {...defaultProps} />);

      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      expect(fileInput).toHaveClass('hidden');
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

  describe('keyboard handling', () => {
    it('calls onKeyPress when pressing a key in textarea', () => {
      const onKeyPress = jest.fn();
      render(<MessageInput {...defaultProps} onKeyPress={onKeyPress} />);

      const textarea = screen.getByPlaceholderText('Type your message...');
      fireEvent.keyPress(textarea, { key: 'Enter', code: 'Enter', charCode: 13 });

      expect(onKeyPress).toHaveBeenCalled();
    });

    it('passes keyboard event to onKeyPress handler', () => {
      const onKeyPress = jest.fn();
      render(<MessageInput {...defaultProps} onKeyPress={onKeyPress} />);

      const textarea = screen.getByPlaceholderText('Type your message...');
      fireEvent.keyPress(textarea, { key: 'a', code: 'KeyA', charCode: 97 });

      expect(onKeyPress).toHaveBeenCalledWith(
        expect.objectContaining({
          key: 'a',
        })
      );
    });
  });

  describe('default props', () => {
    it('uses default hasUpcomingBookings as true', () => {
      const propsWithoutBookings: MessageInputProps = {
        messageText: '',
        pendingAttachments: [],
        isSendDisabled: false,
        typingUserName: null,
        messageDisplay: 'inbox',
        // hasUpcomingBookings intentionally omitted to test default
        onMessageChange: jest.fn(),
        onKeyPress: jest.fn(),
        onSend: jest.fn(),
        onAttachmentAdd: jest.fn(),
        onAttachmentRemove: jest.fn(),
      };

      render(<MessageInput {...propsWithoutBookings} />);

      // Should render full input since default is true
      expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
    });
  });

  describe('attachment display', () => {
    it('shows file name with title attribute', () => {
      const longFileName = 'very-long-file-name-that-might-be-truncated.pdf';
      const mockFiles = [new File(['content'], longFileName, { type: 'application/pdf' })];

      render(<MessageInput {...defaultProps} pendingAttachments={mockFiles} />);

      const fileNameElement = screen.getByText(longFileName);
      expect(fileNameElement).toHaveAttribute('title', longFileName);
    });

    it('removes second attachment when clicking its remove button', () => {
      const onAttachmentRemove = jest.fn();
      const mockFiles: File[] = [
        new File(['content1'], 'file1.pdf', { type: 'application/pdf' }),
        new File(['content2'], 'file2.pdf', { type: 'application/pdf' }),
      ];

      render(
        <MessageInput
          {...defaultProps}
          pendingAttachments={mockFiles}
          onAttachmentRemove={onAttachmentRemove}
        />
      );

      const removeButtons = screen.getAllByRole('button', { name: /remove attachment/i });
      fireEvent.click(removeButtons[1]!);

      expect(onAttachmentRemove).toHaveBeenCalledWith(1);
    });
  });
});
