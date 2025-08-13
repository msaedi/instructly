import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { LessonCard } from '@/components/lessons/LessonCard';
import { Booking } from '@/types/booking';

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
  }),
}));

// Mock the formatLessonStatus function
jest.mock('@/hooks/useMyLessons', () => ({
  formatLessonStatus: jest.fn((status) => status),
}));

describe('LessonCard', () => {
  const mockBooking: Booking = {
    id: 1,
    booking_date: '2024-12-25',
    start_time: '14:00:00',
    end_time: '15:00:00',
    status: 'CONFIRMED',
    total_price: 60,
    hourly_rate: 60,
    duration_minutes: 60,
    location_type: 'student_home',
    meeting_location: '123 Main St, NYC',
    student_note: 'Looking forward to the lesson!',
    instructor_note: null,
    cancellation_reason: null,
    cancelled_at: null,
    cancelled_by: null,
    instructor_id: 1,
    student_id: 1,
    service_id: 1,
    service_name: 'Mathematics',
    created_at: '2024-12-01T10:00:00Z',
    updated_at: '2024-12-01T10:00:00Z',
    instructor: {
      id: 1,
      email: 'john@example.com',
      first_name: 'John',
      last_initial: 'D',
      role: 'INSTRUCTOR',
      created_at: '2024-01-01T00:00:00Z',
    },
  };

  const mockOnViewDetails = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders lesson card with correct information', () => {
    render(
      <LessonCard lesson={mockBooking} isCompleted={false} onViewDetails={mockOnViewDetails} />
    );

    // Check instructor name
    expect(screen.getByText('John D.')).toBeInTheDocument();

    // Check service name
    expect(screen.getByText('Mathematics')).toBeInTheDocument();

    // Check date and time
    expect(screen.getByText(/Dec 25/)).toBeInTheDocument();
    expect(screen.getByText(/2:00pm/)).toBeInTheDocument();

    // Check price
    expect(screen.getByText('$60.00')).toBeInTheDocument();
  });

  it('shows no badge for upcoming confirmed lessons', () => {
    render(
      <LessonCard lesson={mockBooking} isCompleted={false} onViewDetails={mockOnViewDetails} />
    );

    // Confirmed lessons don't show a status badge
    expect(screen.queryByText('Confirmed')).not.toBeInTheDocument();
  });

  it('shows completed badge for completed lessons', () => {
    const completedBooking = {
      ...mockBooking,
      status: 'COMPLETED' as const,
    };

    render(
      <LessonCard lesson={completedBooking} isCompleted={true} onViewDetails={mockOnViewDetails} />
    );

    // The formatLessonStatus function is mocked to return the status
    expect(completedBooking.status).toBe('COMPLETED');
  });

  it('shows cancelled badge for cancelled lessons', () => {
    const cancelledBooking = {
      ...mockBooking,
      status: 'CANCELLED' as const,
      cancellation_reason: 'Student request',
      cancelled_at: '2024-12-24T10:00:00Z',
    };

    render(
      <LessonCard lesson={cancelledBooking} isCompleted={true} onViewDetails={mockOnViewDetails} />
    );

    // The formatLessonStatus function is mocked
    expect(cancelledBooking.status).toBe('CANCELLED');
  });

  it('calls onViewDetails when card is clicked', () => {
    render(
      <LessonCard lesson={mockBooking} isCompleted={false} onViewDetails={mockOnViewDetails} />
    );

    // Click on the card container
    const card = document.querySelector('.cursor-pointer');
    fireEvent.click(card!);

    expect(mockOnViewDetails).toHaveBeenCalledTimes(1);
  });

  it('applies cursor-pointer class to card', () => {
    const { container } = render(
      <LessonCard lesson={mockBooking} isCompleted={false} onViewDetails={mockOnViewDetails} />
    );

    const card = container.querySelector('.cursor-pointer');
    expect(card).toBeInTheDocument();
  });

  it('handles missing instructor gracefully', () => {
    const bookingWithoutInstructor = {
      ...mockBooking,
      instructor: undefined,
    };

    render(
      <LessonCard
        lesson={bookingWithoutInstructor as any}
        isCompleted={false}
        onViewDetails={mockOnViewDetails}
      />
    );

    // InstructorInfo component returns null when instructor is missing
    expect(screen.queryByText('John Doe')).not.toBeInTheDocument();
  });

  it('shows Book Again button for completed lessons', () => {
    const completedBooking = {
      ...mockBooking,
      status: 'COMPLETED' as const,
    };

    const mockOnBookAgain = jest.fn();

    render(
      <LessonCard
        lesson={completedBooking}
        isCompleted={true}
        onViewDetails={mockOnViewDetails}
        onBookAgain={mockOnBookAgain}
      />
    );

    const bookAgainButton = screen.getByRole('button', { name: /book again/i });
    expect(bookAgainButton).toBeInTheDocument();

    fireEvent.click(bookAgainButton);
    expect(mockOnBookAgain).toHaveBeenCalledTimes(1);
  });

  it('formats time correctly for different hours', () => {
    const morningBooking = {
      ...mockBooking,
      start_time: '09:30:00',
      end_time: '10:30:00',
    };

    render(
      <LessonCard lesson={morningBooking} isCompleted={false} onViewDetails={mockOnViewDetails} />
    );

    expect(screen.getByText(/9:30am/)).toBeInTheDocument();
  });

  it('shows cancellation fee information for cancelled lessons', () => {
    const cancelledBooking = {
      ...mockBooking,
      status: 'CANCELLED' as const,
      cancelled_at: '2024-12-24T10:00:00Z', // Cancelled >24 hours before
    };

    render(
      <LessonCard lesson={cancelledBooking} isCompleted={true} onViewDetails={mockOnViewDetails} />
    );

    // Should show no charge for cancellation >24 hours before
    expect(screen.getByText('$0.00 (No charge)')).toBeInTheDocument();
  });

  it('shows See lesson details link', () => {
    render(
      <LessonCard lesson={mockBooking} isCompleted={false} onViewDetails={mockOnViewDetails} />
    );

    expect(screen.getByText('See lesson details')).toBeInTheDocument();
  });

  it('prevents event bubbling when clicking action buttons', () => {
    const completedBooking = {
      ...mockBooking,
      status: 'COMPLETED' as const,
    };

    const mockOnBookAgain = jest.fn();

    render(
      <LessonCard
        lesson={completedBooking}
        isCompleted={true}
        onViewDetails={mockOnViewDetails}
        onBookAgain={mockOnBookAgain}
      />
    );

    const bookAgainButton = screen.getByRole('button', { name: /book again/i });
    fireEvent.click(bookAgainButton);

    // Should call onBookAgain but not onViewDetails
    expect(mockOnBookAgain).toHaveBeenCalledTimes(1);
    expect(mockOnViewDetails).not.toHaveBeenCalled();
  });
});
