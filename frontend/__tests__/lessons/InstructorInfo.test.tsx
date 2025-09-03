import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { InstructorInfo } from '@/components/lessons/InstructorInfo';

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
    render(
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
    render(<InstructorInfo instructor={mockInstructor} onChat={mockOnChat} />);
    // Our UserAvatar now falls back to first initial rather than glyph
    expect(screen.getByText('J')).toBeInTheDocument();
  });

  it('calls onChat when chat button is clicked', () => {
    render(<InstructorInfo instructor={mockInstructor} onChat={mockOnChat} />);

    const chatButton = screen.getByRole('button', { name: /chat/i });
    fireEvent.click(chatButton);

    expect(mockOnChat).toHaveBeenCalledTimes(1);
  });

  it('returns null when instructor is not provided', () => {
    const { container } = render(<InstructorInfo instructor={undefined} onChat={mockOnChat} />);

    expect(container.firstChild).toBeNull();
  });

  it('hides rating when rating info not provided', () => {
    render(<InstructorInfo instructor={mockInstructor} onChat={mockOnChat} />);

    expect(screen.queryByText('4.9')).not.toBeInTheDocument(); // no default rating
    expect(screen.queryByText('(0 reviews)')).not.toBeInTheDocument(); // no default review count
  });

  it('handles single lesson count correctly', () => {
    render(<InstructorInfo instructor={mockInstructor} lessonsCompleted={1} onChat={mockOnChat} />);

    expect(screen.getByText('1 lessons completed')).toBeInTheDocument();
  });

  it('shows privacy-safe name for complex names and initials fallback', () => {
    const longNameInstructor = {
      ...mockInstructor,
      first_name: 'Alexandra',
      last_initial: 'M',
    };

    render(<InstructorInfo instructor={longNameInstructor} onChat={mockOnChat} />);

    expect(screen.getByText('Alexandra M.')).toBeInTheDocument();
    // Fallback initial is shown when no profile pic
    expect(screen.getByText('A')).toBeInTheDocument();
  });

  it('shows review and tip button for completed lessons', () => {
    const mockOnReview = jest.fn();

    render(
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
    render(
      <InstructorInfo instructor={mockInstructor} onChat={mockOnChat} showReviewButton={false} />
    );

    expect(screen.queryByRole('button', { name: /review & tip/i })).not.toBeInTheDocument();
  });

  it('does not show chat button when onChat is not provided', () => {
    render(<InstructorInfo instructor={mockInstructor} />);

    expect(screen.queryByRole('button', { name: /chat/i })).not.toBeInTheDocument();
  });

  it('stops event propagation when buttons are clicked', () => {
    const mockEvent = { stopPropagation: jest.fn() };
    const mockOnChatWithEvent = jest.fn();

    render(<InstructorInfo instructor={mockInstructor} onChat={mockOnChatWithEvent} />);

    const chatButton = screen.getByRole('button', { name: /chat/i });
    fireEvent.click(chatButton, mockEvent as unknown as React.MouseEvent<HTMLButtonElement>);

    expect(mockOnChatWithEvent).toHaveBeenCalled();
  });

  it('does not show lessons completed when count is 0', () => {
    render(<InstructorInfo instructor={mockInstructor} lessonsCompleted={0} onChat={mockOnChat} />);

    // When lessons completed is 0, it should not show the text
    expect(screen.queryByText(/lessons completed/)).not.toBeInTheDocument();
  });

  it('handles missing optional props gracefully', () => {
    render(<InstructorInfo instructor={mockInstructor} />);

    // Should render with defaults and no buttons (privacy-protected: Jane S.)
    expect(screen.getByText('Jane S.')).toBeInTheDocument();
    // No default rating rendered
    expect(screen.queryByText('4.9')).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
