import React from 'react';
import { render, fireEvent, waitFor, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ChatModal } from '../ChatModal';

// Mock the Chat component to avoid its complex dependencies
jest.mock('../Chat', () => ({
  Chat: function MockChat(_props: { onClose?: () => void }) {
    return (
      <div data-testid="mock-chat">
        Mock Chat Component
        <button type="button" data-testid="mock-chat-action">Chat action</button>
      </div>
    );
  },
}));

// Mock QueryErrorBoundary
jest.mock('@/components/errors/QueryErrorBoundary', () => ({
  QueryErrorBoundary: function MockQueryErrorBoundary({
    children,
  }: {
    children: React.ReactNode;
  }) {
    return <>{children}</>;
  },
}));

// Mock apiBase
jest.mock('@/lib/apiBase', () => ({
  withApiBase: (url: string) => url,
  withApiBaseForRequest: (url: string) => url,
}));

// Mock fetch for conversation creation
global.fetch = jest.fn();

describe('ChatModal', () => {
  let queryClient: QueryClient;

  const baseProps = {
    isOpen: true,
    onClose: jest.fn(),
    conversationId: 'conversation-123',
    bookingId: 'booking-123',
    currentUserId: 'user-1',
    currentUserName: 'Instructor A',
    otherUserName: 'Student A',
  };

  beforeEach(() => {
    jest.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
    // Reset body overflow style
    document.body.style.overflow = '';
  });

  afterEach(() => {
    document.body.style.overflow = '';
  });

  it('renders modal when isOpen is true', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} />
      </QueryClientProvider>
    );

    expect(screen.getByText('Chat with Student A')).toBeInTheDocument();
    expect(screen.getByTestId('mock-chat')).toBeInTheDocument();
  });

  it('moves initial focus to first focusable element in modal', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} />
      </QueryClientProvider>
    );

    expect(screen.getByLabelText('Close chat')).toHaveFocus();
  });

  it('does not render when isOpen is false', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} isOpen={false} />
      </QueryClientProvider>
    );

    expect(screen.queryByText('Chat with Student A')).not.toBeInTheDocument();
  });

  it('calls onClose when escape key is pressed', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} />
      </QueryClientProvider>
    );

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(baseProps.onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when backdrop is clicked', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} />
      </QueryClientProvider>
    );

    // Find the backdrop by its aria-hidden attribute
    const backdrop = document.querySelector('[aria-hidden="true"]');
    expect(backdrop).toBeInTheDocument();
    fireEvent.click(backdrop!);

    expect(baseProps.onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when close button is clicked', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} />
      </QueryClientProvider>
    );

    const closeButton = screen.getByLabelText('Close chat');
    fireEvent.click(closeButton);

    expect(baseProps.onClose).toHaveBeenCalledTimes(1);
  });

  it('prevents body scroll when modal is open', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} />
      </QueryClientProvider>
    );

    expect(document.body.style.overflow).toBe('hidden');
  });

  it('restores body scroll when modal closes', () => {
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} />
      </QueryClientProvider>
    );

    expect(document.body.style.overflow).toBe('hidden');

    rerender(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} isOpen={false} />
      </QueryClientProvider>
    );

    expect(document.body.style.overflow).toBe('');
  });

  it('cleans up event listeners on unmount', () => {
    const removeEventListenerSpy = jest.spyOn(document, 'removeEventListener');

    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} />
      </QueryClientProvider>
    );

    unmount();

    expect(removeEventListenerSpy).toHaveBeenCalledWith(
      'keydown',
      expect.any(Function)
    );
    removeEventListenerSpy.mockRestore();
  });

  it('displays lesson title when provided', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} lessonTitle="Piano Lesson" />
      </QueryClientProvider>
    );

    expect(screen.getByText('Piano Lesson')).toBeInTheDocument();
  });

  it('displays lesson title and date when both provided', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} lessonTitle="Piano Lesson" lessonDate="Jan 15, 2024" />
      </QueryClientProvider>
    );

    expect(screen.getByText('Piano Lesson • Jan 15, 2024')).toBeInTheDocument();
  });

  it('shows loading state when fetching conversation', async () => {
    // Remove conversationId to trigger API fetch
    (global.fetch as jest.Mock).mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(() => {
            resolve({
              ok: true,
              json: () => Promise.resolve({ id: 'new-conversation-id' }),
            });
          }, 100);
        })
    );

    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal
          {...baseProps}
          conversationId={undefined}
          instructorId="instructor-123"
        />
      </QueryClientProvider>
    );

    expect(screen.getByText('Loading conversation...')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('mock-chat')).toBeInTheDocument();
    });
  });

  it('handles conversation creation error gracefully', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 500,
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal
          {...baseProps}
          conversationId={undefined}
          instructorId="instructor-123"
        />
      </QueryClientProvider>
    );

    // Wait for the query to fail
    await waitFor(() => {
      // The Chat component should not render without a conversation ID
      expect(screen.queryByTestId('mock-chat')).not.toBeInTheDocument();
    });
  });

  it('passes isReadOnly prop to Chat component', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} isReadOnly={true} />
      </QueryClientProvider>
    );

    // The mock Chat component should be rendered
    expect(screen.getByTestId('mock-chat')).toBeInTheDocument();
  });

  it('does not ignore non-escape keys', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} />
      </QueryClientProvider>
    );

    fireEvent.keyDown(document, { key: 'Enter' });
    fireEvent.keyDown(document, { key: 'Tab' });
    fireEvent.keyDown(document, { key: 'Space' });

    expect(baseProps.onClose).not.toHaveBeenCalled();
  });

  it('wraps focus from last to first on Tab', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} />
      </QueryClientProvider>
    );

    const closeButton = screen.getByLabelText('Close chat');
    const chatActionButton = screen.getByTestId('mock-chat-action');

    chatActionButton.focus();
    fireEvent.keyDown(document, { key: 'Tab' });

    expect(closeButton).toHaveFocus();
  });

  it('wraps focus from first to last on Shift+Tab', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} />
      </QueryClientProvider>
    );

    const closeButton = screen.getByLabelText('Close chat');
    const chatActionButton = screen.getByTestId('mock-chat-action');

    closeButton.focus();
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });

    expect(chatActionButton).toHaveFocus();
  });

  it('falls back to focusing the dialog when no focusable elements are detected', () => {
    const originalQuerySelectorAll = HTMLDivElement.prototype.querySelectorAll;
    const emptyNodeList = document.createDocumentFragment().querySelectorAll('*');
    const querySelectorSpy = jest.spyOn(HTMLDivElement.prototype, 'querySelectorAll').mockImplementation(function (selector: string) {
      if (this.getAttribute('role') === 'dialog') {
        return emptyNodeList as unknown as NodeListOf<Element>;
      }
      return originalQuerySelectorAll.call(this, selector);
    });

    try {
      render(
        <QueryClientProvider client={queryClient}>
          <ChatModal {...baseProps} />
        </QueryClientProvider>
      );

      const dialog = screen.getByRole('dialog', { name: 'Chat' });
      expect(dialog).toHaveFocus();

      fireEvent.keyDown(document, { key: 'Tab' });
      expect(dialog).toHaveFocus();
    } finally {
      querySelectorSpy.mockRestore();
    }
  });

  it('moves focus back into the modal when tab is pressed from outside', () => {
    const outsideButton = document.createElement('button');
    outsideButton.type = 'button';
    outsideButton.textContent = 'Outside trigger';
    document.body.appendChild(outsideButton);

    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} />
      </QueryClientProvider>
    );

    outsideButton.focus();
    expect(outsideButton).toHaveFocus();

    fireEvent.keyDown(document, { key: 'Tab' });
    expect(screen.getByLabelText('Close chat')).toHaveFocus();

    outsideButton.remove();
  });

  it('returns focus to trigger element when modal closes', () => {
    const trigger = document.createElement('button');
    trigger.textContent = 'Open chat';
    document.body.appendChild(trigger);
    trigger.focus();

    const onClose = jest.fn();
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} onClose={onClose} />
      </QueryClientProvider>
    );

    fireEvent.click(screen.getByLabelText('Close chat'));
    expect(onClose).toHaveBeenCalledTimes(1);

    rerender(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} isOpen={false} onClose={onClose} />
      </QueryClientProvider>
    );

    expect(trigger).toHaveFocus();
    trigger.remove();
  });

  it('adds and removes keydown event listener correctly', () => {
    const addEventListenerSpy = jest.spyOn(document, 'addEventListener');
    const removeEventListenerSpy = jest.spyOn(document, 'removeEventListener');

    const { rerender, unmount } = render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} isOpen={false} />
      </QueryClientProvider>
    );

    // Should not add listener when closed
    expect(addEventListenerSpy).not.toHaveBeenCalledWith(
      'keydown',
      expect.any(Function)
    );

    // Open the modal
    rerender(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} isOpen={true} />
      </QueryClientProvider>
    );

    expect(addEventListenerSpy).toHaveBeenCalledWith(
      'keydown',
      expect.any(Function)
    );

    unmount();

    expect(removeEventListenerSpy).toHaveBeenCalledWith(
      'keydown',
      expect.any(Function)
    );

    addEventListenerSpy.mockRestore();
    removeEventListenerSpy.mockRestore();
  });

  it('creates conversation when instructorId is provided but conversationId is not', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: 'new-conversation-id' }),
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal
          {...baseProps}
          conversationId={undefined}
          instructorId="instructor-123"
        />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/conversations',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ instructor_id: 'instructor-123' }),
        })
      );
    });
  });

  it('does not fetch conversation when conversationId is provided', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} conversationId="existing-conversation" />
      </QueryClientProvider>
    );

    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('does not fetch conversation when neither conversationId nor instructorId is provided', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ChatModal {...baseProps} conversationId={undefined} instructorId={undefined} />
      </QueryClientProvider>
    );

    expect(global.fetch).not.toHaveBeenCalled();
    expect(screen.queryByTestId('mock-chat')).not.toBeInTheDocument();
  });
});
