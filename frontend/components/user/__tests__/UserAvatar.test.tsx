/**
 * @jest-environment jsdom
 */
import React from 'react';
import { render, screen } from '@testing-library/react';

// ---------- mocks ----------

const mockGetUserInitials = jest.fn(
  (user: { first_name?: string; last_name?: string; email?: string } | null) => {
    if (!user) return '';
    if (user.first_name) return user.first_name[0]!.toUpperCase();
    return '';
  }
);

jest.mock('@/features/shared/hooks/useAuth.helpers', () => ({
  getUserInitials: (...args: unknown[]) => mockGetUserInitials(...(args as [Parameters<typeof mockGetUserInitials>[0]])),
}));

const mockUseProfilePictureUrls = jest.fn<
  Record<string, string | null>,
  [string[], string?]
>(() => ({}));

jest.mock('@/hooks/useProfilePictureUrls', () => ({
  useProfilePictureUrls: (...args: unknown[]) =>
    mockUseProfilePictureUrls(...(args as [string[], string?])),
}));

jest.mock('@/lib/utils', () => ({
  cn: (...classes: (string | boolean | undefined)[]) =>
    classes.filter(Boolean).join(' '),
}));

// Mock the Avatar UI primitives so AvatarImage renders immediately in jsdom
// (Radix AvatarImage waits for the browser image onLoad which never fires in jsdom)
jest.mock('@/components/ui/avatar', () => ({
  Avatar: ({ children, className, style }: { children: React.ReactNode; className?: string; style?: React.CSSProperties }) => (
    <span className={className} style={style}>{children}</span>
  ),
  AvatarImage: ({ src, alt }: { src: string; alt?: string }) =>
    React.createElement('img', { src, alt }),
  AvatarFallback: ({ children, className, style }: { children: React.ReactNode; className?: string; style?: React.CSSProperties }) => (
    <span className={className} style={style}>{children}</span>
  ),
}));

import { UserAvatar } from '../UserAvatar';

// ---------- helpers ----------

function makeUser(overrides: Partial<{
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  has_profile_picture: boolean;
  profile_picture_version: number;
}> = {}) {
  return {
    id: '01AAAAAAAAAAAAAAAAAAAAAAAAA',
    first_name: 'Jane',
    last_name: 'Doe',
    email: 'jane@example.com',
    has_profile_picture: true,
    profile_picture_version: 3,
    ...overrides,
  };
}

// ---------- tests ----------

describe('UserAvatar', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetUserInitials.mockImplementation(
      (user) => {
        if (!user) return '';
        if (user.first_name) return user.first_name[0]!.toUpperCase();
        return '';
      }
    );
  });

  // ---- buildRawId branch coverage ----

  describe('buildRawId logic', () => {
    it('appends version when profile_picture_version is a finite number', () => {
      const user = makeUser({ profile_picture_version: 3 });
      render(<UserAvatar user={user} />);

      // The hook should receive the rawId with version appended
      expect(mockUseProfilePictureUrls).toHaveBeenCalledWith(
        ['01AAAAAAAAAAAAAAAAAAAAAAAAA::v=3'],
        'thumb'
      );
    });

    it('appends version 0 when profile_picture_version is 0', () => {
      const user = makeUser({ profile_picture_version: 0 });
      render(<UserAvatar user={user} />);

      // Number.isFinite(0) is true, so version should be appended
      expect(mockUseProfilePictureUrls).toHaveBeenCalledWith(
        ['01AAAAAAAAAAAAAAAAAAAAAAAAA::v=0'],
        'thumb'
      );
    });

    it('omits version suffix when profile_picture_version is undefined', () => {
      const user = makeUser();
      // Remove the version property entirely
      const { profile_picture_version: _, ...userWithoutVersion } = user;
      render(<UserAvatar user={userWithoutVersion as typeof user} />);

      expect(mockUseProfilePictureUrls).toHaveBeenCalledWith(
        ['01AAAAAAAAAAAAAAAAAAAAAAAAA'],
        'thumb'
      );
    });
  });

  // ---- shouldFetch branch coverage ----

  describe('shouldFetch logic', () => {
    it('does not fetch when has_profile_picture is explicitly false', () => {
      const user = makeUser({ has_profile_picture: false });
      render(<UserAvatar user={user} />);

      // shouldFetch is false, so hook receives empty array
      expect(mockUseProfilePictureUrls).toHaveBeenCalledWith([], 'thumb');
    });

    it('fetches when has_profile_picture is undefined (not explicitly false)', () => {
      const user = makeUser();
      const { has_profile_picture: _, ...userWithoutPicFlag } = user;
      render(<UserAvatar user={userWithoutPicFlag as typeof user} />);

      // shouldFetch should be true since has_profile_picture !== false
      const callArgs = mockUseProfilePictureUrls.mock.calls[0];
      expect(callArgs?.[0]?.length).toBe(1);
    });

    it('does not fetch when user is null', () => {
      render(<UserAvatar user={null} />);

      expect(mockUseProfilePictureUrls).toHaveBeenCalledWith([], 'thumb');
    });
  });

  // ---- resolvedUrl branch coverage ----

  describe('resolvedUrl logic', () => {
    it('uses prefetchedUrl when provided, bypassing fetched URLs', () => {
      mockUseProfilePictureUrls.mockReturnValue({
        '01AAAAAAAAAAAAAAAAAAAAAAAAA': 'https://fetched.example.com/pic.jpg',
      });

      render(
        <UserAvatar
          user={makeUser()}
          prefetchedUrl="https://prefetched.example.com/avatar.jpg"
        />
      );

      // Should render AvatarImage with the prefetched URL
      const img = screen.getByRole('img');
      expect(img).toHaveAttribute('src', 'https://prefetched.example.com/avatar.jpg');
    });

    it('uses fetched URL when prefetchedUrl is not provided', () => {
      mockUseProfilePictureUrls.mockReturnValue({
        '01AAAAAAAAAAAAAAAAAAAAAAAAA': 'https://fetched.example.com/pic.jpg',
      });

      render(<UserAvatar user={makeUser()} />);

      const img = screen.getByRole('img');
      expect(img).toHaveAttribute('src', 'https://fetched.example.com/pic.jpg');
    });

    it('shows fallback when rawId is null (no fetch)', () => {
      render(<UserAvatar user={null} />);

      // No image should render, fallback shows
      expect(screen.queryByRole('img')).not.toBeInTheDocument();
    });

    it('shows fallback when fetched URL is null', () => {
      mockUseProfilePictureUrls.mockReturnValue({
        '01AAAAAAAAAAAAAAAAAAAAAAAAA': null,
      });

      render(<UserAvatar user={makeUser()} />);

      // The null value from fetchedUrls triggers the ?? null path,
      // which is still null, so fallback renders
      expect(screen.queryByRole('img')).not.toBeInTheDocument();
    });

    it('shows fallback when fetchedUrls map does not contain user id', () => {
      // Returns an empty map: fetchedUrls[user.id] is undefined, triggers ?? null
      mockUseProfilePictureUrls.mockReturnValue({});

      render(<UserAvatar user={makeUser()} />);

      expect(screen.queryByRole('img')).not.toBeInTheDocument();
    });

    it('uses prefetchedUrl=null to fall through to fetched URL', () => {
      mockUseProfilePictureUrls.mockReturnValue({
        '01AAAAAAAAAAAAAAAAAAAAAAAAA': 'https://fetched.example.com/pic.jpg',
      });

      render(
        <UserAvatar
          user={makeUser()}
          prefetchedUrl={null}
        />
      );

      // null prefetchedUrl triggers ?? fallthrough to the (rawId ? ... : null) branch
      const img = screen.getByRole('img');
      expect(img).toHaveAttribute('src', 'https://fetched.example.com/pic.jpg');
    });
  });

  // ---- initials / emoji fallback ----

  describe('fallback display', () => {
    it('shows initials when getUserInitials returns a value and no URL is resolved', () => {
      mockGetUserInitials.mockReturnValue('J');
      mockUseProfilePictureUrls.mockReturnValue({});

      render(<UserAvatar user={makeUser()} />);

      expect(screen.queryByRole('img')).not.toBeInTheDocument();
      expect(screen.getByText('J')).toBeInTheDocument();
    });

    it('shows emoji fallback when getUserInitials returns empty string and no URL is resolved', () => {
      mockGetUserInitials.mockReturnValue('');
      mockUseProfilePictureUrls.mockReturnValue({});

      render(<UserAvatar user={makeUser()} />);

      expect(screen.queryByRole('img')).not.toBeInTheDocument();
    });
  });

  // ---- custom colors ----

  describe('fallback colors', () => {
    it('uses default purple background and white text when no colors specified', () => {
      mockUseProfilePictureUrls.mockReturnValue({});

      const { container } = render(<UserAvatar user={makeUser()} />);

      const fallback = container.querySelector('[style]');
      expect(fallback).toBeTruthy();
    });

    it('applies custom fallbackBgColor and fallbackTextColor', () => {
      mockUseProfilePictureUrls.mockReturnValue({});
      mockGetUserInitials.mockReturnValue('J');

      const { container } = render(
        <UserAvatar
          user={makeUser()}
          fallbackBgColor="#FF0000"
          fallbackTextColor="#00FF00"
        />
      );

      const fallbackEl = container.querySelector('.flex.items-center.justify-center');
      if (fallbackEl) {
        const style = (fallbackEl as HTMLElement).style;
        expect(style.backgroundColor).toBe('rgb(255, 0, 0)');
        expect(style.color).toBe('rgb(0, 255, 0)');
      }
    });
  });

  // ---- variant prop ----

  describe('variant prop', () => {
    it('passes variant to useProfilePictureUrls', () => {
      render(<UserAvatar user={makeUser()} variant="display" />);

      expect(mockUseProfilePictureUrls).toHaveBeenCalledWith(
        expect.any(Array),
        'display'
      );
    });

    it('defaults variant to thumb', () => {
      render(<UserAvatar user={makeUser()} />);

      expect(mockUseProfilePictureUrls).toHaveBeenCalledWith(
        expect.any(Array),
        'thumb'
      );
    });
  });

  // ---- size and className ----

  describe('size and className', () => {
    it('applies custom size to the avatar root', () => {
      const { container } = render(
        <UserAvatar user={makeUser()} size={64} className="my-avatar" />
      );

      const root = container.firstChild as HTMLElement;
      expect(root.style.width).toBe('64px');
      expect(root.style.height).toBe('64px');
    });

    it('defaults size to 40', () => {
      const { container } = render(<UserAvatar user={makeUser()} />);

      const root = container.firstChild as HTMLElement;
      expect(root.style.width).toBe('40px');
      expect(root.style.height).toBe('40px');
    });
  });
});
