import React from 'react';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { InstructorHeader } from '../InstructorHeader';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useInstructorRatingsQuery } from '@/hooks/queries/useRatings';
import { useFavoriteStatus, useSetFavoriteStatus } from '@/hooks/queries/useFavoriteStatus';
import { favoritesApi } from '@/services/api/favorites';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import type { InstructorProfile } from '@/types/instructor';

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(),
}));

jest.mock('@/hooks/queries/useRatings', () => ({
  useInstructorRatingsQuery: jest.fn(),
}));

jest.mock('@/hooks/queries/useFavoriteStatus', () => ({
  useFavoriteStatus: jest.fn(),
  useSetFavoriteStatus: jest.fn(),
}));

jest.mock('@/services/api/favorites', () => ({
  favoritesApi: {
    add: jest.fn(),
    remove: jest.fn(),
  },
}));

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

jest.mock('@/components/user/UserAvatar', () => ({
  UserAvatar: ({ user }: { user: { id: string } }) => (
    <div data-testid="user-avatar">{user.id}</div>
  ),
}));

jest.mock('@/components/instructor/MessageInstructorButton', () => ({
  MessageInstructorButton: ({ instructorId }: { instructorId: string }) => (
    <button data-testid="message-button">Message {instructorId}</button>
  ),
}));

jest.mock('@/components/ui/FoundingBadge', () => ({
  FoundingBadge: () => <span data-testid="founding-badge">Founding</span>,
}));

jest.mock('@/components/ui/BGCBadge', () => ({
  BGCBadge: ({ isLive }: { isLive: boolean }) => (
    <span data-testid="bgc-badge">{isLive ? 'Live' : 'Pending'}</span>
  ),
}));

const mockUseAuth = useAuth as jest.Mock;
const mockUseRouter = useRouter as jest.Mock;
const mockUseInstructorRatingsQuery = useInstructorRatingsQuery as jest.Mock;
const mockUseFavoriteStatus = useFavoriteStatus as jest.Mock;
const mockUseSetFavoriteStatus = useSetFavoriteStatus as jest.Mock;
const mockFavoritesApi = favoritesApi as jest.Mocked<typeof favoritesApi>;
const mockToast = toast as jest.Mocked<typeof toast>;

const createInstructor = (overrides: Partial<InstructorProfile> = {}): InstructorProfile => ({
  id: '01K2TEST00000000000000001',
  user_id: '01K2TEST00000000000000001',
  bio: 'Test bio for instructor',
  service_area_boroughs: ['Manhattan'],
  service_area_neighborhoods: [],
  service_area_summary: null,
  preferred_teaching_locations: [],
  preferred_public_spaces: [],
  years_experience: 5,
  user: {
    first_name: 'John',
    last_initial: 'D',
  },
  services: [],
  favorited_count: 10,
  ...overrides,
});

describe('InstructorHeader', () => {
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
    mockUseInstructorRatingsQuery.mockReturnValue({ data: null });
    mockUseFavoriteStatus.mockReturnValue({ data: false });
    mockUseSetFavoriteStatus.mockReturnValue(mockSetFavoriteStatus);
  });

  const renderWithProviders = (ui: React.ReactElement) => {
    return render(
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
    );
  };

  describe('rendering', () => {
    it('renders instructor name correctly', () => {
      const instructor = createInstructor();
      renderWithProviders(<InstructorHeader instructor={instructor} />);
      expect(screen.getByTestId('instructor-profile-name')).toHaveTextContent('John D.');
    });

    it('renders fallback name when user has no last initial', () => {
      const instructor = createInstructor({
        user: { first_name: 'Jane', last_initial: '' },
      });
      renderWithProviders(<InstructorHeader instructor={instructor} />);
      expect(screen.getByTestId('instructor-profile-name')).toHaveTextContent('Jane');
    });

    it('renders fallback when user object is missing', () => {
      const instructor = createInstructor({ user: undefined });
      renderWithProviders(<InstructorHeader instructor={instructor} />);
      expect(screen.getByTestId('instructor-profile-name')).toHaveTextContent('Instructor #01K2TEST00000000000000001');
    });

    it('renders experience when available', () => {
      const instructor = createInstructor({ years_experience: 10 });
      renderWithProviders(<InstructorHeader instructor={instructor} />);
      expect(screen.getByText('10 years experience')).toBeInTheDocument();
    });

    it('renders founding badge when is_founding_instructor is true', () => {
      const instructor = createInstructor({ is_founding_instructor: true } as InstructorProfile);
      renderWithProviders(<InstructorHeader instructor={instructor} />);
      expect(screen.getByTestId('founding-badge')).toBeInTheDocument();
    });

    it('renders BGC badge when instructor is live', () => {
      const instructor = createInstructor({ is_live: true } as InstructorProfile);
      renderWithProviders(<InstructorHeader instructor={instructor} />);
      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });

    it('renders BGC badge when bgc_status is pending', () => {
      const instructor = { ...createInstructor(), bgc_status: 'pending' } as InstructorProfile & { bgc_status: string };
      renderWithProviders(<InstructorHeader instructor={instructor} />);
      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });

    it('does not render background check cleared text for pending status', () => {
      const instructor = { ...createInstructor(), bgc_status: 'pending', is_live: false } as InstructorProfile & { bgc_status: string };
      renderWithProviders(<InstructorHeader instructor={instructor} />);
      expect(screen.queryByText('Background check cleared')).not.toBeInTheDocument();
    });

    it('renders rating and review count when available', () => {
      mockUseInstructorRatingsQuery.mockReturnValue({
        data: { overall: { rating: 4.5, total_reviews: 10 } },
      });
      const instructor = createInstructor();
      renderWithProviders(<InstructorHeader instructor={instructor} />);
      expect(screen.getByText('4.5')).toBeInTheDocument();
      expect(screen.getByText('(10 reviews)')).toBeInTheDocument();
    });

    it('hides rating when fewer than 3 reviews', () => {
      mockUseInstructorRatingsQuery.mockReturnValue({
        data: { overall: { rating: 5.0, total_reviews: 2 } },
      });
      const instructor = createInstructor();
      renderWithProviders(<InstructorHeader instructor={instructor} />);
      expect(screen.queryByText('5.0')).not.toBeInTheDocument();
    });

    it('renders bio or default text', () => {
      const instructor = createInstructor({ bio: 'My custom bio' });
      renderWithProviders(<InstructorHeader instructor={instructor} />);
      expect(screen.getByText('My custom bio')).toBeInTheDocument();
    });

    it('renders default bio when bio is empty', () => {
      const instructor = createInstructor({ bio: '' });
      renderWithProviders(<InstructorHeader instructor={instructor} />);
      expect(screen.getByText(/Passionate instructor with/)).toBeInTheDocument();
    });
  });

  describe('handleShare', () => {
    it('uses navigator.share when available', async () => {
      const mockShare = jest.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, 'share', {
        value: mockShare,
        writable: true,
        configurable: true,
      });

      const instructor = createInstructor();
      renderWithProviders(<InstructorHeader instructor={instructor} />);

      const user = userEvent.setup();
      await user.click(screen.getByLabelText('Share profile'));

      expect(mockShare).toHaveBeenCalledWith({
        title: 'John D.',
        url: expect.any(String),
      });

      delete (navigator as { share?: unknown }).share;
    });

    it('handles share error gracefully', async () => {
      const mockShare = jest.fn().mockRejectedValue(new Error('Share failed'));
      Object.defineProperty(navigator, 'share', {
        value: mockShare,
        writable: true,
        configurable: true,
      });

      const instructor = createInstructor();
      renderWithProviders(<InstructorHeader instructor={instructor} />);

      const user = userEvent.setup();
      // Should not throw
      await user.click(screen.getByLabelText('Share profile'));

      delete (navigator as { share?: unknown }).share;
    });

    it('falls back to clipboard and shows "Link copied" when navigator.share is absent', async () => {
      // Ensure navigator.share is NOT available
      delete (navigator as { share?: unknown }).share;

      // Provide a working clipboard.writeText so the fallback path succeeds
      const mockWriteText = jest.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: mockWriteText, readText: jest.fn() },
        writable: true,
        configurable: true,
      });

      const instructor = createInstructor();
      renderWithProviders(<InstructorHeader instructor={instructor} />);

      const shareButton = screen.getByLabelText('Share profile');
      // Before clicking, title should be "Share profile"
      expect(shareButton).toHaveAttribute('title', 'Share profile');

      // Use fireEvent to bypass userEvent's clipboard interception
      await act(async () => {
        fireEvent.click(shareButton);
      });

      // After the clipboard fallback, setShareCopied(true) is called and title becomes "Link copied"
      await waitFor(() => {
        expect(screen.getByLabelText('Share profile')).toHaveAttribute('title', 'Link copied');
      });

      // Verify writeText was called with the page URL
      expect(mockWriteText).toHaveBeenCalledWith(expect.any(String));
    });

    it('does not crash when clipboard.writeText throws', async () => {
      // Ensure navigator.share is NOT available
      delete (navigator as { share?: unknown }).share;

      // Override clipboard with a rejecting writeText to test the empty catch block
      const mockWriteText = jest.fn().mockRejectedValue(new Error('Clipboard denied'));
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: mockWriteText, readText: jest.fn() },
        writable: true,
        configurable: true,
      });

      const instructor = createInstructor();
      renderWithProviders(<InstructorHeader instructor={instructor} />);

      // Use fireEvent to bypass userEvent clipboard interception
      await act(async () => {
        fireEvent.click(screen.getByLabelText('Share profile'));
      });

      // The empty catch block should swallow the error. Button should still work.
      expect(screen.getByLabelText('Share profile')).toBeInTheDocument();
      // Since clipboard.writeText threw, setShareCopied(true) was never reached,
      // so the title should remain "Share profile"
      expect(screen.getByLabelText('Share profile')).toHaveAttribute('title', 'Share profile');
    });

    it('passes the correct displayName as title to navigator.share', async () => {
      const mockShare = jest.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, 'share', {
        value: mockShare,
        writable: true,
        configurable: true,
      });

      // Use a different name to verify displayName is correctly computed
      const instructor = createInstructor({
        user: { first_name: 'Alice', last_initial: 'B' },
      });
      renderWithProviders(<InstructorHeader instructor={instructor} />);

      const user = userEvent.setup();
      await user.click(screen.getByLabelText('Share profile'));

      expect(mockShare).toHaveBeenCalledWith({
        title: 'Alice B.',
        url: expect.any(String),
      });

      delete (navigator as { share?: unknown }).share;
    });

    it('does not call clipboard.writeText when navigator.share succeeds', async () => {
      const mockShare = jest.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, 'share', {
        value: mockShare,
        writable: true,
        configurable: true,
      });

      const mockWriteText = jest.fn();
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: mockWriteText },
        writable: true,
        configurable: true,
      });

      const instructor = createInstructor();
      renderWithProviders(<InstructorHeader instructor={instructor} />);

      const user = userEvent.setup();
      await user.click(screen.getByLabelText('Share profile'));

      // navigator.share was called, so clipboard.writeText should NOT be called (early return)
      expect(mockShare).toHaveBeenCalled();
      expect(mockWriteText).not.toHaveBeenCalled();

      delete (navigator as { share?: unknown }).share;
    });

  });

  describe('handleHeartClick', () => {
    it('redirects guest users to login', async () => {
      mockUseAuth.mockReturnValue({ user: null });
      const instructor = createInstructor();
      renderWithProviders(<InstructorHeader instructor={instructor} />);

      const user = userEvent.setup();
      await user.click(screen.getByLabelText('Sign in to save'));

      expect(mockPush).toHaveBeenCalledWith(
        expect.stringContaining('/login?returnTo=')
      );
      // URL is encoded, so action=favorite becomes action%3Dfavorite
      expect(mockPush).toHaveBeenCalledWith(
        expect.stringMatching(/action(%3D|=)favorite/)
      );
    });

    it('adds to favorites when not already saved', async () => {
      mockUseAuth.mockReturnValue({ user: { id: 'user-1' } });
      mockUseFavoriteStatus.mockReturnValue({ data: false });
      mockFavoritesApi.add.mockResolvedValue({ success: true, message: 'Added to favorites', favorite_id: 'fav-1' });

      const instructor = createInstructor();
      renderWithProviders(<InstructorHeader instructor={instructor} />);

      const user = userEvent.setup();
      await user.click(screen.getByLabelText('Toggle favorite'));

      await waitFor(() => {
        expect(mockSetFavoriteStatus).toHaveBeenCalledWith(
          '01K2TEST00000000000000001',
          true
        );
      });
      expect(mockFavoritesApi.add).toHaveBeenCalledWith('01K2TEST00000000000000001');
      expect(mockToast.success).toHaveBeenCalledWith('Added to favorites!');
    });

    it('removes from favorites when already saved', async () => {
      mockUseAuth.mockReturnValue({ user: { id: 'user-1' } });
      mockUseFavoriteStatus.mockReturnValue({ data: true });
      mockFavoritesApi.remove.mockResolvedValue({ success: true, message: 'Removed from favorites', not_favorited: true });

      const instructor = createInstructor();
      renderWithProviders(<InstructorHeader instructor={instructor} />);

      const user = userEvent.setup();
      await user.click(screen.getByLabelText('Toggle favorite'));

      await waitFor(() => {
        expect(mockFavoritesApi.remove).toHaveBeenCalledWith('01K2TEST00000000000000001');
      });
      expect(mockToast.success).toHaveBeenCalledWith('Removed from favorites');
    });

    it('reverts optimistic update on error', async () => {
      mockUseAuth.mockReturnValue({ user: { id: 'user-1' } });
      mockUseFavoriteStatus.mockReturnValue({ data: false });
      mockFavoritesApi.add.mockRejectedValue(new Error('API error'));

      const instructor = createInstructor();
      renderWithProviders(<InstructorHeader instructor={instructor} />);

      const user = userEvent.setup();
      await user.click(screen.getByLabelText('Toggle favorite'));

      await waitFor(() => {
        expect(mockSetFavoriteStatus).toHaveBeenCalledWith(
          '01K2TEST00000000000000001',
          false
        );
      });
      expect(mockToast.error).toHaveBeenCalledWith('Failed to update favorite');
    });

    it('prevents multiple clicks while loading', async () => {
      mockUseAuth.mockReturnValue({ user: { id: 'user-1' } });
      mockUseFavoriteStatus.mockReturnValue({ data: false });

      // Make the API call hang
      mockFavoritesApi.add.mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 1000))
      );

      const instructor = createInstructor();
      renderWithProviders(<InstructorHeader instructor={instructor} />);

      const user = userEvent.setup();
      // Click twice quickly
      await user.click(screen.getByLabelText('Toggle favorite'));
      await user.click(screen.getByLabelText('Toggle favorite'));

      // Should only be called once
      expect(mockFavoritesApi.add).toHaveBeenCalledTimes(1);
    });
  });

  describe('reviews link', () => {
    it('navigates to reviews page when clicking review count', async () => {
      mockUseInstructorRatingsQuery.mockReturnValue({
        data: { overall: { rating: 4.5, total_reviews: 10 } },
      });
      const instructor = createInstructor();
      renderWithProviders(<InstructorHeader instructor={instructor} />);

      const user = userEvent.setup();
      await user.click(screen.getByText('(10 reviews)'));

      expect(mockPush).toHaveBeenCalledWith('/instructors/01K2TEST00000000000000001/reviews');
    });
  });

  describe('display name edge cases', () => {
    it('renders Instructor #id when user has empty first_name and empty last_initial', () => {
      const instructor = createInstructor({
        user: { first_name: '', last_initial: '' },
      });
      renderWithProviders(<InstructorHeader instructor={instructor} />);
      // lastInitial is '' (falsy), firstName is '' (falsy) -> falls to Instructor #user_id
      expect(screen.getByTestId('instructor-profile-name')).toHaveTextContent(
        'Instructor #01K2TEST00000000000000001'
      );
    });
  });

  describe('isSaved resolution', () => {
    it('falls back to instructor.is_favorited when favoriteStatus is undefined', () => {
      mockUseAuth.mockReturnValue({ user: { id: 'user-1' } });
      // useFavoriteStatus returns undefined (not boolean)
      mockUseFavoriteStatus.mockReturnValue({ data: undefined });

      const instructor = createInstructor({ is_favorited: true } as InstructorProfile);
      renderWithProviders(<InstructorHeader instructor={instructor} />);

      // isSaved = undefined ?? true ?? false = true
      const heartButton = screen.getByLabelText('Toggle favorite');
      expect(heartButton).toBeInTheDocument();
      // Heart should be filled (isSaved=true)
      expect(heartButton.querySelector('svg')).toHaveAttribute('fill', '#7E22CE');
    });

    it('uses false when both favoriteStatus and is_favorited are undefined', () => {
      mockUseAuth.mockReturnValue({ user: { id: 'user-1' } });
      mockUseFavoriteStatus.mockReturnValue({ data: undefined });

      const instructor = createInstructor();
      // is_favorited is not set -> undefined
      renderWithProviders(<InstructorHeader instructor={instructor} />);

      // isSaved = undefined ?? undefined ?? false = false
      const heartButton = screen.getByLabelText('Toggle favorite');
      expect(heartButton.querySelector('svg')).toHaveAttribute('fill', 'none');
    });
  });

  describe('badge rendering edge cases', () => {
    it('does not render badge container when neither founding nor BGC', () => {
      const instructor = createInstructor({
        is_live: false,
        is_founding_instructor: false,
      } as InstructorProfile);

      renderWithProviders(<InstructorHeader instructor={instructor} />);

      expect(screen.queryByTestId('founding-badge')).not.toBeInTheDocument();
      expect(screen.queryByTestId('bgc-badge')).not.toBeInTheDocument();
    });

    it('renders BGC badge for background_check_status "verified"', () => {
      const instructor = {
        ...createInstructor(),
        background_check_status: 'verified',
      } as InstructorProfile & { background_check_status: string };

      renderWithProviders(<InstructorHeader instructor={instructor} />);

      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });

    it('renders BGC badge when background_check_verified is true', () => {
      const instructor = {
        ...createInstructor(),
        background_check_verified: true,
      } as InstructorProfile & { background_check_verified: boolean };

      renderWithProviders(<InstructorHeader instructor={instructor} />);

      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });

    it('renders BGC badge when background_check_completed is true', () => {
      const instructor = {
        ...createInstructor(),
        background_check_completed: true,
      } as InstructorProfile & { background_check_completed: boolean };

      renderWithProviders(<InstructorHeader instructor={instructor} />);

      expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
    });
  });

  describe('default bio', () => {
    it('shows years_experience in default bio when available', () => {
      const instructor = createInstructor({ bio: '', years_experience: 0 });
      renderWithProviders(<InstructorHeader instructor={instructor} />);
      // years_experience is 0 (falsy) -> uses 'several'
      expect(screen.getByText(/Passionate instructor with several years of experience/)).toBeInTheDocument();
    });
  });
});
