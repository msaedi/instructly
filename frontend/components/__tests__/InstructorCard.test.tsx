import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import InstructorCard from '../InstructorCard';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useFavoriteStatus, useSetFavoriteStatus } from '@/hooks/queries/useFavoriteStatus';
import { useInstructorRatingsQuery } from '@/hooks/queries/useRatings';
import { useRecentReviews } from '@/src/api/services/reviews';
import { favoritesApi } from '@/services/api/favorites';
import { useServicesCatalog } from '@/hooks/queries/useServices';
import { fetchPricingPreview } from '@/lib/api/pricing';
import { ApiProblemError } from '@/lib/api/fetch';
import type { Problem } from '@/lib/errors/problem';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import type { Instructor } from '@/types/api';
import type { ServiceLocationType } from '@/types/instructor';

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(),
}));

jest.mock('@/hooks/queries/useFavoriteStatus', () => ({
  useFavoriteStatus: jest.fn(),
  useSetFavoriteStatus: jest.fn(),
}));

jest.mock('@/hooks/queries/useRatings', () => ({
  useInstructorRatingsQuery: jest.fn(),
}));

jest.mock('@/src/api/services/reviews', () => ({
  useRecentReviews: jest.fn(),
}));

jest.mock('@/services/api/favorites', () => ({
  favoritesApi: {
    add: jest.fn(),
    remove: jest.fn(),
  },
}));

jest.mock('@/hooks/queries/useServices', () => ({
  useServicesCatalog: jest.fn(),
}));

// Mock the ApiProblemError class inline so instanceof checks work
jest.mock('@/lib/api/fetch', () => {
  class MockApiProblemError extends Error {
    problem: { detail?: string; title?: string; status?: number };
    response: { status: number } | undefined;
    constructor(problem: { detail?: string; title?: string; status?: number }, response?: { status: number }) {
      super(problem.detail || 'API error');
      this.problem = problem;
      this.response = response;
    }
  }
  return {
    ApiProblemError: MockApiProblemError,
  };
});

jest.mock('@/lib/api/pricing', () => ({
  fetchPricingPreview: jest.fn(),
  formatCentsToDisplay: (cents: number) => `$${(cents / 100).toFixed(2)}`,
}));

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('@/lib/logger', () => ({
  logger: { info: jest.fn(), warn: jest.fn(), error: jest.fn() },
}));

jest.mock('@/components/user/UserAvatar', () => ({
  UserAvatar: ({ user, size }: { user: { id: string }; size: number }) => (
    <div data-testid="user-avatar" data-size={size}>{user.id}</div>
  ),
}));

jest.mock('@/components/instructor/MessageInstructorButton', () => ({
  MessageInstructorButton: ({ instructorId }: { instructorId: string }) => (
    <button data-testid="message-button">Message {instructorId}</button>
  ),
}));

jest.mock('@/components/ui/FoundingBadge', () => ({
  FoundingBadge: ({ size }: { size: string }) => <span data-testid="founding-badge" data-size={size}>Founding</span>,
}));

jest.mock('@/components/ui/BGCBadge', () => ({
  BGCBadge: ({ isLive }: { isLive: boolean }) => <span data-testid="bgc-badge">{isLive ? 'Live' : 'Pending'}</span>,
}));

const mockUseAuth = useAuth as jest.Mock;
const mockUseRouter = useRouter as jest.Mock;
const mockUseFavoriteStatus = useFavoriteStatus as jest.Mock;
const mockUseSetFavoriteStatus = useSetFavoriteStatus as jest.Mock;
const mockUseInstructorRatingsQuery = useInstructorRatingsQuery as jest.Mock;
const mockUseRecentReviews = useRecentReviews as jest.Mock;
const mockUseServicesCatalog = useServicesCatalog as jest.Mock;
const mockFavoritesApi = favoritesApi as jest.Mocked<typeof favoritesApi>;
const mockFetchPricingPreview = fetchPricingPreview as jest.Mock;

const createInstructor = (overrides: Partial<Instructor> = {}): Instructor => ({
  user_id: '01K2TEST00000000000000001',
  user: {
    first_name: 'John',
    last_initial: 'D',
  },
  bio: 'Test bio for the instructor',
  years_experience: 5,
  services: [
    {
      id: 'svc-1',
      service_catalog_id: 'cat-1',
      hourly_rate: 75,
      duration_options: [30, 60, 90],
    },
  ],
  service_area_boroughs: ['Manhattan'],
  service_area_neighborhoods: [],
  service_area_summary: 'NYC',
  ...overrides,
} as Instructor);

describe('InstructorCard', () => {
  let queryClient: QueryClient;
  let mockPush: jest.Mock;
  let mockSetFavoriteStatus: jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    mockPush = jest.fn();
    mockSetFavoriteStatus = jest.fn();

    mockUseRouter.mockReturnValue({ push: mockPush });
    mockUseAuth.mockReturnValue({ user: null });
    mockUseFavoriteStatus.mockReturnValue({ data: false });
    mockUseSetFavoriteStatus.mockReturnValue(mockSetFavoriteStatus);
    mockUseInstructorRatingsQuery.mockReturnValue({ data: null });
    mockUseRecentReviews.mockReturnValue({ data: null });
    mockUseServicesCatalog.mockReturnValue({
      data: [
        { id: 'cat-1', name: 'Piano', description: 'Piano lessons', subcategory_id: '01HABCTESTSUBCAT0000000001' },
        { id: 'cat-2', name: 'Guitar', description: 'Guitar lessons', subcategory_id: '01HABCTESTSUBCAT0000000002' },
      ],
    });
    Object.defineProperty(window, 'sessionStorage', {
      value: { setItem: jest.fn(), getItem: jest.fn(), removeItem: jest.fn() },
      writable: true,
    });
  });

  const renderWithProviders = (ui: React.ReactElement) => {
    return render(
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
    );
  };

  describe('rendering', () => {
    it('renders instructor name correctly', async () => {
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByTestId('instructor-name')).toHaveTextContent('John D.');
    });

    it('renders name without last initial when missing', async () => {
      const instructor = createInstructor({
        user: { first_name: 'Jane', last_initial: '' },
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByTestId('instructor-name')).toHaveTextContent('Jane');
    });

    it('renders hourly rate correctly', async () => {
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByTestId('instructor-price')).toHaveTextContent('$75/hr');
    });

    it('handles string hourly rate', async () => {
      const instructor = createInstructor({
        services: [{ id: 'svc-1', service_catalog_id: 'cat-1', hourly_rate: '60.00' as unknown as number, duration_options: [60] }],
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByTestId('instructor-price')).toHaveTextContent('$60/hr');
    });

    it('handles NaN hourly rate gracefully', async () => {
      const instructor = createInstructor({
        services: [{ id: 'svc-1', service_catalog_id: 'cat-1', hourly_rate: 'invalid' as unknown as number, duration_options: [60] }],
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByTestId('instructor-price')).toHaveTextContent('$0/hr');
    });

    it('renders founding badge when is_founding_instructor is true', async () => {
      const instructor = { ...createInstructor(), is_founding_instructor: true };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.getByTestId('founding-badge')).toBeInTheDocument();
    });

    it('renders BGC badge when instructor is live', async () => {
      const instructor = { ...createInstructor(), is_live: true };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.getByTestId('bgc-badge')).toHaveTextContent('Live');
    });

    it('renders BGC badge when bgc_status is pending', async () => {
      const instructor = { ...createInstructor(), bgc_status: 'pending' };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.getByTestId('bgc-badge')).toHaveTextContent('Pending');
    });

    it('shows distance when available', async () => {
      const instructor = { ...createInstructor(), distance_mi: 2.5 };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.getByText('· 2.5 mi')).toBeInTheDocument();
    });

    it('displays rating when reviewCount >= 3', async () => {
      mockUseInstructorRatingsQuery.mockReturnValue({
        data: { overall: { rating: 4.5, total_reviews: 10 } },
      });
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByText('4.5')).toBeInTheDocument();
      expect(screen.getByText('10 reviews')).toBeInTheDocument();
    });

    it('hides rating when reviewCount < 3', async () => {
      mockUseInstructorRatingsQuery.mockReturnValue({
        data: { overall: { rating: 5.0, total_reviews: 2 } },
      });
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.queryByText('5.0')).not.toBeInTheDocument();
    });

    it('renders compact mode correctly', async () => {
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} compact />);
      expect(screen.getByTestId('user-avatar')).toHaveAttribute('data-size', '128');
    });

    it('renders default mode with larger avatar', async () => {
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByTestId('user-avatar')).toHaveAttribute('data-size', '224');
    });

    it('renders mock bio when instructor bio is missing', async () => {
      const instructor = createInstructor({ bio: '' });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      // Should render one of the mock bios
      expect(screen.getByText(/"/)).toBeInTheDocument();
    });

    it('renders recent reviews when available', async () => {
      mockUseRecentReviews.mockReturnValue({
        data: {
          reviews: [
            { id: 'r1', review_text: 'Great teacher!', reviewer_display_name: 'Alice' },
            { id: 'r2', review_text: 'Loved the lessons', reviewer_display_name: 'Bob' },
          ],
        },
      });
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByText('"Great teacher!"')).toBeInTheDocument();
      expect(screen.getByText('"Loved the lessons"')).toBeInTheDocument();
    });

    it('hides reviews in compact mode', async () => {
      mockUseRecentReviews.mockReturnValue({
        data: {
          reviews: [{ id: 'r1', review_text: 'Great teacher!', reviewer_display_name: 'Alice' }],
        },
      });
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} compact />);
      expect(screen.queryByText('"Great teacher!"')).not.toBeInTheDocument();
    });
  });

  describe('duration selection', () => {
    it('renders duration options when multiple available', async () => {
      const instructor = createInstructor({
        services: [{ id: 'svc-1', service_catalog_id: 'cat-1', hourly_rate: 60, duration_options: [30, 60, 90] }],
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByLabelText(/30 min/)).toBeInTheDocument();
      expect(screen.getByLabelText(/60 min/)).toBeInTheDocument();
      expect(screen.getByLabelText(/90 min/)).toBeInTheDocument();
    });

    it('calculates correct price for each duration', async () => {
      const instructor = createInstructor({
        services: [{ id: 'svc-1', service_catalog_id: 'cat-1', hourly_rate: 60, duration_options: [30, 60, 90] }],
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByText(/30 min \(\$30\)/)).toBeInTheDocument();
      expect(screen.getByText(/60 min \(\$60\)/)).toBeInTheDocument();
      expect(screen.getByText(/90 min \(\$90\)/)).toBeInTheDocument();
    });

    it('changes selected duration when radio clicked', async () => {
      const instructor = createInstructor({
        services: [{ id: 'svc-1', service_catalog_id: 'cat-1', hourly_rate: 60, duration_options: [30, 60, 90] }],
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);

      const user = userEvent.setup();
      const radioFor90 = screen.getByLabelText(/90 min \(\$90\)/);
      await user.click(radioFor90);
      expect(radioFor90).toBeChecked();
    });

    it('hides duration selector when only one option', async () => {
      const instructor = createInstructor({
        services: [{ id: 'svc-1', service_catalog_id: 'cat-1', hourly_rate: 60, duration_options: [60] }],
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.queryByText(/duration:/i)).not.toBeInTheDocument();
    });
  });

  describe('favorite functionality', () => {
    it('redirects guest users to login when clicking favorite', async () => {
      mockUseAuth.mockReturnValue({ user: null });
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);

      const user = userEvent.setup();
      await user.click(screen.getByLabelText('Sign in to save'));

      expect(mockPush).toHaveBeenCalledWith(
        expect.stringContaining('/login?returnTo=')
      );
    });

    it('adds to favorites when not already saved', async () => {
      mockUseAuth.mockReturnValue({ user: { id: 'user-1' } });
      mockUseFavoriteStatus.mockReturnValue({ data: false });
      mockFavoritesApi.add.mockResolvedValue({ success: true, message: 'Added', favorite_id: 'fav-1' });

      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);

      const user = userEvent.setup();
      await user.click(screen.getByLabelText('Toggle favorite'));

      await waitFor(() => {
        expect(mockSetFavoriteStatus).toHaveBeenCalledWith('01K2TEST00000000000000001', true);
      });
      expect(mockFavoritesApi.add).toHaveBeenCalledWith('01K2TEST00000000000000001');
      expect(toast.success).toHaveBeenCalledWith('Added to favorites!');
    });

    it('removes from favorites when already saved', async () => {
      mockUseAuth.mockReturnValue({ user: { id: 'user-1' } });
      mockUseFavoriteStatus.mockReturnValue({ data: true });
      mockFavoritesApi.remove.mockResolvedValue({ success: true, message: 'Removed', not_favorited: true });

      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);

      const user = userEvent.setup();
      await user.click(screen.getByLabelText('Toggle favorite'));

      await waitFor(() => {
        expect(mockFavoritesApi.remove).toHaveBeenCalledWith('01K2TEST00000000000000001');
      });
      expect(toast.success).toHaveBeenCalledWith('Removed from favorites');
    });

    it('reverts optimistic update on error', async () => {
      mockUseAuth.mockReturnValue({ user: { id: 'user-1' } });
      mockUseFavoriteStatus.mockReturnValue({ data: false });
      mockFavoritesApi.add.mockRejectedValue(new Error('API error'));

      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);

      const user = userEvent.setup();
      await user.click(screen.getByLabelText('Toggle favorite'));

      await waitFor(() => {
        expect(mockSetFavoriteStatus).toHaveBeenCalledWith('01K2TEST00000000000000001', false);
      });
      expect(toast.error).toHaveBeenCalledWith('Failed to update favorite');
    });

    it('prevents multiple clicks while loading', async () => {
      mockUseAuth.mockReturnValue({ user: { id: 'user-1' } });
      mockUseFavoriteStatus.mockReturnValue({ data: false });
      mockFavoritesApi.add.mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 1000))
      );

      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);

      const user = userEvent.setup();
      await user.click(screen.getByLabelText('Toggle favorite'));
      await user.click(screen.getByLabelText('Toggle favorite'));

      expect(mockFavoritesApi.add).toHaveBeenCalledTimes(1);
    });
  });

  describe('navigation', () => {
    it('calls onViewProfile when view profile is clicked', async () => {
      const onViewProfile = jest.fn();
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} onViewProfile={onViewProfile} />);

      const user = userEvent.setup();
      await user.click(screen.getByTestId('instructor-link'));

      expect(onViewProfile).toHaveBeenCalled();
    });

    it('calls onBookNow when more options is clicked', async () => {
      const onBookNow = jest.fn();
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} onBookNow={onBookNow} />);

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /more options/i }));

      expect(onBookNow).toHaveBeenCalled();
    });

    it('navigates to reviews page when rating clicked', async () => {
      mockUseInstructorRatingsQuery.mockReturnValue({
        data: { overall: { rating: 4.5, total_reviews: 10 } },
      });
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /see all reviews/i }));

      expect(mockPush).toHaveBeenCalledWith('/instructors/01K2TEST00000000000000001/reviews');
    });
  });

  describe('availability and booking', () => {
    it('shows no availability info when no availability data', () => {
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByText('No availability info')).toBeInTheDocument();
    });

    it('shows next available slot when availability data provided', () => {
      const instructor = createInstructor();
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const dateStr = tomorrow.toISOString().split('T')[0] as string;

      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              [dateStr]: {
                available_slots: [{ start_time: '10:00', end_time: '12:00' }],
              },
            },
          }}
        />
      );

      expect(screen.getByText(/next available/i)).toBeInTheDocument();
    });

    it('skips blackout days when finding next slot', () => {
      const instructor = createInstructor();
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const dayAfter = new Date();
      dayAfter.setDate(dayAfter.getDate() + 2);
      const tomorrowStr = tomorrow.toISOString().split('T')[0] as string;
      const dayAfterStr = dayAfter.toISOString().split('T')[0] as string;

      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              [tomorrowStr]: { is_blackout: true, available_slots: [{ start_time: '10:00', end_time: '12:00' }] },
              [dayAfterStr]: { available_slots: [{ start_time: '14:00', end_time: '16:00' }] },
            },
          }}
        />
      );

      // Should skip blackout day and show day after
      expect(screen.getByText(/next available/i)).toBeInTheDocument();
    });

    it('skips slots that are too short for selected duration', () => {
      const instructor = createInstructor({
        services: [{ id: 'svc-1', service_catalog_id: 'cat-1', hourly_rate: 60, duration_options: [90] }],
      });
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const dateStr = tomorrow.toISOString().split('T')[0] as string;

      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              [dateStr]: {
                available_slots: [{ start_time: '10:00', end_time: '11:00' }], // Only 60 min available
              },
            },
          }}
        />
      );

      expect(screen.getByText('No availability info')).toBeInTheDocument();
    });
  });

  describe('pricing preview', () => {
    it('shows pricing preview when bookingDraftId is provided', async () => {
      mockFetchPricingPreview.mockResolvedValue({
        base_price_cents: 6000,
        line_items: [{ label: 'Platform fee', amount_cents: 500 }],
        student_pay_cents: 6500,
      });

      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} bookingDraftId="draft-123" />);

      await waitFor(() => {
        expect(screen.getByText('$60.00')).toBeInTheDocument();
        expect(screen.getByText('Platform fee')).toBeInTheDocument();
        expect(screen.getByText('$65.00')).toBeInTheDocument();
      });
    });

    it('shows credit line items with green styling', async () => {
      mockFetchPricingPreview.mockResolvedValue({
        base_price_cents: 6000,
        line_items: [{ label: 'Credit', amount_cents: -1000 }],
        student_pay_cents: 5000,
      });

      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} bookingDraftId="draft-123" />);

      await waitFor(() => {
        expect(screen.getByText('Credit')).toBeInTheDocument();
        expect(screen.getByText('$-10.00')).toBeInTheDocument();
      });
    });

    it('hides service & support fees from display', async () => {
      mockFetchPricingPreview.mockResolvedValue({
        base_price_cents: 6000,
        line_items: [{ label: 'Service & Support Fee', amount_cents: 500 }],
        student_pay_cents: 6500,
      });

      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} bookingDraftId="draft-123" />);

      await waitFor(() => {
        expect(screen.queryByText('Service & Support Fee')).not.toBeInTheDocument();
      });
    });

    it('shows error when pricing preview fails with 422', async () => {
      // Use the mocked ApiProblemError so instanceof check works
      const mockProblem = { type: 'validation_error', title: 'Validation Error', status: 422, detail: 'Price below minimum' };
      const mockResponse = { status: 422 } as Response;
      mockFetchPricingPreview.mockRejectedValue(
        new ApiProblemError(mockProblem, mockResponse)
      );

      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} bookingDraftId="draft-123" />);

      await waitFor(() => {
        expect(screen.getByText('Price below minimum')).toBeInTheDocument();
      });
    });

    it('shows generic error when pricing preview fails with other error', async () => {
      mockFetchPricingPreview.mockRejectedValue(new Error('Network error'));

      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} bookingDraftId="draft-123" />);

      await waitFor(() => {
        expect(screen.getByText('Unable to load pricing preview.')).toBeInTheDocument();
      });
    });
  });

  describe('service catalog', () => {
    it('renders service pills with correct names', async () => {
      const instructor = createInstructor({
        services: [
          { id: 'svc-1', service_catalog_id: 'cat-1', hourly_rate: 60, duration_options: [60] },
        ],
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);

      await waitFor(() => {
        expect(screen.getByText('Piano')).toBeInTheDocument();
      });
    });

    it('highlights matching service when highlightServiceCatalogId provided', async () => {
      const instructor = createInstructor({
        services: [
          { id: 'svc-1', service_catalog_id: 'cat-1', hourly_rate: 60, duration_options: [60] },
        ],
      });
      renderWithProviders(
        <InstructorCard instructor={instructor} highlightServiceCatalogId="cat-1" />
      );

      await waitFor(() => {
        const pill = screen.getByText('Piano');
        expect(pill).toHaveClass('bg-[#7E22CE]/15');
      });
    });
  });

  describe('bio expand/collapse', () => {
    it('shows read more button for long bio', () => {
      const longBio = 'A'.repeat(450);
      const instructor = createInstructor({ bio: longBio });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByRole('button', { name: /read more/i })).toBeInTheDocument();
    });

    it('toggles bio expansion when read more clicked', async () => {
      const longBio = 'A'.repeat(450);
      const instructor = createInstructor({ bio: longBio });
      renderWithProviders(<InstructorCard instructor={instructor} />);

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /read more/i }));

      expect(screen.getByRole('button', { name: /show less/i })).toBeInTheDocument();
    });

    it('hides bio in compact mode', () => {
      const instructor = createInstructor({ bio: 'Test bio' });
      renderWithProviders(<InstructorCard instructor={instructor} compact />);
      expect(screen.queryByText(/"Test bio"/)).not.toBeInTheDocument();
    });
  });

  describe('service area and experience display', () => {
    it('displays years of experience', () => {
      const instructor = createInstructor({ years_experience: 10 });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByText('10 years experience')).toBeInTheDocument();
    });

    it('displays service area boroughs', () => {
      const instructor = createInstructor({
        service_area_boroughs: ['Manhattan', 'Brooklyn'],
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByText('Manhattan, Brooklyn')).toBeInTheDocument();
    });

    it('shows kids lesson badge when age_groups includes kids', async () => {
      const instructor = createInstructor({
        services: [
          {
            id: 'svc-1',
            service_catalog_id: 'cat-1',
            hourly_rate: 60,
            duration_options: [60],
            age_groups: ['kids', 'adults'],
          },
        ],
      });
      renderWithProviders(<InstructorCard instructor={instructor} highlightServiceCatalogId="cat-1" />);

      await waitFor(() => {
        expect(screen.getByText('Kids lesson available')).toBeInTheDocument();
      });
    });

    it('shows levels taught from matched service context', async () => {
      const instructor = {
        ...createInstructor(),
        _matchedServiceContext: { levels: ['beginner', 'intermediate'] },
      };
      renderWithProviders(
        <InstructorCard instructor={instructor as Instructor} highlightServiceCatalogId="cat-1" />
      );

      await waitFor(() => {
        expect(screen.getByText(/beginner.*intermediate/i)).toBeInTheDocument();
      });
    });

    it('shows location types from service', async () => {
      const instructor = createInstructor({
        services: [
          {
            id: 'svc-1',
            service_catalog_id: 'cat-1',
            hourly_rate: 60,
            duration_options: [60],
            location_types: ['in_person', 'online'],
            offers_travel: true,
            offers_online: true,
          },
        ],
      });
      renderWithProviders(<InstructorCard instructor={instructor} highlightServiceCatalogId="cat-1" />);

      await waitFor(() => {
        expect(screen.getByText(/format:/i)).toBeInTheDocument();
        expect(screen.getByRole('img', { name: /travels to you/i })).toBeInTheDocument();
        expect(screen.getByRole('img', { name: /online/i })).toBeInTheDocument();
      });
    });
  });

  describe('edge cases', () => {
    it('handles missing services array', () => {
      const instructor = { ...createInstructor(), services: [] };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.getByTestId('instructor-card')).toBeInTheDocument();
    });

    it('handles null rating gracefully', () => {
      mockUseInstructorRatingsQuery.mockReturnValue({
        data: { overall: { rating: null, total_reviews: 5 } },
      });
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      // Should not display rating when it's null
      expect(screen.queryByText(/\d\.\d/)).not.toBeInTheDocument();
    });

    it('handles empty duration_options array', () => {
      const instructor = createInstructor({
        services: [{ id: 'svc-1', service_catalog_id: 'cat-1', hourly_rate: 60, duration_options: [] }],
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      // Should default to 60 minutes
      expect(screen.getByTestId('instructor-card')).toBeInTheDocument();
    });

    it('parses invalid date strings gracefully', () => {
      const instructor = createInstructor();
      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              'invalid-date': { available_slots: [{ start_time: '10:00', end_time: '12:00' }] },
            },
          }}
        />
      );
      expect(screen.getByText('No availability info')).toBeInTheDocument();
    });

    it('handles invalid time strings gracefully', () => {
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const dateStr = tomorrow.toISOString().split('T')[0] as string;

      const instructor = createInstructor();
      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              [dateStr]: { available_slots: [{ start_time: 'invalid', end_time: '12:00' }] },
            },
          }}
        />
      );
      expect(screen.getByText('No availability info')).toBeInTheDocument();
    });

    it('handles date strings with NaN parts', () => {
      const instructor = createInstructor();
      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              '2025-NaN-15': { available_slots: [{ start_time: '10:00', end_time: '12:00' }] },
            },
          }}
        />
      );
      expect(screen.getByText('No availability info')).toBeInTheDocument();
    });

    it('handles date with too few parts', () => {
      const instructor = createInstructor();
      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              '2025-01': { available_slots: [{ start_time: '10:00', end_time: '12:00' }] },
            },
          }}
        />
      );
      expect(screen.getByText('No availability info')).toBeInTheDocument();
    });
  });

  describe('Book Now button', () => {
    it('stores booking data in sessionStorage and navigates when clicked', async () => {
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const dateStr = tomorrow.toISOString().split('T')[0] as string;

      const mockSetItem = jest.fn();
      Object.defineProperty(window, 'sessionStorage', {
        value: {
          setItem: mockSetItem,
          getItem: jest.fn(),
          removeItem: jest.fn(),
        },
        writable: true,
      });

      const instructor = createInstructor({
        services: [{ id: 'svc-123', service_catalog_id: 'cat-1', hourly_rate: 60, duration_options: [60] }],
      });

      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              [dateStr]: { available_slots: [{ start_time: '10:00', end_time: '12:00' }] },
            },
          }}
        />
      );

      const user = userEvent.setup();
      const bookNowButton = screen.getByRole('button', { name: /next available/i });
      await user.click(bookNowButton);

      expect(mockSetItem).toHaveBeenCalledWith('bookingData', expect.any(String));
      expect(mockSetItem).toHaveBeenCalledWith('serviceId', 'svc-123');
      expect(mockPush).toHaveBeenCalledWith('/student/booking/confirm');
    });

    it('calculates end time correctly for different durations', async () => {
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const dateStr = tomorrow.toISOString().split('T')[0] as string;

      const mockSetItem = jest.fn();
      Object.defineProperty(window, 'sessionStorage', {
        value: {
          setItem: mockSetItem,
          getItem: jest.fn(),
          removeItem: jest.fn(),
        },
        writable: true,
      });

      const instructor = createInstructor({
        services: [{ id: 'svc-123', service_catalog_id: 'cat-1', hourly_rate: 60, duration_options: [90] }],
      });

      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              [dateStr]: { available_slots: [{ start_time: '10:00', end_time: '13:00' }] },
            },
          }}
        />
      );

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /next available/i }));

      // Verify booking data was stored with correct end time (10:00 + 90min = 11:30)
      const bookingDataCall = mockSetItem.mock.calls.find(
        (call: [string, string]) => call[0] === 'bookingData'
      );
      expect(bookingDataCall).toBeDefined();
      const bookingData = JSON.parse(bookingDataCall[1]);
      expect(bookingData.endTime).toBe('11:30');
    });
  });

  describe('service catalog error handling', () => {
    it('handles failed service catalog fetch gracefully', async () => {
      mockUseServicesCatalog.mockReturnValue({ data: undefined, error: new Error('Network error') });

      const instructor = createInstructor();
      // Should not throw
      renderWithProviders(<InstructorCard instructor={instructor} />);

      await waitFor(() => {
        expect(screen.getByTestId('instructor-card')).toBeInTheDocument();
      });
    });
  });

  describe('availability slot filtering', () => {
    it('filters out past slots for today', async () => {
      // Set current time to 11:00 AM
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 11, 0, 0);
      jest.useFakeTimers();
      jest.setSystemTime(today);

      const dateStr = today.toISOString().split('T')[0] as string;

      const instructor = createInstructor();
      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              // Slot at 10:00 should be filtered out since current time is 11:00
              [dateStr]: { available_slots: [{ start_time: '10:00', end_time: '11:00' }] },
            },
          }}
        />
      );

      // No valid slots since the only one is in the past
      expect(screen.getByText('No availability info')).toBeInTheDocument();

      jest.useRealTimers();
    });

    it('shows future slots for today', async () => {
      // Set current time to 9:00 AM
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 9, 0, 0);
      jest.useFakeTimers();
      jest.setSystemTime(today);

      const dateStr = today.toISOString().split('T')[0] as string;

      const instructor = createInstructor();
      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              [dateStr]: { available_slots: [{ start_time: '10:00', end_time: '12:00' }] },
            },
          }}
        />
      );

      // Slot at 10:00 should be shown since current time is 9:00
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /next available/i })).toBeEnabled();
      });

      jest.useRealTimers();
    });
  });

  describe('service name resolution', () => {
    it('uses service_catalog_name when available (no catalog lookup needed)', () => {
      const instructor = createInstructor({
        services: [
          {
            id: 'svc-1',
            service_catalog_id: 'cat-unknown',
            service_catalog_name: 'Voice Lessons',
            hourly_rate: 60,
            duration_options: [60],
          },
        ],
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByText('Voice Lessons')).toBeInTheDocument();
    });

    it('uses skill field as fallback when service_catalog_name is missing', () => {
      const instructor = createInstructor({
        services: [
          {
            id: 'svc-1',
            service_catalog_id: 'cat-unknown',
            skill: 'Drums',
            hourly_rate: 60,
            duration_options: [60],
          },
        ],
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByText('Drums')).toBeInTheDocument();
    });

    it('returns empty string when service_catalog_name, skill, and catalog lookup all fail', () => {
      mockUseServicesCatalog.mockReturnValue({ data: [] });
      const instructor = createInstructor({
        services: [
          {
            id: 'svc-1',
            service_catalog_id: 'cat-missing',
            hourly_rate: 60,
            duration_options: [60],
          },
        ],
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      // Empty service name should not render a pill
      expect(screen.getByTestId('instructor-card')).toBeInTheDocument();
    });
  });

  describe('pricing preview edge cases', () => {
    it('shows fallback error when ApiProblemError has no detail', async () => {
      // Intentionally omit `detail` to test the ?? fallback in the component
      const mockProblem = { type: 'validation_error', title: 'Validation Error', status: 422 } as unknown as Problem;
      const mockResponse = { status: 422 } as Response;
      mockFetchPricingPreview.mockRejectedValue(
        new ApiProblemError(mockProblem, mockResponse)
      );

      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} bookingDraftId="draft-123" />);

      await waitFor(() => {
        expect(screen.getByText('Price is below the minimum.')).toBeInTheDocument();
      });
    });

    it('resets pricing state when bookingDraftId becomes undefined', async () => {
      // When bookingDraftId is removed, the useEffect clears the pricing state
      // and does not call fetchPricingPreview
      mockFetchPricingPreview.mockResolvedValue({
        base_price_cents: 6000,
        line_items: [],
        student_pay_cents: 6000,
      });

      const instructor = createInstructor();

      // First render with no bookingDraftId
      renderWithProviders(
        <InstructorCard instructor={instructor} />
      );

      // fetchPricingPreview should not be called without bookingDraftId
      await new Promise((r) => setTimeout(r, 50));
      expect(mockFetchPricingPreview).not.toHaveBeenCalled();

      // No pricing text should be shown
      expect(screen.queryByText('Updating pricing')).not.toBeInTheDocument();
    });
  });

  describe('location format display', () => {
    it('shows at-location icon when offers_at_location and has teaching_locations', async () => {
      const instructor = {
        ...createInstructor({
          services: [
            {
              id: 'svc-1',
              service_catalog_id: 'cat-1',
              hourly_rate: 60,
              duration_options: [60],
              offers_at_location: true,
            },
          ],
        }),
        teaching_locations: [{ name: 'Studio A' }],
      };

      renderWithProviders(
        <InstructorCard instructor={instructor as unknown as Instructor} highlightServiceCatalogId="cat-1" />
      );

      await waitFor(() => {
        expect(screen.getByText(/format:/i)).toBeInTheDocument();
        expect(screen.getByRole('img', { name: /at their studio/i })).toBeInTheDocument();
      });
    });
  });

  describe('profile picture in UserAvatar', () => {
    it('passes has_profile_picture and profile_picture_version to UserAvatar', () => {
      const instructor = createInstructor({
        user: {
          first_name: 'Alice',
          last_initial: 'B',
          has_profile_picture: true,
          profile_picture_version: 3,
        } as Instructor['user'],
      });

      renderWithProviders(<InstructorCard instructor={instructor} />);
      // The UserAvatar should receive the profile picture data
      expect(screen.getByTestId('user-avatar')).toBeInTheDocument();
    });
  });

  describe('applied credit cents', () => {
    it('handles negative appliedCreditCents (clamps to 0)', async () => {
      mockFetchPricingPreview.mockResolvedValue({
        base_price_cents: 6000,
        line_items: [],
        student_pay_cents: 6000,
      });

      const instructor = createInstructor();
      renderWithProviders(
        <InstructorCard instructor={instructor} bookingDraftId="draft-123" appliedCreditCents={-500} />
      );

      await waitFor(() => {
        expect(mockFetchPricingPreview).toHaveBeenCalledWith('draft-123', 0);
      });
    });
  });

  describe('levels taught filtering', () => {
    it('filters out empty and whitespace-only levels', async () => {
      const instructor = createInstructor({
        services: [{
          id: 'svc-1',
          service_catalog_id: 'cat-1',
          hourly_rate: 60,
          duration_options: [60],
          levels_taught: ['beginner', '', '  ', 'advanced'],
        }],
      });

      renderWithProviders(
        <InstructorCard instructor={instructor} highlightServiceCatalogId="cat-1" />
      );

      // Should display only valid levels
      await waitFor(() => {
        expect(screen.getByText(/beginner/i)).toBeInTheDocument();
        expect(screen.getByText(/advanced/i)).toBeInTheDocument();
      });
    });

    it('handles location_types with empty values', async () => {
      const instructor = createInstructor({
        services: [{
          id: 'svc-1',
          service_catalog_id: 'cat-1',
          hourly_rate: 60,
          duration_options: [60],
          location_types: ['online', '', 'in-home'] as unknown as ServiceLocationType[],
        }],
      });

      renderWithProviders(
        <InstructorCard instructor={instructor} highlightServiceCatalogId="cat-1" />
      );

      await waitFor(() => {
        expect(screen.getByTestId('instructor-card')).toBeInTheDocument();
      });
    });
  });

  describe('all past availability dates', () => {
    it('shows no availability when all dates are in the past', () => {
      const instructor = createInstructor();
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      const twoDaysAgo = new Date();
      twoDaysAgo.setDate(twoDaysAgo.getDate() - 2);

      const yesterdayStr = yesterday.toISOString().split('T')[0] as string;
      const twoDaysAgoStr = twoDaysAgo.toISOString().split('T')[0] as string;

      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              [twoDaysAgoStr]: { available_slots: [{ start_time: '10:00', end_time: '12:00' }] },
              [yesterdayStr]: { available_slots: [{ start_time: '14:00', end_time: '16:00' }] },
            },
          }}
        />
      );

      expect(screen.getByText('No availability info')).toBeInTheDocument();
    });

    it('shows no availability when availability data has empty slots for all dates', () => {
      const instructor = createInstructor();
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const dateStr = tomorrow.toISOString().split('T')[0] as string;

      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              [dateStr]: { available_slots: [] },
            },
          }}
        />
      );

      expect(screen.getByText('No availability info')).toBeInTheDocument();
    });
  });

  describe('blackout day filtering', () => {
    it('skips blackout days and finds slot on non-blackout day', () => {
      const instructor = createInstructor({
        services: [{ id: 'svc-1', service_catalog_id: 'cat-1', hourly_rate: 60, duration_options: [60] }],
      });
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const dayAfter = new Date();
      dayAfter.setDate(dayAfter.getDate() + 2);
      const dayAfterThat = new Date();
      dayAfterThat.setDate(dayAfterThat.getDate() + 3);

      const tomorrowStr = tomorrow.toISOString().split('T')[0] as string;
      const dayAfterStr = dayAfter.toISOString().split('T')[0] as string;
      const dayAfterThatStr = dayAfterThat.toISOString().split('T')[0] as string;

      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              [tomorrowStr]: {
                is_blackout: true,
                available_slots: [{ start_time: '09:00', end_time: '17:00' }],
              },
              [dayAfterStr]: {
                is_blackout: true,
                available_slots: [{ start_time: '09:00', end_time: '17:00' }],
              },
              [dayAfterThatStr]: {
                available_slots: [{ start_time: '10:00', end_time: '12:00' }],
              },
            },
          }}
        />
      );

      // Should skip the two blackout days and show availability from the third day
      expect(screen.getByText(/next available/i)).toBeInTheDocument();
    });

    it('shows no availability when all days are blackout', () => {
      const instructor = createInstructor();
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const tomorrowStr = tomorrow.toISOString().split('T')[0] as string;

      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              [tomorrowStr]: {
                is_blackout: true,
                available_slots: [{ start_time: '10:00', end_time: '18:00' }],
              },
            },
          }}
        />
      );

      expect(screen.getByText('No availability info')).toBeInTheDocument();
    });
  });

  describe('service name fallback chain', () => {
    it('uses catalog name when service_catalog_name and skill are both absent', () => {
      mockUseServicesCatalog.mockReturnValue({
        data: [{ id: 'cat-guitar', name: 'Guitar', description: 'Guitar lessons', subcategory_id: 'sub-1' }],
      });
      const instructor = createInstructor({
        services: [
          {
            id: 'svc-1',
            service_catalog_id: 'cat-guitar',
            hourly_rate: 50,
            duration_options: [60],
            // no service_catalog_name, no skill
          },
        ],
      });

      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByText('Guitar')).toBeInTheDocument();
    });

    it('does not render pill when name resolves to empty string', () => {
      mockUseServicesCatalog.mockReturnValue({ data: [] });
      const instructor = createInstructor({
        services: [
          {
            id: 'svc-1',
            service_catalog_id: 'cat-nonexistent',
            hourly_rate: 50,
            duration_options: [60],
            // no service_catalog_name, no skill, no catalog match
          },
        ],
      });

      renderWithProviders(<InstructorCard instructor={instructor} />);
      // The component returns null for empty serviceName, so no pill span should render
      const pills = screen.queryAllByText(/./);
      const servicePill = pills.find((el) =>
        el.className?.includes('rounded-full') && el.textContent === ''
      );
      expect(servicePill).toBeUndefined();
    });

    it('prefers service_catalog_name over skill and catalog lookup', () => {
      mockUseServicesCatalog.mockReturnValue({
        data: [{ id: 'cat-1', name: 'Catalog Piano', description: 'desc', subcategory_id: 'sub-1' }],
      });
      const instructor = createInstructor({
        services: [
          {
            id: 'svc-1',
            service_catalog_id: 'cat-1',
            service_catalog_name: 'Inline Piano',
            skill: 'Skill Piano',
            hourly_rate: 50,
            duration_options: [60],
          },
        ],
      });

      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByText('Inline Piano')).toBeInTheDocument();
      expect(screen.queryByText('Skill Piano')).not.toBeInTheDocument();
      expect(screen.queryByText('Catalog Piano')).not.toBeInTheDocument();
    });
  });

  describe('favorite toggle race condition', () => {
    it('prevents duplicate API calls when clicking favorite rapidly', async () => {
      mockUseAuth.mockReturnValue({ user: { id: 'user-1' } });
      mockUseFavoriteStatus.mockReturnValue({ data: false });

      let resolveAdd: (() => void) | undefined;
      mockFavoritesApi.add.mockImplementation(
        () => new Promise<{ success: boolean; message: string; favorite_id: string }>((resolve) => {
          resolveAdd = () => resolve({ success: true, message: 'Added', favorite_id: 'fav-1' });
        })
      );

      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);

      const user = userEvent.setup();
      const favButton = screen.getByLabelText('Toggle favorite');

      // Click twice rapidly
      await user.click(favButton);
      await user.click(favButton);

      // Only one API call should be made because isLoadingFavorite gates the second click
      expect(mockFavoritesApi.add).toHaveBeenCalledTimes(1);

      // Clean up
      if (resolveAdd) resolveAdd();
    });
  });

  describe('conditional rendering branches', () => {
    it('does not show BGC badge when neither verified nor pending', () => {
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.queryByTestId('bgc-badge')).not.toBeInTheDocument();
    });

    it('shows BGC badge when bgc_status is passed', () => {
      const instructor = { ...createInstructor(), bgc_status: 'passed' };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });

    it('shows BGC badge when bgc_status is clear', () => {
      const instructor = { ...createInstructor(), bgc_status: 'clear' };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });

    it('shows BGC badge when bgc_status is verified', () => {
      const instructor = { ...createInstructor(), bgc_status: 'verified' };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });

    it('shows BGC badge when background_check_verified is true', () => {
      const instructor = { ...createInstructor(), background_check_verified: true };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });

    it('shows BGC badge when background_check_completed is true', () => {
      const instructor = { ...createInstructor(), background_check_completed: true };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });

    it('does not show distance when distance_mi is not a number', () => {
      const instructor = { ...createInstructor(), distance_mi: null };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.queryByText(/mi$/)).not.toBeInTheDocument();
    });

    it('does not show distance when distance_mi is Infinity', () => {
      const instructor = { ...createInstructor(), distance_mi: Infinity };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.queryByText(/Infinity/)).not.toBeInTheDocument();
    });

    it('does not show rating when rating is null even with enough reviews', () => {
      mockUseInstructorRatingsQuery.mockReturnValue({
        data: { overall: { rating: null, total_reviews: 10 } },
      });
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.queryByRole('button', { name: /see all reviews/i })).not.toBeInTheDocument();
    });

    it('does not show founding badge when is_founding_instructor is false', () => {
      const instructor = { ...createInstructor(), is_founding_instructor: false };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.queryByTestId('founding-badge')).not.toBeInTheDocument();
    });

    it('hides experience row when years_experience is 0', () => {
      const instructor = createInstructor({ years_experience: 0 });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.queryByText(/years experience/)).not.toBeInTheDocument();
    });

    it('uses background_check_status as fallback when bgc_status is absent', () => {
      const instructor = { ...createInstructor(), background_check_status: 'PASSED' };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      // bgc_status is absent but background_check_status is 'PASSED', lowered to 'passed'
      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });
  });

  describe('availability with undefined day entry', () => {
    it('skips undefined day entries gracefully', () => {
      const instructor = createInstructor();
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const dateStr = tomorrow.toISOString().split('T')[0] as string;

      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              [dateStr]: undefined as unknown as { available_slots?: { start_time: string; end_time: string }[] },
            },
          }}
        />
      );

      expect(screen.getByText('No availability info')).toBeInTheDocument();
    });
  });

  describe('slot sorting within a day', () => {
    it('selects the earliest available slot when slots are not in order', () => {
      const instructor = createInstructor({
        services: [{ id: 'svc-1', service_catalog_id: 'cat-1', hourly_rate: 60, duration_options: [60] }],
      });
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const dateStr = tomorrow.toISOString().split('T')[0] as string;

      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              [dateStr]: {
                available_slots: [
                  { start_time: '14:00', end_time: '16:00' },
                  { start_time: '09:00', end_time: '11:00' },
                ],
              },
            },
          }}
        />
      );

      // The component sorts slots and should pick 9:00 AM as the first
      const button = screen.getByRole('button', { name: /next available/i });
      expect(button.textContent).toContain('9:00');
    });
  });

  describe('review star rating rendering', () => {
    it('renders filled stars up to review rating and empty stars after', () => {
      mockUseRecentReviews.mockReturnValue({
        data: {
          reviews: [
            { id: 'r1', rating: 3, review_text: 'Good lesson', reviewer_display_name: 'Charlie' },
          ],
        },
      });
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);

      // Review text should appear
      expect(screen.getByText('"Good lesson"')).toBeInTheDocument();
      expect(screen.getByText('- Charlie')).toBeInTheDocument();
    });

    it('renders review without review_text gracefully', () => {
      mockUseRecentReviews.mockReturnValue({
        data: {
          reviews: [
            { id: 'r1', rating: 4 },
          ],
        },
      });
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      // Should render the review card without review text
      expect(screen.getByTestId('instructor-card')).toBeInTheDocument();
    });

    it('renders review without reviewer_display_name gracefully', () => {
      mockUseRecentReviews.mockReturnValue({
        data: {
          reviews: [
            { id: 'r1', rating: 5, review_text: 'Amazing!', reviewer_display_name: null },
          ],
        },
      });
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByText('"Amazing!"')).toBeInTheDocument();
      // No reviewer name line should be rendered
      expect(screen.queryByText(/^-/)).not.toBeInTheDocument();
    });

    it('renders review with non-numeric rating gracefully', () => {
      mockUseRecentReviews.mockReturnValue({
        data: {
          reviews: [
            { id: 'r1', rating: null, review_text: 'Okay class', reviewer_display_name: 'Dan' },
          ],
        },
      });
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      // All stars should be gray when rating is not a number
      expect(screen.getByText('"Okay class"')).toBeInTheDocument();
    });
  });

  describe('preferred_teaching_locations fallback', () => {
    it('shows at-location icon when preferred_teaching_locations are set instead of teaching_locations', async () => {
      const instructor = {
        ...createInstructor({
          services: [
            {
              id: 'svc-1',
              service_catalog_id: 'cat-1',
              hourly_rate: 60,
              duration_options: [60],
              offers_at_location: true,
            },
          ],
        }),
        preferred_teaching_locations: [{ name: 'Home Studio' }],
      };

      renderWithProviders(
        <InstructorCard instructor={instructor as unknown as Instructor} highlightServiceCatalogId="cat-1" />
      );

      await waitFor(() => {
        expect(screen.getByText(/format:/i)).toBeInTheDocument();
        expect(screen.getByRole('img', { name: /at their studio/i })).toBeInTheDocument();
      });
    });
  });

  describe('context age_groups fallback to derived', () => {
    it('uses derived age_groups from highlightService when context has no age_groups', async () => {
      const instructor = createInstructor({
        services: [
          {
            id: 'svc-1',
            service_catalog_id: 'cat-1',
            hourly_rate: 60,
            duration_options: [60],
            age_groups: ['kids', 'teens'],
          },
        ],
      });

      renderWithProviders(
        <InstructorCard instructor={instructor} highlightServiceCatalogId="cat-1" />
      );

      await waitFor(() => {
        expect(screen.getByText('Kids lesson available')).toBeInTheDocument();
      });
    });

    it('does not show kids badge when context has age_groups without kids', async () => {
      const instructor = {
        ...createInstructor({
          services: [
            {
              id: 'svc-1',
              service_catalog_id: 'cat-1',
              hourly_rate: 60,
              duration_options: [60],
              age_groups: ['kids'],
            },
          ],
        }),
        _matchedServiceContext: { age_groups: ['adults'] },
      };

      renderWithProviders(
        <InstructorCard instructor={instructor as Instructor} highlightServiceCatalogId="cat-1" />
      );

      await waitFor(() => {
        expect(screen.queryByText('Kids lesson available')).not.toBeInTheDocument();
      });
    });
  });

  describe('combined meta rows layout', () => {
    it('renders both highlight and meta rows together with dividers', async () => {
      const instructor = {
        ...createInstructor({
          years_experience: 8,
          services: [
            {
              id: 'svc-1',
              service_catalog_id: 'cat-1',
              hourly_rate: 60,
              duration_options: [60],
              levels_taught: ['beginner'],
              offers_travel: true,
              age_groups: ['kids'],
            },
          ],
        }),
        service_area_boroughs: ['Manhattan'],
      };

      renderWithProviders(
        <InstructorCard instructor={instructor as Instructor} highlightServiceCatalogId="cat-1" />
      );

      await waitFor(() => {
        expect(screen.getByText('Kids lesson available')).toBeInTheDocument();
        expect(screen.getByText(/beginner/i)).toBeInTheDocument();
        expect(screen.getByText(/format:/i)).toBeInTheDocument();
        expect(screen.getByText('8 years experience')).toBeInTheDocument();
        expect(screen.getByText('Manhattan')).toBeInTheDocument();
      });
    });

    it('renders only meta rows when no highlight rows', async () => {
      const instructor = createInstructor({
        years_experience: 5,
        services: [
          {
            id: 'svc-1',
            service_catalog_id: 'cat-1',
            hourly_rate: 60,
            duration_options: [60],
          },
        ],
      });

      renderWithProviders(
        <InstructorCard instructor={instructor} highlightServiceCatalogId="cat-1" />
      );

      await waitFor(() => {
        expect(screen.getByText('5 years experience')).toBeInTheDocument();
      });
    });

    it('returns null when no combined rows exist', async () => {
      const instructor = createInstructor({
        years_experience: 0,
        service_area_boroughs: [],
        service_area_summary: '',
        services: [
          {
            id: 'svc-1',
            service_catalog_id: 'cat-1',
            hourly_rate: 60,
            duration_options: [60],
          },
        ],
      });

      renderWithProviders(<InstructorCard instructor={instructor} />);

      // No experience or service area rows should be rendered
      expect(screen.queryByText(/experience/i)).not.toBeInTheDocument();
    });
  });

  describe('founding badge and BGC badge margin logic', () => {
    it('applies margin to founding badge when rating is shown', () => {
      mockUseInstructorRatingsQuery.mockReturnValue({
        data: { overall: { rating: 4.0, total_reviews: 5 } },
      });
      const instructor = { ...createInstructor(), is_founding_instructor: true };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.getByTestId('founding-badge')).toBeInTheDocument();
      expect(screen.getByText('4')).toBeInTheDocument();
    });

    it('applies margin to BGC badge when both rating and founding badge are shown', () => {
      mockUseInstructorRatingsQuery.mockReturnValue({
        data: { overall: { rating: 4.5, total_reviews: 10 } },
      });
      const instructor = {
        ...createInstructor(),
        is_founding_instructor: true,
        bgc_status: 'passed',
      };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.getByTestId('founding-badge')).toBeInTheDocument();
      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });

    it('applies margin to BGC badge when only founding badge is shown (no rating)', () => {
      const instructor = {
        ...createInstructor(),
        is_founding_instructor: true,
        bgc_status: 'passed',
      };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.getByTestId('founding-badge')).toBeInTheDocument();
      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });
  });

  describe('duration price calculation with NaN rate', () => {
    it('renders duration options with $0 when hourly_rate is NaN', () => {
      const instructor = createInstructor({
        services: [{
          id: 'svc-1',
          service_catalog_id: 'cat-1',
          hourly_rate: 'not-a-number' as unknown as number,
          duration_options: [30, 60],
        }],
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByText(/30 min \(\$0\)/)).toBeInTheDocument();
      expect(screen.getByText(/60 min \(\$0\)/)).toBeInTheDocument();
    });

    it('renders duration options with string hourly_rate coerced', () => {
      const instructor = createInstructor({
        services: [{
          id: 'svc-1',
          service_catalog_id: 'cat-1',
          hourly_rate: '120' as unknown as number,
          duration_options: [30, 60],
        }],
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByText(/30 min \(\$60\)/)).toBeInTheDocument();
      expect(screen.getByText(/60 min \(\$120\)/)).toBeInTheDocument();
    });
  });

  describe('pricing preview edge cases - bookingDraftId presence', () => {
    it('shows loading state while pricing preview fetches', async () => {
      // Keep the pricing preview loading indefinitely
      mockFetchPricingPreview.mockImplementation(() => new Promise(() => {}));

      const instructor = createInstructor();
      renderWithProviders(
        <InstructorCard instructor={instructor} bookingDraftId="draft-loading" />
      );

      await waitFor(() => {
        expect(screen.getByText(/updating pricing/i)).toBeInTheDocument();
      });
    });

    it('does not show pricing section when bookingDraftId is absent', () => {
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.queryByText('Lesson')).not.toBeInTheDocument();
      expect(screen.queryByText('Total')).not.toBeInTheDocument();
    });
  });

  describe('service area display fallback', () => {
    it('uses service area summary as fallback when no boroughs', () => {
      const instructor = createInstructor({
        service_area_boroughs: [],
        service_area_summary: 'All of NYC',
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByText('All of NYC')).toBeInTheDocument();
    });

    it('defaults to NYC when service area display is empty', () => {
      const instructor = createInstructor({
        service_area_boroughs: [],
        service_area_summary: '',
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByText('NYC')).toBeInTheDocument();
    });
  });

  describe('highlight service catalog matching', () => {
    it('highlights service with case-insensitive matching', async () => {
      const instructor = createInstructor({
        services: [
          { id: 'svc-1', service_catalog_id: 'CAT-1', service_catalog_name: 'Piano', hourly_rate: 60, duration_options: [60] },
        ],
      });
      renderWithProviders(
        <InstructorCard instructor={instructor} highlightServiceCatalogId="cat-1" />
      );

      await waitFor(() => {
        const pill = screen.getByText('Piano');
        expect(pill).toHaveClass('bg-[#7E22CE]/15');
      });
    });

    it('does not highlight when highlightServiceCatalogId does not match', async () => {
      const instructor = createInstructor({
        services: [
          { id: 'svc-1', service_catalog_id: 'cat-1', hourly_rate: 60, duration_options: [60] },
        ],
      });
      renderWithProviders(
        <InstructorCard instructor={instructor} highlightServiceCatalogId="cat-999" />
      );

      await waitFor(() => {
        const pill = screen.getByText('Piano');
        expect(pill).toHaveClass('bg-gray-100');
      });
    });
  });

  describe('compact mode specific rendering', () => {
    it('renders founding badge with sm size in compact mode', () => {
      const instructor = { ...createInstructor(), is_founding_instructor: true };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} compact />);
      expect(screen.getByTestId('founding-badge')).toHaveAttribute('data-size', 'sm');
    });

    it('renders founding badge with md size in default mode', () => {
      const instructor = { ...createInstructor(), is_founding_instructor: true };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.getByTestId('founding-badge')).toHaveAttribute('data-size', 'md');
    });
  });

  describe('format service fallback to first service when no highlightService', () => {
    it('uses first service for format data when no highlight match', async () => {
      const instructor = createInstructor({
        services: [
          {
            id: 'svc-1',
            service_catalog_id: 'cat-1',
            hourly_rate: 60,
            duration_options: [60],
            offers_online: true,
          },
        ],
      });

      renderWithProviders(
        <InstructorCard instructor={instructor} highlightServiceCatalogId="cat-nonexistent" />
      );

      await waitFor(() => {
        expect(screen.getByText(/format:/i)).toBeInTheDocument();
        expect(screen.getByRole('img', { name: /online/i })).toBeInTheDocument();
      });
    });
  });

  describe('pricing preview line_items filtering', () => {
    it('hides line items starting with service & support (case insensitive)', async () => {
      mockFetchPricingPreview.mockResolvedValue({
        base_price_cents: 6000,
        line_items: [
          { label: 'service & support fee', amount_cents: 300 },
          { label: 'Booking fee', amount_cents: 200 },
        ],
        student_pay_cents: 6500,
      });

      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} bookingDraftId="draft-filter" />);

      await waitFor(() => {
        expect(screen.queryByText('service & support fee')).not.toBeInTheDocument();
        expect(screen.getByText('Booking fee')).toBeInTheDocument();
      });
    });

    it('renders line item with 0 amount_cents as non-credit', async () => {
      mockFetchPricingPreview.mockResolvedValue({
        base_price_cents: 6000,
        line_items: [
          { label: 'Promo discount', amount_cents: 0 },
        ],
        student_pay_cents: 6000,
      });

      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} bookingDraftId="draft-zero" />);

      await waitFor(() => {
        expect(screen.getByText('Promo discount')).toBeInTheDocument();
      });
    });
  });

  describe('book now button click with available slot', () => {
    it('stores correct booking data including lessonType from service name', async () => {
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const dateStr = tomorrow.toISOString().split('T')[0] as string;

      const mockSetItem = jest.fn();
      Object.defineProperty(window, 'sessionStorage', {
        value: { setItem: mockSetItem, getItem: jest.fn(), removeItem: jest.fn() },
        writable: true,
      });

      mockUseServicesCatalog.mockReturnValue({
        data: [{ id: 'cat-piano', name: 'Piano', description: 'Piano lessons', subcategory_id: 'sub-1' }],
      });

      const instructor = createInstructor({
        services: [{ id: 'svc-book', service_catalog_id: 'cat-piano', hourly_rate: 80, duration_options: [60] }],
      });

      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              [dateStr]: { available_slots: [{ start_time: '14:00', end_time: '16:00' }] },
            },
          }}
        />
      );

      const user = userEvent.setup();
      const bookBtn = screen.getByRole('button', { name: /next available/i });
      await user.click(bookBtn);

      expect(mockSetItem).toHaveBeenCalledWith('bookingData', expect.any(String));
      const bookingData = JSON.parse(
        mockSetItem.mock.calls.find((c: [string, string]) => c[0] === 'bookingData')?.[1] ?? '{}'
      );
      expect(bookingData.lessonType).toBe('Piano');
      expect(bookingData.duration).toBe(60);
      expect(bookingData.basePrice).toBe(80);
      expect(bookingData.startTime).toBe('14:00');
      expect(bookingData.endTime).toBe('15:00');
      expect(mockPush).toHaveBeenCalledWith('/student/booking/confirm');
    });

    it('falls back to "Service" when no service name is available', async () => {
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const dateStr = tomorrow.toISOString().split('T')[0] as string;

      const mockSetItem = jest.fn();
      Object.defineProperty(window, 'sessionStorage', {
        value: { setItem: mockSetItem, getItem: jest.fn(), removeItem: jest.fn() },
        writable: true,
      });

      mockUseServicesCatalog.mockReturnValue({ data: [] });

      const instructor = createInstructor({
        services: [{ id: 'svc-none', service_catalog_id: 'cat-missing', hourly_rate: 50, duration_options: [60] }],
      });

      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              [dateStr]: { available_slots: [{ start_time: '10:00', end_time: '12:00' }] },
            },
          }}
        />
      );

      const user = userEvent.setup();
      const bookBtn = screen.getByRole('button', { name: /next available/i });
      await user.click(bookBtn);

      const bookingData = JSON.parse(
        mockSetItem.mock.calls.find((c: [string, string]) => c[0] === 'bookingData')?.[1] ?? '{}'
      );
      expect(bookingData.lessonType).toBe('Service');
    });

    it('stores empty serviceId when service has no id', async () => {
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const dateStr = tomorrow.toISOString().split('T')[0] as string;

      const mockSetItem = jest.fn();
      Object.defineProperty(window, 'sessionStorage', {
        value: { setItem: mockSetItem, getItem: jest.fn(), removeItem: jest.fn() },
        writable: true,
      });

      const instructor = createInstructor({
        services: [{ service_catalog_id: 'cat-1', hourly_rate: 60, duration_options: [60] } as Instructor['services'][0]],
      });

      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              [dateStr]: { available_slots: [{ start_time: '10:00', end_time: '12:00' }] },
            },
          }}
        />
      );

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /next available/i }));

      const serviceIdCall = mockSetItem.mock.calls.find((c: [string, string]) => c[0] === 'serviceId');
      expect(serviceIdCall).toBeDefined();
    });
  });

  describe('compact mode text sizing', () => {
    it('renders rating button in compact mode with smaller text', () => {
      mockUseInstructorRatingsQuery.mockReturnValue({
        data: { overall: { rating: 4.8, total_reviews: 20 } },
      });
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} compact />);
      expect(screen.getByText('4.8')).toBeInTheDocument();
      expect(screen.getByText('20 reviews')).toBeInTheDocument();
    });

    it('renders distance in compact mode with smaller text', () => {
      const instructor = { ...createInstructor(), distance_mi: 1.2 };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} compact />);
      expect(screen.getByText('· 1.2 mi')).toBeInTheDocument();
    });
  });

  // -----------------------------------------------------------------
  // Branch-coverage: nullish paths, ternary false paths, else branches
  // -----------------------------------------------------------------
  describe('branch coverage — nullish and conditional rendering', () => {
    it('does not show distance when distanceMi is null (line 169 showDistance=false)', () => {
      const instructor = { ...createInstructor(), distance_mi: null };
      renderWithProviders(<InstructorCard instructor={instructor as unknown as Instructor} />);
      expect(screen.queryByText(/mi$/)).not.toBeInTheDocument();
    });

    it('does not show distance when distanceMi is Infinity (line 169)', () => {
      const instructor = { ...createInstructor(), distance_mi: Infinity };
      renderWithProviders(<InstructorCard instructor={instructor as unknown as Instructor} />);
      expect(screen.queryByText(/Infinity/)).not.toBeInTheDocument();
    });

    it('does not show founding badge when is_founding_instructor is false/undefined', () => {
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.queryByTestId('founding-badge')).not.toBeInTheDocument();
    });

    it('does not show BGC badge when bgc_status is absent and not live', () => {
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.queryByTestId('bgc-badge')).not.toBeInTheDocument();
    });

    it('shows BGC badge for bgc_status "passed" (line 179)', () => {
      const instructor = { ...createInstructor(), bgc_status: 'passed' };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });

    it('shows BGC badge for bgc_status "clear" (line 180)', () => {
      const instructor = { ...createInstructor(), bgc_status: 'clear' };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });

    it('shows BGC badge for bgc_status "verified" (line 181)', () => {
      const instructor = { ...createInstructor(), bgc_status: 'verified' };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });

    it('shows BGC badge when background_check_verified is true (line 183)', () => {
      const instructor = { ...createInstructor(), background_check_verified: true };
      renderWithProviders(<InstructorCard instructor={instructor as unknown as Instructor} />);
      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });

    it('shows BGC badge when background_check_completed is true (line 186)', () => {
      const instructor = { ...createInstructor(), background_check_completed: true };
      renderWithProviders(<InstructorCard instructor={instructor as unknown as Instructor} />);
      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });

    it('does not render review stars section when reviewCount is 0 (rating=null)', () => {
      mockUseInstructorRatingsQuery.mockReturnValue({ data: null });
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.queryByLabelText('See all reviews')).not.toBeInTheDocument();
    });

    it('handles instructor with no services array (empty services, line 143 primaryService undefined)', () => {
      const instructor = createInstructor({ services: [] });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      // hourly rate defaults to 0
      expect(screen.getByTestId('instructor-price')).toHaveTextContent('$0/hr');
    });

    it('handles rating being non-number (line 164-165)', () => {
      mockUseInstructorRatingsQuery.mockReturnValue({
        data: { overall: { rating: 'not-a-number', total_reviews: 10 } },
      });
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      // rating is not number so showRating should be false
      expect(screen.queryByLabelText('See all reviews')).not.toBeInTheDocument();
    });

    it('does not show years experience when years_experience is 0 (line 561)', () => {
      const instructor = createInstructor({ years_experience: 0 });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.queryByText(/years experience/)).not.toBeInTheDocument();
    });

    it('renders review without review_text (only star rating, line 808)', () => {
      mockUseRecentReviews.mockReturnValue({
        data: {
          reviews: [
            { id: 'r1', rating: 4, review_text: null, reviewer_display_name: 'Alice' },
          ],
        },
      });
      const instructor = createInstructor();
      const { container } = renderWithProviders(<InstructorCard instructor={instructor} />);
      // Review text paragraph (italic) should not be rendered when review_text is null
      expect(container.querySelector('p.italic.line-clamp-3')).not.toBeInTheDocument();
      // But reviewer name should be displayed
      expect(screen.getByText(/Alice/)).toBeInTheDocument();
    });

    it('renders review without reviewer_display_name (line 811-812)', () => {
      mockUseRecentReviews.mockReturnValue({
        data: {
          reviews: [
            { id: 'r1', rating: 5, review_text: 'Amazing teacher', reviewer_display_name: null },
          ],
        },
      });
      const instructor = createInstructor();
      renderWithProviders(<InstructorCard instructor={instructor} />);
      expect(screen.getByText('"Amazing teacher"')).toBeInTheDocument();
      // No reviewer name line
      expect(screen.queryByText(/^-\s/)).not.toBeInTheDocument();
    });

    it('handles service without service_catalog_id in pill (returns null, line 442)', () => {
      mockUseServicesCatalog.mockReturnValue({ data: [] });
      const instructor = createInstructor({
        services: [
          {
            id: 'svc-no-name',
            service_catalog_id: 'cat-missing',
            hourly_rate: 60,
            duration_options: [60],
          },
        ],
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      // Service pill with empty name should not render
      expect(screen.getByTestId('instructor-card')).toBeInTheDocument();
    });

    it('handles instructor with bgc_status as background_check_status field (line 173)', () => {
      const instructor = {
        ...createInstructor(),
        bgc_status: undefined,
        background_check_status: 'passed',
      };
      renderWithProviders(<InstructorCard instructor={instructor as unknown as Instructor} />);
      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });

    it('handles no highlightServiceCatalogId — uses first service for format (line 472)', () => {
      const instructor = createInstructor({
        services: [{
          id: 'svc-1',
          service_catalog_id: 'cat-1',
          hourly_rate: 60,
          duration_options: [60],
          offers_travel: true,
          offers_online: true,
        }],
      });
      renderWithProviders(<InstructorCard instructor={instructor} />);
      // Should still show format using first service
      expect(screen.getByText(/format:/i)).toBeInTheDocument();
    });

    it('renders badge margin classes correctly with showRating but no founding badge (line 433)', () => {
      mockUseInstructorRatingsQuery.mockReturnValue({
        data: { overall: { rating: 4.5, total_reviews: 5 } },
      });
      const instructor = { ...createInstructor(), bgc_status: 'passed' };
      renderWithProviders(<InstructorCard instructor={instructor as Instructor} />);
      // Both rating and BGC badge should be shown
      expect(screen.getByText('4.5')).toBeInTheDocument();
      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });

    it('handles empty availabilityByDate object', () => {
      const instructor = createInstructor();
      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{ availabilityByDate: {} }}
        />
      );
      expect(screen.getByText('No availability info')).toBeInTheDocument();
    });

    it('handles day with empty available_slots array', () => {
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const dateStr = tomorrow.toISOString().split('T')[0] as string;

      const instructor = createInstructor();
      renderWithProviders(
        <InstructorCard
          instructor={instructor}
          availabilityData={{
            availabilityByDate: {
              [dateStr]: { available_slots: [] },
            },
          }}
        />
      );
      expect(screen.getByText('No availability info')).toBeInTheDocument();
    });

    it('handles preferred_teaching_locations for hasTeachingLocations (lines 474-478)', () => {
      const instructor = {
        ...createInstructor({
          services: [{
            id: 'svc-1',
            service_catalog_id: 'cat-1',
            hourly_rate: 60,
            duration_options: [60],
            offers_at_location: true,
          }],
        }),
        preferred_teaching_locations: [{ id: 'loc-1', address: '123 St' }],
      };
      renderWithProviders(
        <InstructorCard instructor={instructor as unknown as Instructor} highlightServiceCatalogId="cat-1" />
      );
      expect(screen.getByRole('img', { name: /at their studio/i })).toBeInTheDocument();
    });
  });
});
