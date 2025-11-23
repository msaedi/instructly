import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useRouter, useParams } from 'next/navigation';
import LessonDetailsPage from '@/app/(auth)/student/lessons/[id]/page';
import * as myLessonsModule from '@/hooks/useMyLessons';
import * as authModule from '@/features/shared/hooks/useAuth';

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useParams: jest.fn(),
}));

// Mock the auth hook but keep named helpers (getUserInitials, getAvatarColor)
jest.mock('@/features/shared/hooks/useAuth', () => {
  const actual = jest.requireActual('@/features/shared/hooks/useAuth');
  return {
    ...actual,
    useAuth: jest.fn(() => ({
      isAuthenticated: true,
      isLoading: false,
      redirectToLogin: jest.fn(),
    })),
  };
});

// Mock the lesson hooks
jest.mock('@/hooks/useMyLessons', () => ({
  useLessonDetails: jest.fn(),
  calculateCancellationFee: jest.fn(() => 0),
}));

// Mock the API error check
jest.mock('@/lib/react-query/api', () => ({
  isApiError: jest.fn((error) => error?.status !== undefined),
}));

// Mock the modal components
jest.mock('@/components/lessons/modals/RescheduleModal', () => ({
  RescheduleModal: ({ isOpen }: { isOpen: boolean; onClose: () => void }) =>
    isOpen ? <div data-testid="reschedule-modal">Reschedule Modal</div> : null,
}));

jest.mock('@/components/lessons/modals/CancelWarningModal', () => ({
  CancelWarningModal: ({ isOpen, onReschedule }: { isOpen: boolean; onClose: () => void; onReschedule: () => void }) =>
    isOpen ? (
      <div data-testid="cancel-modal">
        Cancel Warning Modal
        <button onClick={onReschedule}>Reschedule instead</button>
      </div>
    ) : null,
}));

const createTestQueryClient = () => {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
};

const renderWithProviders = (ui: React.ReactElement) => {
  const queryClient = createTestQueryClient();
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
};

describe('LessonDetailsPage', () => {
  const mockRouter = {
    push: jest.fn(),
    back: jest.fn(),
  };

  const mockLesson = {
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
    service_area: 'Manhattan',
    service_name: 'Mathematics',
    instructor_id: 1,
    student_id: 1,
    service: { id: 1 },
    created_at: '2024-12-01T10:00:00Z',
    updated_at: '2024-12-01T10:00:00Z',
    instructor: {
      id: 1,
      first_name: 'John',
      last_initial: 'D',
      rating: 4.5,
      rating_count: 20,
      completed_lesson_count: 100,
    },
    payment_summary: {
      lesson_amount: 60,
      service_fee: 7.2,
      credit_applied: 0,
      subtotal: 67.2,
      tip_amount: 0,
      tip_paid: 0,
      total_paid: 67.2,
      tip_status: null,
    },
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue(mockRouter);
    (useParams as jest.Mock).mockReturnValue({ id: '1' });
  });

  it('renders lesson details correctly', () => {
    const useLessonDetails = myLessonsModule.useLessonDetails as jest.Mock;
    useLessonDetails.mockReturnValue({
      data: mockLesson,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<LessonDetailsPage />);

    // Check lesson title - service_name is displayed as primary title
    expect(screen.getByText('Mathematics')).toBeInTheDocument();

    // Check date and time (weekday copy changed to Wed in UI)
    const dateEls = screen.getAllByText(/Dec 25/);
    expect(dateEls.length).toBeGreaterThan(0);
    expect(screen.getByText(/2:00 PM/)).toBeInTheDocument();

    // Check price - use getAllByText since price appears multiple times
    const priceElements = screen.getAllByText(/60\.00/);
    expect(priceElements.length).toBeGreaterThan(0);

    // Check instructor (privacy-protected: John D.)
    expect(screen.getByText('John D.')).toBeInTheDocument();

    // Check location
    expect(screen.getByText('123 Main St, NYC')).toBeInTheDocument();
  });

  it('shows back button that navigates to My Lessons', () => {
    const useLessonDetails = myLessonsModule.useLessonDetails as jest.Mock;
    useLessonDetails.mockReturnValue({
      data: mockLesson,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<LessonDetailsPage />);

    const backButton = screen.getByRole('button', { name: /back to my lessons/i });
    fireEvent.click(backButton);

    // The page now includes a default tab param
    expect(mockRouter.push).toHaveBeenCalledWith('/student/lessons?tab=upcoming');
  });

  it('shows reschedule and cancel buttons for upcoming lessons', () => {
    // Mock a future date to ensure the lesson is upcoming
    const futureLesson = {
      ...mockLesson,
      booking_date: '2025-12-25',
      start_time: '14:00:00',
    };

    const useLessonDetails = myLessonsModule.useLessonDetails as jest.Mock;
    useLessonDetails.mockReturnValue({
      data: futureLesson,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<LessonDetailsPage />);

    expect(screen.getByRole('button', { name: /reschedule lesson/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancel lesson/i })).toBeInTheDocument();
  });

  it('opens reschedule modal when reschedule button is clicked', async () => {
    // Mock a future date to ensure the lesson is upcoming
    const futureLesson = {
      ...mockLesson,
      booking_date: '2025-12-25',
      start_time: '14:00:00',
    };

    const useLessonDetails = myLessonsModule.useLessonDetails as jest.Mock;
    useLessonDetails.mockReturnValue({
      data: futureLesson,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<LessonDetailsPage />);

    const rescheduleButton = screen.getByRole('button', { name: /reschedule lesson/i });
    fireEvent.click(rescheduleButton);

    await waitFor(() => {
      expect(screen.getByTestId('reschedule-modal')).toBeInTheDocument();
    });
  });

  it('opens cancel modal when cancel button is clicked', async () => {
    // Mock a future date to ensure the lesson is upcoming
    const futureLesson = {
      ...mockLesson,
      booking_date: '2025-12-25',
      start_time: '14:00:00',
    };

    const useLessonDetails = myLessonsModule.useLessonDetails as jest.Mock;
    useLessonDetails.mockReturnValue({
      data: futureLesson,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<LessonDetailsPage />);

    const cancelButton = screen.getByRole('button', { name: /cancel lesson/i });
    fireEvent.click(cancelButton);

    await waitFor(() => {
      expect(screen.getByTestId('cancel-modal')).toBeInTheDocument();
    });
  });

  it('switches from cancel to reschedule modal', async () => {
    // Mock a future date to ensure the lesson is upcoming
    const futureLesson = {
      ...mockLesson,
      booking_date: '2025-12-25',
      start_time: '14:00:00',
    };

    const useLessonDetails = myLessonsModule.useLessonDetails as jest.Mock;
    useLessonDetails.mockReturnValue({
      data: futureLesson,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<LessonDetailsPage />);

    // Open cancel modal
    const cancelButton = screen.getByRole('button', { name: /cancel lesson/i });
    fireEvent.click(cancelButton);

    await waitFor(() => {
      expect(screen.getByTestId('cancel-modal')).toBeInTheDocument();
    });

    // Click reschedule instead
    const rescheduleInsteadButton = screen.getByRole('button', { name: /reschedule instead/i });
    fireEvent.click(rescheduleInsteadButton);

    await waitFor(() => {
      expect(screen.queryByTestId('cancel-modal')).not.toBeInTheDocument();
      expect(screen.getByTestId('reschedule-modal')).toBeInTheDocument();
    });
  });

  it('shows completed lesson UI for completed lessons', () => {
    const completedLesson = {
      ...mockLesson,
      status: 'COMPLETED',
    };

    const useLessonDetails = myLessonsModule.useLessonDetails as jest.Mock;
    useLessonDetails.mockReturnValue({
      data: completedLesson,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<LessonDetailsPage />);

    // Check for completed status badge
    expect(screen.getByText('Completed')).toBeInTheDocument();

    // Check for completed lesson buttons
    expect(screen.getByRole('button', { name: /review & tip/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /chat history/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /book again/i })).toBeInTheDocument();

    // Check for receipt
    expect(screen.getByText('Receipt')).toBeInTheDocument();

    // Should not show reschedule/cancel buttons
    expect(screen.queryByRole('button', { name: /reschedule lesson/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /cancel lesson/i })).not.toBeInTheDocument();
  });

  it('navigates to instructor profile when Book Again is clicked', () => {
    const completedLesson = {
      ...mockLesson,
      status: 'COMPLETED',
    };

    const useLessonDetails = myLessonsModule.useLessonDetails as jest.Mock;
    useLessonDetails.mockReturnValue({
      data: completedLesson,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<LessonDetailsPage />);

    const bookAgainButton = screen.getByRole('button', { name: /book again/i });
    fireEvent.click(bookAgainButton);

    expect(mockRouter.push).toHaveBeenCalledWith('/instructors/1');
  });

  it('shows loading state', () => {
    const useLessonDetails = myLessonsModule.useLessonDetails as jest.Mock;
    useLessonDetails.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    });

    renderWithProviders(<LessonDetailsPage />);

    // Should show skeleton loading states
    const skeletons = document.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('shows error state when lesson not found', () => {
    const useLessonDetails = myLessonsModule.useLessonDetails as jest.Mock;
    useLessonDetails.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('Lesson not found'),
    });

    renderWithProviders(<LessonDetailsPage />);

    expect(screen.getByText('Unable to load lesson details')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /back to my lessons/i })).toBeInTheDocument();
  });

  it('redirects to login when not authenticated', () => {
    const useAuth = authModule.useAuth as jest.Mock;
    const mockRedirectToLogin = jest.fn();
    useAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      redirectToLogin: mockRedirectToLogin,
    });

    renderWithProviders(<LessonDetailsPage />);

    expect(mockRedirectToLogin).toHaveBeenCalledWith('/student/lessons/1');
  });

  it('handles 401 error by redirecting to login', () => {
    const useAuth = authModule.useAuth as jest.Mock;
    const mockRedirectToLogin = jest.fn();
    useAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      redirectToLogin: mockRedirectToLogin,
    });

    const useLessonDetails = myLessonsModule.useLessonDetails as jest.Mock;
    useLessonDetails.mockReturnValue({
      data: null,
      isLoading: false,
      error: { status: 401, message: 'Unauthorized' },
    });

    renderWithProviders(<LessonDetailsPage />);

    expect(mockRedirectToLogin).toHaveBeenCalledWith('/student/lessons/1');
  });

  it('shows lesson notes when available', () => {
    const useLessonDetails = myLessonsModule.useLessonDetails as jest.Mock;
    useLessonDetails.mockReturnValue({
      data: mockLesson,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<LessonDetailsPage />);

    expect(screen.getByText('Description')).toBeInTheDocument();
    expect(screen.getByText('Looking forward to the lesson!')).toBeInTheDocument();
  });

  it('shows receipt details for completed lessons', () => {
    const completedLesson = {
      ...mockLesson,
      status: 'COMPLETED',
      payment_summary: {
        ...mockLesson.payment_summary,
        lesson_amount: 60,
        service_fee: 7.2,
        tip_amount: 10,
        tip_paid: 10,
        total_paid: 77.2,
      },
    };

    const useLessonDetails = myLessonsModule.useLessonDetails as jest.Mock;
    useLessonDetails.mockReturnValue({
      data: completedLesson,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<LessonDetailsPage />);

    // Check receipt details
    expect(screen.getByText('Date of Lesson')).toBeInTheDocument();
    // Receipt shows combined text with currency symbol
    expect(screen.getByText(/\$?60\.00\/hr x 1 hr/)).toBeInTheDocument();
    expect(screen.getByText('Service fee')).toBeInTheDocument();
    expect(screen.getByText('$7.20')).toBeInTheDocument();
    expect(screen.getByText('Tip')).toBeInTheDocument();
    expect(screen.getByText('$10.00')).toBeInTheDocument();
    expect(screen.getByText('Total')).toBeInTheDocument();
    const totalValues = screen.getAllByText('$77.20');
    expect(totalValues.length).toBeGreaterThan(0);
  });

  it('shows receipt section for completed lessons', () => {
    const completedLesson = {
      ...mockLesson,
      status: 'COMPLETED',
    };

    const useLessonDetails = myLessonsModule.useLessonDetails as jest.Mock;
    useLessonDetails.mockReturnValue({
      data: completedLesson,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<LessonDetailsPage />);

    expect(screen.getByText('Receipt')).toBeInTheDocument();
  });
});
