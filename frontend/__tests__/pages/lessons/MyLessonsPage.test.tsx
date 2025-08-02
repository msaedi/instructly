import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import MyLessonsPage from '@/app/(auth)/student/lessons/page';

// Mock next/navigation
const mockPush = jest.fn();
const mockBack = jest.fn();
const mockForward = jest.fn();
const mockRefresh = jest.fn();
const mockReplace = jest.fn();
const mockPrefetch = jest.fn();
const mockSearchParams = new URLSearchParams();

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    back: mockBack,
    forward: mockForward,
    refresh: mockRefresh,
    replace: mockReplace,
    prefetch: mockPrefetch,
  }),
  useSearchParams: () => mockSearchParams,
}));

// Mock the auth hook
jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(() => ({
    isAuthenticated: true,
    isLoading: false,
    redirectToLogin: jest.fn(),
  })),
}));

// Mock the lesson hooks
jest.mock('@/hooks/useMyLessons', () => ({
  useCurrentLessons: jest.fn(),
  useCompletedLessons: jest.fn(),
  formatLessonStatus: jest.fn((status) => status),
}));

// Mock the API error check
jest.mock('@/lib/react-query/api', () => ({
  isApiError: jest.fn((error) => error?.status !== undefined),
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

describe('MyLessonsPage', () => {
  const mockUpcomingLessons = {
    items: [
      {
        id: 1,
        booking_date: '2024-12-25',
        start_time: '14:00:00',
        end_time: '15:00:00',
        status: 'CONFIRMED',
        total_price: 60,
        hourly_rate: 60,
        duration_minutes: 60,
        service_name: 'Mathematics',
        instructor_id: 1,
        student_id: 1,
        service_id: 1,
        created_at: '2024-12-01T10:00:00Z',
        updated_at: '2024-12-01T10:00:00Z',
        instructor: {
          id: 1,
          full_name: 'John Doe',
        },
      },
      {
        id: 2,
        booking_date: '2024-12-26',
        start_time: '10:00:00',
        end_time: '11:00:00',
        status: 'CONFIRMED',
        total_price: 80,
        hourly_rate: 80,
        duration_minutes: 60,
        service_name: 'Physics',
        instructor_id: 2,
        student_id: 1,
        service_id: 2,
        created_at: '2024-12-01T10:00:00Z',
        updated_at: '2024-12-01T10:00:00Z',
        instructor: {
          id: 2,
          full_name: 'Jane Smith',
        },
      },
    ],
    total: 2,
    page: 1,
    per_page: 50,
    has_next: false,
    has_prev: false,
  };

  const mockHistoryLessons = {
    items: [
      {
        id: 3,
        booking_date: '2024-12-20',
        start_time: '14:00:00',
        end_time: '15:00:00',
        status: 'COMPLETED',
        total_price: 60,
        hourly_rate: 60,
        duration_minutes: 60,
        service_name: 'Mathematics',
        instructor_id: 1,
        student_id: 1,
        service_id: 1,
        created_at: '2024-12-01T10:00:00Z',
        updated_at: '2024-12-01T10:00:00Z',
        instructor: {
          id: 1,
          full_name: 'John Doe',
        },
      },
      {
        id: 4,
        booking_date: '2024-12-19',
        start_time: '10:00:00',
        end_time: '11:00:00',
        status: 'CANCELLED',
        total_price: 80,
        hourly_rate: 80,
        duration_minutes: 60,
        service_name: 'Chemistry',
        instructor_id: 2,
        student_id: 1,
        service_id: 3,
        created_at: '2024-12-01T10:00:00Z',
        updated_at: '2024-12-01T10:00:00Z',
        cancellation_reason: 'Student request',
        cancelled_at: '2024-12-18T10:00:00Z',
        instructor: {
          id: 2,
          full_name: 'Jane Smith',
        },
      },
    ],
    total: 2,
    page: 1,
    per_page: 50,
    has_next: false,
    has_prev: false,
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockPush.mockClear();
    mockBack.mockClear();
    mockForward.mockClear();
    mockRefresh.mockClear();
    mockReplace.mockClear();
    mockPrefetch.mockClear();
  });

  afterEach(() => {
    jest.clearAllMocks();

    // Reset the auth mock to authenticated state
    const { useAuth } = require('@/features/shared/hooks/useAuth');
    useAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      redirectToLogin: jest.fn(),
    });
  });

  it('renders the page with title and tabs', () => {
    const { useCurrentLessons, useCompletedLessons } = require('@/hooks/useMyLessons');
    useCurrentLessons.mockReturnValue({
      data: mockUpcomingLessons,
      isLoading: false,
      error: null,
    });
    useCompletedLessons.mockReturnValue({
      data: mockHistoryLessons,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<MyLessonsPage />);

    // "My Lessons" appears in both breadcrumb and title
    const myLessonsElements = screen.getAllByText('My Lessons');
    expect(myLessonsElements.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Upcoming')).toBeInTheDocument();
    expect(screen.getByText('History')).toBeInTheDocument();
  });

  it('shows upcoming lessons by default', () => {
    const { useCurrentLessons, useCompletedLessons } = require('@/hooks/useMyLessons');
    useCurrentLessons.mockReturnValue({
      data: mockUpcomingLessons,
      isLoading: false,
      error: null,
    });
    useCompletedLessons.mockReturnValue({
      data: mockHistoryLessons,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<MyLessonsPage />);

    expect(screen.getByText('John Doe')).toBeInTheDocument();
    expect(screen.getByText('Mathematics')).toBeInTheDocument();
    expect(screen.getByText('Jane Smith')).toBeInTheDocument();
    expect(screen.getByText('Physics')).toBeInTheDocument();
  });

  it('switches to history tab when clicked', async () => {
    const { useCurrentLessons, useCompletedLessons } = require('@/hooks/useMyLessons');
    useCurrentLessons.mockReturnValue({
      data: mockUpcomingLessons,
      isLoading: false,
      error: null,
    });
    useCompletedLessons.mockReturnValue({
      data: mockHistoryLessons,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<MyLessonsPage />);

    const historyTab = screen.getByText('History');
    fireEvent.click(historyTab);

    await waitFor(() => {
      expect(screen.getByText('Chemistry')).toBeInTheDocument();
    });
  });

  it('navigates to lesson details when card is clicked', () => {
    const { useCurrentLessons, useCompletedLessons } = require('@/hooks/useMyLessons');
    useCurrentLessons.mockReturnValue({
      data: mockUpcomingLessons,
      isLoading: false,
      error: null,
    });
    useCompletedLessons.mockReturnValue({
      data: mockHistoryLessons,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<MyLessonsPage />);

    // Click on the first lesson card
    const lessonCard = screen.getByText('Mathematics').closest('.cursor-pointer');
    fireEvent.click(lessonCard!);

    expect(mockPush).toHaveBeenCalledWith('/student/lessons/1');
  });

  it('shows loading state', () => {
    const { useCurrentLessons, useCompletedLessons } = require('@/hooks/useMyLessons');
    useCurrentLessons.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    });
    useCompletedLessons.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<MyLessonsPage />);

    // Should show skeleton loading states
    const skeletons = document.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('shows error state with retry button', () => {
    const { useCurrentLessons, useCompletedLessons } = require('@/hooks/useMyLessons');
    useCurrentLessons.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('Network error'),
    });
    useCompletedLessons.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<MyLessonsPage />);

    expect(screen.getByText('Failed to load lessons')).toBeInTheDocument();
    expect(
      screen.getByText('There was an error loading your lessons. Please try again.')
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('shows empty state for upcoming lessons', () => {
    const { useCurrentLessons, useCompletedLessons } = require('@/hooks/useMyLessons');
    useCurrentLessons.mockReturnValue({
      data: { items: [], total: 0, page: 1, per_page: 50, has_next: false, has_prev: false },
      isLoading: false,
      error: null,
    });
    useCompletedLessons.mockReturnValue({
      data: { items: [], total: 0, page: 1, per_page: 50, has_next: false, has_prev: false },
      isLoading: false,
      error: null,
    });

    renderWithProviders(<MyLessonsPage />);

    expect(screen.getByText("You don't have any upcoming lessons")).toBeInTheDocument();
    expect(screen.getByText('Ready to learn something new?')).toBeInTheDocument();
  });

  it('shows empty state for history', async () => {
    const { useCurrentLessons, useCompletedLessons } = require('@/hooks/useMyLessons');
    useCurrentLessons.mockReturnValue({
      data: { items: [], total: 0, page: 1, per_page: 50, has_next: false, has_prev: false },
      isLoading: false,
      error: null,
    });
    useCompletedLessons.mockReturnValue({
      data: { items: [], total: 0, page: 1, per_page: 50, has_next: false, has_prev: false },
      isLoading: false,
      error: null,
    });

    renderWithProviders(<MyLessonsPage />);

    const historyTab = screen.getByText('History');
    fireEvent.click(historyTab);

    await waitFor(() => {
      expect(screen.getByText('Your lesson history will appear here')).toBeInTheDocument();
      expect(
        screen.getByText('This includes completed, cancelled, and past lessons.')
      ).toBeInTheDocument();
    });
  });

  it('redirects to login when not authenticated', () => {
    const { useAuth } = require('@/features/shared/hooks/useAuth');
    const mockRedirectToLogin = jest.fn();
    useAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      redirectToLogin: mockRedirectToLogin,
    });

    renderWithProviders(<MyLessonsPage />);

    expect(mockRedirectToLogin).toHaveBeenCalledWith('/student/lessons');
  });

  it('handles 401 error by redirecting to login', () => {
    const { useAuth } = require('@/features/shared/hooks/useAuth');
    const mockRedirectToLogin = jest.fn();
    useAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      redirectToLogin: mockRedirectToLogin,
    });

    const { useCurrentLessons, useCompletedLessons } = require('@/hooks/useMyLessons');
    useCurrentLessons.mockReturnValue({
      data: null,
      isLoading: false,
      error: { status: 401, message: 'Unauthorized' },
    });
    useCompletedLessons.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<MyLessonsPage />);

    expect(mockRedirectToLogin).toHaveBeenCalledWith('/student/lessons');
  });

  it('shows loading while checking authentication', () => {
    const { useAuth } = require('@/features/shared/hooks/useAuth');
    useAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: true,
      redirectToLogin: jest.fn(),
    });

    renderWithProviders(<MyLessonsPage />);

    // Should show skeleton loading state
    const skeletons = document.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('shows correct empty state message for upcoming lessons', () => {
    const { useCurrentLessons, useCompletedLessons } = require('@/hooks/useMyLessons');
    useCurrentLessons.mockReturnValue({
      data: { items: [], total: 0, page: 1, per_page: 50, has_next: false, has_prev: false },
      isLoading: false,
      error: null,
    });
    useCompletedLessons.mockReturnValue({
      data: { items: [], total: 0, page: 1, per_page: 50, has_next: false, has_prev: false },
      isLoading: false,
      error: null,
    });

    renderWithProviders(<MyLessonsPage />);

    // Wait for the component to render
    expect(screen.getByText("You don't have any upcoming lessons")).toBeInTheDocument();
    expect(screen.getByText('Ready to learn something new?')).toBeInTheDocument();
  });

  it('maintains tab state when switching between tabs', async () => {
    const { useCurrentLessons, useCompletedLessons } = require('@/hooks/useMyLessons');
    useCurrentLessons.mockReturnValue({
      data: mockUpcomingLessons,
      isLoading: false,
      error: null,
    });
    useCompletedLessons.mockReturnValue({
      data: mockHistoryLessons,
      isLoading: false,
      error: null,
    });

    renderWithProviders(<MyLessonsPage />);

    // Check upcoming tab is active
    const upcomingTab = screen.getByText('Upcoming');
    expect(upcomingTab).toHaveClass('text-primary');
    expect(upcomingTab).toHaveClass('border-primary');

    // Switch to history
    const historyTab = screen.getByText('History');
    fireEvent.click(historyTab);

    await waitFor(() => {
      expect(historyTab).toHaveClass('text-primary');
      expect(historyTab).toHaveClass('border-primary');
      expect(upcomingTab).not.toHaveClass('text-primary');
      expect(upcomingTab).not.toHaveClass('border-primary');
    });
  });
});
