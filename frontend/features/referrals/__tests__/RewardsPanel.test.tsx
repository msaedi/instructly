import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RewardsPanel from '../RewardsPanel';
import { useSWRCustom } from '@/features/shared/hooks/useSWRCustom';
import { shareOrCopy } from '@/features/shared/referrals/share';
import { toast } from 'sonner';

jest.mock('@/features/shared/hooks/useSWRCustom', () => ({
  useSWRCustom: jest.fn(),
}));

jest.mock('@/features/shared/referrals/share', () => ({
  shareOrCopy: jest.fn(),
}));

jest.mock('@/features/referrals/InviteByEmail', () => ({
  __esModule: true,
  default: ({ shareUrl }: { shareUrl: string }) => <div data-testid="invite-by-email">{shareUrl}</div>,
}));

jest.mock('sonner', () => ({
  toast: {
    error: jest.fn(),
    success: jest.fn(),
  },
}));

const mockUseSWR = useSWRCustom as jest.Mock;

const baseLedger = {
  code: 'REF123',
  share_url: 'https://example.com/ref',
  pending: [],
  unlocked: [],
  redeemed: [],
};

describe('RewardsPanel', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows a loading indicator while rewards load', () => {
    mockUseSWR.mockReturnValue({ data: null, error: null, isLoading: true });

    render(<RewardsPanel />);

    expect(screen.getByText(/loading rewards/i)).toBeInTheDocument();
  });

  it('shows an error banner when loading fails', () => {
    mockUseSWR.mockReturnValue({ data: null, error: new Error('Nope'), isLoading: false });

    render(<RewardsPanel />);

    expect(screen.getByText(/nope/i)).toBeInTheDocument();
  });

  it('renders empty copy per tab', async () => {
    const user = userEvent.setup();
    mockUseSWR.mockReturnValue({ data: baseLedger, error: null, isLoading: false });

    render(<RewardsPanel />);

    expect(screen.getByText(/no unlocked rewards/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /pending/i }));
    expect(screen.getByText(/no pending rewards/i)).toBeInTheDocument();
  });

  it('copies the referral link with clipboard access', async () => {
    const user = userEvent.setup();
    const writeText = jest.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, writable: true });
    mockUseSWR.mockReturnValue({ data: baseLedger, error: null, isLoading: false });

    render(<RewardsPanel />);

    await user.click(screen.getByRole('button', { name: /copy/i }));

    expect(writeText).toHaveBeenCalledWith('https://example.com/ref');
    expect(toast.success).toHaveBeenCalledWith('Referral link copied');
  });

  it('falls back to execCommand when clipboard is unavailable', async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, 'clipboard', { value: undefined, writable: true });
    const execCommand = jest.fn().mockReturnValue(true);
    document.execCommand = execCommand;
    mockUseSWR.mockReturnValue({ data: baseLedger, error: null, isLoading: false });

    render(<RewardsPanel />);

    await user.click(screen.getByRole('button', { name: /copy/i }));

    expect(execCommand).toHaveBeenCalledWith('copy');
    expect(toast.success).toHaveBeenCalledWith('Referral link copied');
  });

  it('shares and renders reward badges with expiry status', async () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-01T00:00:00Z'));
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    (shareOrCopy as jest.Mock).mockResolvedValue('shared');
    mockUseSWR.mockReturnValue({
      data: {
        ...baseLedger,
        unlocked: [
          {
            id: 'reward-1',
            amount_cents: 2000,
            status: 'unlocked',
            created_at: '2024-12-01T00:00:00Z',
            expire_ts: '2025-01-03T00:00:00Z',
          },
        ],
        redeemed: [
          {
            id: 'reward-2',
            amount_cents: 2000,
            status: 'redeemed',
            created_at: '2024-11-01T00:00:00Z',
          },
        ],
      },
      error: null,
      isLoading: false,
    });

    render(<RewardsPanel />);

    await user.click(screen.getByRole('button', { name: /share/i }));
    expect(toast.success).toHaveBeenCalledWith('Share sheet opened');
    expect(screen.getByText(/expires in 2 days/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /redeemed/i }));
    expect(screen.getAllByText(/applied/i).length).toBeGreaterThan(0);
    jest.useRealTimers();
  });
});
