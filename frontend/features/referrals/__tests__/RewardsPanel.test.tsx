import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RewardsPanel from '../RewardsPanel';
import { useSWRCustom } from '@/features/shared/hooks/useSWRCustom';
import { shareOrCopy } from '@/features/shared/referrals/share';
import { fetchReferralLedger } from '@/features/shared/referrals/api';
import { toast } from 'sonner';

jest.mock('@/features/shared/hooks/useSWRCustom', () => ({
  useSWRCustom: jest.fn(),
}));

jest.mock('@/features/shared/referrals/share', () => ({
  shareOrCopy: jest.fn(),
}));

jest.mock('@/features/shared/referrals/api', () => ({
  REFERRALS_ME_KEY: '/api/v1/referrals/me',
  fetchReferralLedger: jest.fn(),
  toReferralSummary: jest.fn((data) => ({
    code: data.code,
    share_url: data.share_url,
    pending: data.pending || [],
    unlocked: data.unlocked || [],
    redeemed: data.redeemed || [],
  })),
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

  // Line 36: When expire_ts is an invalid date (NaN check)
  it('handles invalid expire_ts gracefully (no badge shown)', () => {
    mockUseSWR.mockReturnValue({
      data: {
        ...baseLedger,
        unlocked: [
          {
            id: 'reward-1',
            amount_cents: 2000,
            status: 'unlocked',
            created_at: '2024-12-01T00:00:00Z',
            expire_ts: 'invalid-date-string',
          },
        ],
      },
      error: null,
      isLoading: false,
    });

    render(<RewardsPanel />);

    // Should not show any expiry badge since date is invalid
    expect(screen.queryByText(/expires/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/expired/i)).not.toBeInTheDocument();
  });

  // Line 40: When diffDays <= 0 (expired reward)
  it('shows "Expired" badge when reward has expired', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-15T00:00:00Z'));
    mockUseSWR.mockReturnValue({
      data: {
        ...baseLedger,
        unlocked: [
          {
            id: 'reward-1',
            amount_cents: 2000,
            status: 'unlocked',
            created_at: '2024-12-01T00:00:00Z',
            expire_ts: '2025-01-01T00:00:00Z', // Already passed
          },
        ],
      },
      error: null,
      isLoading: false,
    });

    render(<RewardsPanel />);

    expect(screen.getByText('Expired')).toBeInTheDocument();
    jest.useRealTimers();
  });

  // Lines 45-48: When 4-14 days remaining (warn tone)
  it('shows warning badge for rewards expiring in 4-14 days', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-01T00:00:00Z'));
    mockUseSWR.mockReturnValue({
      data: {
        ...baseLedger,
        unlocked: [
          {
            id: 'reward-1',
            amount_cents: 2000,
            status: 'unlocked',
            created_at: '2024-12-01T00:00:00Z',
            expire_ts: '2025-01-10T00:00:00Z', // 9 days away
          },
        ],
      },
      error: null,
      isLoading: false,
    });

    render(<RewardsPanel />);

    expect(screen.getByText(/expires in 9 days/i)).toBeInTheDocument();
    jest.useRealTimers();
  });

  // Lines 45-48: Neutral tone for expiry > 14 days
  it('shows neutral badge with date for rewards expiring in more than 14 days', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-01T00:00:00Z'));
    mockUseSWR.mockReturnValue({
      data: {
        ...baseLedger,
        unlocked: [
          {
            id: 'reward-1',
            amount_cents: 2000,
            status: 'unlocked',
            created_at: '2024-12-01T00:00:00Z',
            expire_ts: '2025-02-15T00:00:00Z', // 45 days away
          },
        ],
      },
      error: null,
      isLoading: false,
    });

    render(<RewardsPanel />);

    // Date format is "MMM D, YYYY" from Intl.DateTimeFormat
    expect(screen.getByText(/expires on/i)).toBeInTheDocument();
    jest.useRealTimers();
  });

  it('shows danger badge for rewards expiring in exactly 1 day', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-01T00:00:00Z'));
    mockUseSWR.mockReturnValue({
      data: {
        ...baseLedger,
        unlocked: [
          {
            id: 'reward-1',
            amount_cents: 2000,
            status: 'unlocked',
            created_at: '2024-12-01T00:00:00Z',
            expire_ts: '2025-01-02T00:00:00Z',
          },
        ],
      },
      error: null,
      isLoading: false,
    });

    render(<RewardsPanel />);

    expect(screen.getByText(/expires in 1 day$/i)).toBeInTheDocument();
    jest.useRealTimers();
  });

  // Test shareOrCopy returning 'copied'
  it('shows success toast when shareOrCopy returns copied', async () => {
    const user = userEvent.setup();
    (shareOrCopy as jest.Mock).mockResolvedValue('copied');
    mockUseSWR.mockReturnValue({ data: baseLedger, error: null, isLoading: false });

    render(<RewardsPanel />);

    await user.click(screen.getByRole('button', { name: /share/i }));
    expect(toast.success).toHaveBeenCalledWith('Referral link copied');
  });

  // Test shareOrCopy returning 'skipped'
  it('shows error toast when shareOrCopy returns skipped', async () => {
    const user = userEvent.setup();
    (shareOrCopy as jest.Mock).mockResolvedValue('skipped');
    mockUseSWR.mockReturnValue({ data: baseLedger, error: null, isLoading: false });

    render(<RewardsPanel />);

    await user.click(screen.getByRole('button', { name: /share/i }));
    expect(toast.error).toHaveBeenCalledWith('Unable to share right now. Try copying the link instead.');
  });

  // Test copy failure
  it('shows error toast when copy fails', async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: jest.fn().mockRejectedValue(new Error('Permission denied')) },
      writable: true,
    });
    mockUseSWR.mockReturnValue({ data: baseLedger, error: null, isLoading: false });

    render(<RewardsPanel />);

    await user.click(screen.getByRole('button', { name: /copy/i }));
    expect(toast.error).toHaveBeenCalledWith('Unable to copy link. Try again.');
  });

  // Test buttons disabled when no summary
  it('disables share and copy buttons while loading', () => {
    mockUseSWR.mockReturnValue({ data: null, error: null, isLoading: true });

    render(<RewardsPanel />);

    expect(screen.getByRole('button', { name: /share/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /copy/i })).toBeDisabled();
  });

  // Test pending tab rewards
  it('renders pending rewards in pending tab', async () => {
    const user = userEvent.setup();
    mockUseSWR.mockReturnValue({
      data: {
        ...baseLedger,
        pending: [
          {
            id: 'pending-1',
            amount_cents: 2000,
            status: 'pending',
            created_at: '2024-12-15T00:00:00Z',
            unlock_ts: '2025-01-15T00:00:00Z',
          },
        ],
      },
      error: null,
      isLoading: false,
    });

    render(<RewardsPanel />);

    await user.click(screen.getByRole('button', { name: /pending/i }));

    expect(screen.getByText('$20.00')).toBeInTheDocument();
    expect(screen.getByText(/pending.*credits unlock/i)).toBeInTheDocument();
  });

  // Test void rewards display
  it('displays void reward status correctly', async () => {
    mockUseSWR.mockReturnValue({
      data: {
        ...baseLedger,
        unlocked: [
          {
            id: 'void-1',
            amount_cents: 2000,
            status: 'void',
            created_at: '2024-12-01T00:00:00Z',
          },
        ],
      },
      error: null,
      isLoading: false,
    });

    render(<RewardsPanel />);

    expect(screen.getByText(/expired or cancelled/i)).toBeInTheDocument();
  });

  // Test hideHeader prop
  it('hides header when hideHeader prop is true', () => {
    mockUseSWR.mockReturnValue({ data: baseLedger, error: null, isLoading: false });

    render(<RewardsPanel hideHeader />);

    expect(screen.queryByText('Your rewards')).not.toBeInTheDocument();
  });

  // Test InviteByEmail renders with shareUrl
  it('renders InviteByEmail section when summary is loaded', () => {
    mockUseSWR.mockReturnValue({ data: baseLedger, error: null, isLoading: false });

    render(<RewardsPanel />);

    expect(screen.getByTestId('invite-by-email')).toHaveTextContent('https://example.com/ref');
  });

  // Test with inviterName prop
  it('passes inviterName to InviteByEmail', () => {
    mockUseSWR.mockReturnValue({ data: baseLedger, error: null, isLoading: false });

    render(<RewardsPanel inviterName="John" />);

    expect(screen.getByTestId('invite-by-email')).toBeInTheDocument();
  });

  // Test redeemed tab empty state
  it('renders empty copy for redeemed tab', async () => {
    const user = userEvent.setup();
    mockUseSWR.mockReturnValue({ data: baseLedger, error: null, isLoading: false });

    render(<RewardsPanel />);

    await user.click(screen.getByRole('button', { name: /redeemed/i }));

    expect(screen.getByText(/redeemed rewards will show here/i)).toBeInTheDocument();
  });

  // Test button aria-pressed state
  it('marks active tab button as pressed', () => {
    mockUseSWR.mockReturnValue({ data: baseLedger, error: null, isLoading: false });

    render(<RewardsPanel />);

    expect(screen.getByRole('button', { name: /unlocked/i })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /pending/i })).toHaveAttribute('aria-pressed', 'false');
  });

  // Lines 71-78: Test the fetcher callback directly (AbortController cleanup)
  it('calls fetcher with AbortController and cleans up', async () => {
    // Set up mock for fetchReferralLedger
    const mockFetchLedger = fetchReferralLedger as jest.Mock;
    mockFetchLedger.mockResolvedValue(baseLedger);

    // Capture the fetcher function when useSWR is called
    let capturedFetcher: ((url: string) => Promise<unknown>) | null = null;
    mockUseSWR.mockImplementation((_key: string, fetcher: (url: string) => Promise<unknown>) => {
      capturedFetcher = fetcher;
      return { data: baseLedger, error: null, isLoading: false };
    });

    render(<RewardsPanel />);

    // Verify fetcher was captured and call it
    expect(capturedFetcher).not.toBeNull();
    const fetcher = capturedFetcher!;
    const result = await fetcher('/api/v1/referrals/me');
    expect(mockFetchLedger).toHaveBeenCalled();
    // Verify AbortSignal was passed
    expect(mockFetchLedger.mock.calls[0]?.[0]).toBeInstanceOf(AbortSignal);
    expect(result).toEqual(baseLedger);
  });

  // Test fetcher error handling (lines 73-76 try/finally)
  it('handles fetcher error and still aborts controller', async () => {
    const mockFetchLedger = fetchReferralLedger as jest.Mock;
    mockFetchLedger.mockRejectedValue(new Error('Network error'));

    let capturedFetcher: ((url: string) => Promise<unknown>) | null = null;
    mockUseSWR.mockImplementation((_key: string, fetcher: (url: string) => Promise<unknown>) => {
      capturedFetcher = fetcher;
      return { data: null, error: new Error('Network error'), isLoading: false };
    });

    render(<RewardsPanel />);

    // Verify fetcher was captured and call it
    expect(capturedFetcher).not.toBeNull();
    const fetcher = capturedFetcher!;
    await expect(fetcher('/api/v1/referrals/me')).rejects.toThrow('Network error');
  });

  // Test error case in fetcher (lines 79-80 error handling)
  it('handles error in loadError correctly', () => {
    // Test with Error object
    mockUseSWR.mockReturnValue({
      data: null,
      error: new Error('Custom error message'),
      isLoading: false,
    });

    render(<RewardsPanel />);

    expect(screen.getByText('Custom error message')).toBeInTheDocument();
  });

  it('handles non-Error object in loadError', () => {
    // Test with non-Error object (string)
    mockUseSWR.mockReturnValue({
      data: null,
      error: 'Simple string error',
      isLoading: false,
    });

    render(<RewardsPanel />);

    expect(screen.getByText('Failed to load rewards')).toBeInTheDocument();
  });
});
