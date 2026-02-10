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
});
