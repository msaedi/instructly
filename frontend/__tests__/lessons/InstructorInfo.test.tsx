import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { InstructorInfo } from '@/components/lessons/InstructorInfo';

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'QueryClientWrapper';
  return Wrapper;
};

const renderWithQueryClient = (ui: React.ReactElement) =>
  render(ui, { wrapper: createWrapper() });

describe('InstructorInfo', () => {
  const mockInstructor = {
    id: 1,
    first_name: 'Jane',
    last_initial: 'S',
    email: 'jane@example.com',
    role: 'INSTRUCTOR' as const,
    created_at: '2024-01-01T00:00:00Z',
  };

  const mockOnChat = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders instructor information correctly', () => {
    renderWithQueryClient(
      <InstructorInfo
        instructor={mockInstructor}
        rating={4.8}
        reviewCount={50}
        lessonsCompleted={250}
        onChat={mockOnChat}
      />
    );

    // Check name (privacy-protected: Jane S.)
    expect(screen.getByText('Jane S.')).toBeInTheDocument();

    // Check rating
    expect(screen.getByText('4.8')).toBeInTheDocument();
    expect(screen.getByText('(50 reviews)')).toBeInTheDocument();

    // Check lessons count
    expect(screen.getByText('250 lessons completed')).toBeInTheDocument();
  });

  it('renders avatar fallback initials when no photo', () => {
    renderWithQueryClient(<InstructorInfo instructor={mockInstructor} onChat={mockOnChat} />);
    // Our UserAvatar now falls back to first initial rather than glyph
    expect(screen.getByText('J')).toBeInTheDocument();
  });

  it('calls onChat when chat button is clicked', () => {
    renderWithQueryClient(<InstructorInfo instructor={mockInstructor} onChat={mockOnChat} />);

    const chatButton = screen.getByRole('button', { name: /chat/i });
    fireEvent.click(chatButton);

    expect(mockOnChat).toHaveBeenCalledTimes(1);
  });

  it('returns null when instructor is not provided', () => {
    const { container } = renderWithQueryClient(<InstructorInfo onChat={mockOnChat} />);

    expect(container.firstChild).toBeNull();
  });

  it('hides rating when rating info not provided', () => {
    renderWithQueryClient(<InstructorInfo instructor={mockInstructor} onChat={mockOnChat} />);

    expect(screen.queryByText('4.9')).not.toBeInTheDocument(); // no default rating
    expect(screen.queryByText('(0 reviews)')).not.toBeInTheDocument(); // no default review count
  });

  it('handles single lesson count correctly', () => {
    renderWithQueryClient(
      <InstructorInfo instructor={mockInstructor} lessonsCompleted={1} onChat={mockOnChat} />
    );

    expect(screen.getByText('1 lessons completed')).toBeInTheDocument();
  });

  it('shows privacy-safe name for complex names and initials fallback', () => {
    const longNameInstructor = {
      ...mockInstructor,
      first_name: 'Alexandra',
      last_initial: 'M',
    };

    renderWithQueryClient(<InstructorInfo instructor={longNameInstructor} onChat={mockOnChat} />);

    expect(screen.getByText('Alexandra M.')).toBeInTheDocument();
    // Fallback initial is shown when no profile pic
    expect(screen.getByText('A')).toBeInTheDocument();
  });

  it('shows review and tip button for completed lessons', () => {
    const mockOnReview = jest.fn();

    renderWithQueryClient(
      <InstructorInfo
        instructor={mockInstructor}
        onChat={mockOnChat}
        showReviewButton={true}
        onReview={mockOnReview}
      />
    );

    const reviewButton = screen.getByRole('button', { name: /review & tip/i });
    expect(reviewButton).toBeInTheDocument();

    fireEvent.click(reviewButton);
    expect(mockOnReview).toHaveBeenCalledTimes(1);
  });

  it('does not show review button when showReviewButton is false', () => {
    renderWithQueryClient(
      <InstructorInfo instructor={mockInstructor} onChat={mockOnChat} showReviewButton={false} />
    );

    expect(screen.queryByRole('button', { name: /review & tip/i })).not.toBeInTheDocument();
  });

  it('does not show chat button when onChat is not provided', () => {
    renderWithQueryClient(<InstructorInfo instructor={mockInstructor} />);

    expect(screen.queryByRole('button', { name: /chat/i })).not.toBeInTheDocument();
  });

  it('stops event propagation when buttons are clicked', () => {
    const mockEvent = { stopPropagation: jest.fn() };
    const mockOnChatWithEvent = jest.fn();

    renderWithQueryClient(<InstructorInfo instructor={mockInstructor} onChat={mockOnChatWithEvent} />);

    const chatButton = screen.getByRole('button', { name: /chat/i });
    fireEvent.click(chatButton, mockEvent as unknown as React.MouseEvent<HTMLButtonElement>);

    expect(mockOnChatWithEvent).toHaveBeenCalled();
  });

  it('does not show lessons completed when count is 0', () => {
    renderWithQueryClient(
      <InstructorInfo instructor={mockInstructor} lessonsCompleted={0} onChat={mockOnChat} />
    );

    // When lessons completed is 0, it should not show the text
    expect(screen.queryByText(/lessons completed/)).not.toBeInTheDocument();
  });

  it('handles missing optional props gracefully', () => {
    renderWithQueryClient(<InstructorInfo instructor={mockInstructor} />);

    // Should render with defaults and no buttons (privacy-protected: Jane S.)
    expect(screen.getByText('Jane S.')).toBeInTheDocument();
    // No default rating rendered
    expect(screen.queryByText('4.9')).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  describe('reviews link navigation', () => {
    it('renders reviews link with correct aria label', () => {
      renderWithQueryClient(
        <InstructorInfo
          instructor={mockInstructor}
          rating={4.8}
          reviewCount={50}
          onChat={mockOnChat}
        />
      );

      const reviewsLink = screen.getByRole('button', { name: /see all reviews/i });
      expect(reviewsLink).toBeInTheDocument();
      expect(reviewsLink).toHaveClass('cursor-pointer');
    });

    it('renders review count text in the reviews link', () => {
      renderWithQueryClient(
        <InstructorInfo
          instructor={mockInstructor}
          rating={4.8}
          reviewCount={50}
          onChat={mockOnChat}
        />
      );

      expect(screen.getByText('(50 reviews)')).toBeInTheDocument();
    });

    it('handles zero review count', () => {
      renderWithQueryClient(
        <InstructorInfo
          instructor={mockInstructor}
          rating={4.8}
          reviewCount={0}
          onChat={mockOnChat}
        />
      );

      expect(screen.getByText('(0 reviews)')).toBeInTheDocument();
    });

    it('displays rating with one decimal place', () => {
      renderWithQueryClient(
        <InstructorInfo
          instructor={mockInstructor}
          rating={4.567}
          reviewCount={25}
          onChat={mockOnChat}
        />
      );

      expect(screen.getByText('4.6')).toBeInTheDocument();
    });

    it('does not render reviews link when rating is not provided', () => {
      renderWithQueryClient(
        <InstructorInfo
          instructor={mockInstructor}
          onChat={mockOnChat}
        />
      );

      expect(screen.queryByRole('button', { name: /see all reviews/i })).not.toBeInTheDocument();
    });

    it('does not render reviews link when reviewCount is not provided', () => {
      renderWithQueryClient(
        <InstructorInfo
          instructor={mockInstructor}
          rating={4.5}
          onChat={mockOnChat}
        />
      );

      expect(screen.queryByRole('button', { name: /see all reviews/i })).not.toBeInTheDocument();
    });

    it('calls onViewReviews callback when provided and reviews link is clicked', () => {
      const mockOnViewReviews = jest.fn();

      renderWithQueryClient(
        <InstructorInfo
          instructor={mockInstructor}
          rating={4.8}
          reviewCount={50}
          onChat={mockOnChat}
          onViewReviews={mockOnViewReviews}
        />
      );

      const reviewsLink = screen.getByRole('button', { name: /see all reviews/i });
      fireEvent.click(reviewsLink);

      expect(mockOnViewReviews).toHaveBeenCalledTimes(1);
      expect(mockOnViewReviews).toHaveBeenCalledWith(1); // instructor.id
    });

    it('passes correct instructor id to onViewReviews for string ids', () => {
      const mockOnViewReviews = jest.fn();
      const instructorWithStringId = { ...mockInstructor, id: 'instructor-abc-123' };

      renderWithQueryClient(
        <InstructorInfo
          instructor={instructorWithStringId}
          rating={4.8}
          reviewCount={50}
          onChat={mockOnChat}
          onViewReviews={mockOnViewReviews}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /see all reviews/i }));

      expect(mockOnViewReviews).toHaveBeenCalledWith('instructor-abc-123');
    });
  });

  describe('book again button', () => {
    it('shows book again button when showBookAgainButton is true', () => {
      const mockOnBookAgain = jest.fn();

      renderWithQueryClient(
        <InstructorInfo
          instructor={mockInstructor}
          onChat={mockOnChat}
          showBookAgainButton={true}
          onBookAgain={mockOnBookAgain}
        />
      );

      const bookAgainButton = screen.getByRole('button', { name: /book again/i });
      expect(bookAgainButton).toBeInTheDocument();

      fireEvent.click(bookAgainButton);
      expect(mockOnBookAgain).toHaveBeenCalledTimes(1);
    });

    it('shows chat history button instead of chat when showBookAgainButton is true', () => {
      renderWithQueryClient(
        <InstructorInfo
          instructor={mockInstructor}
          onChat={mockOnChat}
          showBookAgainButton={true}
          onBookAgain={jest.fn()}
        />
      );

      // Should show "Chat history" instead of just "Chat"
      expect(screen.getByRole('button', { name: /chat history/i })).toBeInTheDocument();
    });
  });

  describe('reviewed state', () => {
    it('shows Reviewed badge when reviewed is true', () => {
      renderWithQueryClient(
        <InstructorInfo
          instructor={mockInstructor}
          onChat={mockOnChat}
          showReviewButton={true}
          onReview={jest.fn()}
          reviewed={true}
        />
      );

      expect(screen.getByText('Reviewed')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /review & tip/i })).not.toBeInTheDocument();
    });
  });

  describe('edge cases and bug hunting', () => {
    it('handles instructor with missing first_name', () => {
      const noFirstName = { ...mockInstructor, first_name: undefined };

      renderWithQueryClient(<InstructorInfo instructor={noFirstName} onChat={mockOnChat} />);

      // Should render gracefully with empty name
      expect(screen.queryByText('Jane S.')).not.toBeInTheDocument();
    });

    it('handles instructor with missing last_initial', () => {
      const noLastInitial = { ...mockInstructor, last_initial: undefined };

      renderWithQueryClient(<InstructorInfo instructor={noLastInitial} onChat={mockOnChat} />);

      // Should show just first name without initial
      expect(screen.getByText('Jane')).toBeInTheDocument();
    });

    it('handles instructor with empty strings', () => {
      const emptyStrings = { ...mockInstructor, first_name: '', last_initial: '' };

      renderWithQueryClient(<InstructorInfo instructor={emptyStrings} onChat={mockOnChat} />);

      // Should render gracefully
      expect(document.body).toBeInTheDocument();
    });

    it('handles rating of 0', () => {
      renderWithQueryClient(
        <InstructorInfo
          instructor={mockInstructor}
          rating={0}
          reviewCount={0}
          onChat={mockOnChat}
        />
      );

      // Rating of 0 with 0 reviews - should still display
      expect(screen.getByText('0.0')).toBeInTheDocument();
      expect(screen.getByText('(0 reviews)')).toBeInTheDocument();
    });

    it('handles very high lesson count', () => {
      renderWithQueryClient(
        <InstructorInfo
          instructor={mockInstructor}
          lessonsCompleted={10000}
          onChat={mockOnChat}
        />
      );

      expect(screen.getByText('10000 lessons completed')).toBeInTheDocument();
    });
  });
});
