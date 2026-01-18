import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StudentHeader } from '../StudentHeader';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';

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
});
