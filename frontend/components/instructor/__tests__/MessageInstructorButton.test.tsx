/**
 * Tests for MessageInstructorButton component
 *
 * Phase 6: Pre-booking messaging button tests
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MessageInstructorButton } from '../MessageInstructorButton';
import type { ReactNode } from 'react';

// Mock the hooks
const mockCreateConversation = jest.fn();
const mockRedirectToLogin = jest.fn();

jest.mock('@/hooks/useCreateConversation', () => ({
  useCreateConversation: jest.fn(() => ({
    createConversation: mockCreateConversation,
    isCreating: false,
    error: null,
  })),
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(() => ({
    user: { id: 'student_123' },
    isAuthenticated: true,
    redirectToLogin: mockRedirectToLogin,
  })),
}));

// Import after mocking
import { useCreateConversation } from '@/hooks/useCreateConversation';
import { useAuth } from '@/features/shared/hooks/useAuth';

const mockUseCreateConversation = useCreateConversation as jest.Mock;
const mockUseAuth = useAuth as jest.Mock;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'TestWrapper';
  return Wrapper;
};

describe('MessageInstructorButton', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseCreateConversation.mockReturnValue({
      createConversation: mockCreateConversation,
      isCreating: false,
      error: null,
    });
    mockUseAuth.mockReturnValue({
      user: { id: 'student_123' },
      isAuthenticated: true,
      redirectToLogin: mockRedirectToLogin,
    });
  });

  it('renders message button', () => {
    render(
      <MessageInstructorButton instructorId="instructor_456" instructorName="Sarah" />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByRole('button', { name: /message sarah/i })).toBeInTheDocument();
    expect(screen.getByText('Message')).toBeInTheDocument();
  });

  it('does not render for own profile', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 'instructor_456' },
      isAuthenticated: true,
      redirectToLogin: mockRedirectToLogin,
    });

    const { container } = render(
      <MessageInstructorButton instructorId="instructor_456" instructorName="Sarah" />,
      { wrapper: createWrapper() }
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('calls createConversation when clicked by authenticated user', async () => {
    render(
      <MessageInstructorButton instructorId="instructor_456" instructorName="Sarah" />,
      { wrapper: createWrapper() }
    );

    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(mockCreateConversation).toHaveBeenCalledWith('instructor_456', {
        navigateToMessages: true,
      });
    });
  });

  it('redirects to login when not authenticated', async () => {
    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin: mockRedirectToLogin,
    });

    render(
      <MessageInstructorButton instructorId="instructor_456" instructorName="Sarah" />,
      { wrapper: createWrapper() }
    );

    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(mockRedirectToLogin).toHaveBeenCalledWith('/instructors/instructor_456');
    });
    expect(mockCreateConversation).not.toHaveBeenCalled();
  });

  it('shows loading state when creating conversation', () => {
    mockUseCreateConversation.mockReturnValue({
      createConversation: mockCreateConversation,
      isCreating: true,
      error: null,
    });

    render(
      <MessageInstructorButton instructorId="instructor_456" instructorName="Sarah" />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText('Opening...')).toBeInTheDocument();
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('renders with different variants', () => {
    const { rerender } = render(
      <MessageInstructorButton
        instructorId="instructor_456"
        instructorName="Sarah"
        variant="default"
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByRole('button')).toBeInTheDocument();

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <MessageInstructorButton
          instructorId="instructor_456"
          instructorName="Sarah"
          variant="secondary"
        />
      </QueryClientProvider>
    );

    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('renders icon-only mode', () => {
    render(
      <MessageInstructorButton
        instructorId="instructor_456"
        instructorName="Sarah"
        iconOnly
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByRole('button')).toBeInTheDocument();
    expect(screen.queryByText('Message')).not.toBeInTheDocument();
  });

  it('applies custom className', () => {
    render(
      <MessageInstructorButton
        instructorId="instructor_456"
        instructorName="Sarah"
        className="custom-class"
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByRole('button')).toHaveClass('custom-class');
  });
});
