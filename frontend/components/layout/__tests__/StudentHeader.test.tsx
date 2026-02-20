import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import type { AnchorHTMLAttributes, MouseEvent, ReactNode } from 'react';
import userEvent from '@testing-library/user-event';
import { StudentHeader } from '../StudentHeader';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';

type MockLinkProps = {
  href: string;
  onClick?: (event: MouseEvent<HTMLAnchorElement>) => void;
  children: ReactNode;
} & AnchorHTMLAttributes<HTMLAnchorElement>;

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, onClick, children, ...props }: MockLinkProps) => (
    <a
      href={href}
      onClick={(event) => {
        event.preventDefault();
        onClick?.(event);
      }}
      {...props}
    >
      {children}
    </a>
  ),
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(),
}));

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  usePathname: jest.fn(),
  useSearchParams: jest.fn(),
}));

jest.mock('@/components/user/UserAvatar', () => ({
  UserAvatar: () => <div data-testid="user-avatar" />,
}));

const useAuthMock = useAuth as jest.Mock;
const useRouterMock = useRouter as jest.Mock;
const usePathnameMock = usePathname as jest.Mock;
const useSearchParamsMock = useSearchParams as jest.Mock;

describe('StudentHeader', () => {
  const push = jest.fn();
  const logout = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    useRouterMock.mockReturnValue({ push });
    useSearchParamsMock.mockReturnValue(new URLSearchParams());
    useAuthMock.mockReturnValue({
      user: { first_name: 'Alex', last_name: 'Lee', email: 'alex@example.com' },
      logout,
    });
  });

  it('hides search nav item on lessons page', () => {
    usePathnameMock.mockReturnValue('/student/lessons');

    render(<StudentHeader />);

    expect(screen.getByRole('link', { name: /my lessons/i })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /search/i })).not.toBeInTheDocument();
  });

  it('highlights rewards tab when active', () => {
    usePathnameMock.mockReturnValue('/student/dashboard');
    useSearchParamsMock.mockReturnValue(new URLSearchParams('tab=rewards'));

    render(<StudentHeader />);

    const rewardsLink = screen.getByRole('link', { name: /rewards/i });
    expect(rewardsLink.className).toMatch(/bg-primary\/10/);
  });

  it('toggles user menu and closes on outside click', async () => {
    usePathnameMock.mockReturnValue('/');
    const user = userEvent.setup();

    render(<StudentHeader />);

    await user.click(screen.getByRole('button', { name: /open account menu/i }));
    expect(screen.getByText(/my profile/i)).toBeInTheDocument();

    document.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));

    await waitFor(() => {
      expect(screen.queryByText(/my profile/i)).not.toBeInTheDocument();
    });
  });

  it('logs out and routes to login', async () => {
    usePathnameMock.mockReturnValue('/');
    const user = userEvent.setup();

    render(<StudentHeader />);

    await user.click(screen.getByRole('button', { name: /open account menu/i }));
    await user.click(screen.getByRole('button', { name: /log out/i }));

    expect(logout).toHaveBeenCalled();
    expect(push).toHaveBeenCalledWith('/login');
  });

  it('opens and closes mobile menu', async () => {
    usePathnameMock.mockReturnValue('/');
    const user = userEvent.setup();

    render(<StudentHeader />);

    await user.click(screen.getByRole('button', { name: /open navigation menu/i }));
    const homeLinks = screen.getAllByRole('link', { name: /home/i });
    expect(homeLinks.length).toBeGreaterThan(1);

    await user.click(homeLinks[homeLinks.length - 1] as HTMLElement);
    expect(screen.queryByRole('link', { name: /my profile/i })).not.toBeInTheDocument();
  });

  it('closes dropdown when profile link is clicked', async () => {
    usePathnameMock.mockReturnValue('/');
    const user = userEvent.setup();

    render(<StudentHeader />);

    // Open user menu
    await user.click(screen.getByRole('button', { name: /open account menu/i }));
    expect(screen.getByText(/my profile/i)).toBeInTheDocument();

    // Click the profile link in the dropdown
    await user.click(screen.getByRole('link', { name: /my profile/i }));

    // Menu should close
    await waitFor(() => {
      expect(screen.queryByText(/alex@example.com/i)).not.toBeInTheDocument();
    });
  });

  it('closes mobile menu when profile link is clicked', async () => {
    usePathnameMock.mockReturnValue('/');
    const user = userEvent.setup();

    render(<StudentHeader />);

    // Open mobile menu
    await user.click(screen.getByRole('button', { name: /open navigation menu/i }));

    // Find mobile menu profile link (there are multiple - get the one in mobile menu section)
    const profileLinks = screen.getAllByRole('link', { name: /my profile/i });
    // The mobile menu link should exist
    expect(profileLinks.length).toBeGreaterThan(0);

    // Click the last one (mobile menu version)
    await user.click(profileLinks[profileLinks.length - 1] as HTMLElement);

    // Mobile menu should close
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /close navigation menu/i })).not.toBeInTheDocument();
    });
  });

  it('handles mobile menu logout', async () => {
    usePathnameMock.mockReturnValue('/');
    const user = userEvent.setup();

    render(<StudentHeader />);

    // Open mobile menu
    await user.click(screen.getByRole('button', { name: /open navigation menu/i }));

    // Find and click the logout button in mobile menu
    const logoutButtons = screen.getAllByRole('button', { name: /log out/i });
    // There should be logout buttons (in mobile menu)
    expect(logoutButtons.length).toBeGreaterThan(0);

    await user.click(logoutButtons[logoutButtons.length - 1] as HTMLElement);

    expect(logout).toHaveBeenCalled();
    expect(push).toHaveBeenCalledWith('/login');
  });

  it('does not close menu when clicking inside the menu ref', async () => {
    usePathnameMock.mockReturnValue('/');
    const user = userEvent.setup();

    render(<StudentHeader />);

    await user.click(screen.getByRole('button', { name: /open account menu/i }));
    expect(screen.getByText(/my profile/i)).toBeInTheDocument();

    // Click inside the dropdown (on the user's name text)
    fireEvent.mouseDown(screen.getByText('Alex Lee'));

    // Menu should remain open because click was inside the menu ref
    await waitFor(() => {
      expect(screen.getByText(/my profile/i)).toBeInTheDocument();
    });
  });

  it('shows user full name and email in dropdown header', async () => {
    usePathnameMock.mockReturnValue('/');
    const user = userEvent.setup();

    render(<StudentHeader />);

    await user.click(screen.getByRole('button', { name: /open account menu/i }));

    expect(screen.getByText('Alex Lee')).toBeInTheDocument();
    expect(screen.getByText('alex@example.com')).toBeInTheDocument();
  });

  it('shows all nav items on non-lessons pages', () => {
    usePathnameMock.mockReturnValue('/');

    render(<StudentHeader />);

    expect(screen.getByRole('link', { name: /home/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /search/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /my lessons/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /rewards/i })).toBeInTheDocument();
  });

  it('hides search on nested lessons pages like /student/lessons/123', () => {
    usePathnameMock.mockReturnValue('/student/lessons/abc-123');

    render(<StudentHeader />);

    expect(screen.queryByRole('link', { name: /^search$/i })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /my lessons/i })).toBeInTheDocument();
  });

  it('cleans up mousedown listener on unmount', async () => {
    usePathnameMock.mockReturnValue('/');
    const removeEventSpy = jest.spyOn(document, 'removeEventListener');

    const { unmount } = render(<StudentHeader />);

    removeEventSpy.mockClear();
    unmount();

    const mousedownRemovals = removeEventSpy.mock.calls.filter(
      ([event]) => event === 'mousedown'
    );
    expect(mousedownRemovals.length).toBeGreaterThan(0);

    removeEventSpy.mockRestore();
  });

  describe('SSR hydration (server snapshot path)', () => {
    it('renders fallback placeholder when useSyncExternalStore returns server snapshot (false)', () => {
      usePathnameMock.mockReturnValue('/');
      const actualReact = jest.requireActual<typeof import('react')>('react');
      const spy = jest.spyOn(actualReact, 'useSyncExternalStore').mockImplementation(
        (_subscribe, _getSnapshot, getServerSnapshot) => {
          return getServerSnapshot ? getServerSnapshot() : _getSnapshot();
        }
      );

      render(<StudentHeader />);

      // When isMounted is false (server snapshot), user info should NOT render.
      // Instead, the fallback "Account" text and the generic user icon should show.
      expect(screen.getByText('Account')).toBeInTheDocument();
      // The UserAvatar should NOT be rendered since isMounted && user is false
      expect(screen.queryByTestId('user-avatar')).not.toBeInTheDocument();

      spy.mockRestore();
    });

    it('shows "User" in dropdown header when server snapshot is active', async () => {
      usePathnameMock.mockReturnValue('/');
      const actualReact = jest.requireActual<typeof import('react')>('react');
      const spy = jest.spyOn(actualReact, 'useSyncExternalStore').mockImplementation(
        (_subscribe, _getSnapshot, getServerSnapshot) => {
          return getServerSnapshot ? getServerSnapshot() : _getSnapshot();
        }
      );
      const user = userEvent.setup();

      render(<StudentHeader />);

      await user.click(screen.getByRole('button', { name: /open account menu/i }));

      // When isMounted is false, the dropdown should show "User" instead of the actual name
      expect(screen.getByText('User')).toBeInTheDocument();
      // Email should be empty string so no email text visible
      expect(screen.queryByText('alex@example.com')).not.toBeInTheDocument();

      spy.mockRestore();
    });
  });
});
