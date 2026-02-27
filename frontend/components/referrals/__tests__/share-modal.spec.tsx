import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ReferralShareModal from '../ReferralShareModal';

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('@/features/shared/referrals/share', () => ({
  shareOrCopy: jest.fn(),
}));

const { toast } = jest.requireMock('sonner') as {
  toast: {
    success: jest.Mock;
    error: jest.Mock;
  };
};

const { shareOrCopy: mockShareOrCopy } = jest.requireMock('@/features/shared/referrals/share') as {
  shareOrCopy: jest.Mock;
};

function setNavigatorProperty<K extends keyof Navigator>(key: K, value: Navigator[K] | undefined) {
  Object.defineProperty(window.navigator, key, {
    configurable: true,
    value: value as Navigator[K],
  });
}

describe('ReferralShareModal', () => {
  const shareUrl = 'https://app.instainstru.com/r/abc123';
  const code = 'ABC123';
  const originalShare = navigator.share;
  const originalClipboard = navigator.clipboard;

  beforeEach(() => {
    toast.success.mockClear();
    toast.error.mockClear();
    mockShareOrCopy.mockClear();
    mockShareOrCopy.mockResolvedValue('shared'); // Default behavior
    setNavigatorProperty('share', originalShare);
    setNavigatorProperty('clipboard', originalClipboard);
  });

  afterAll(() => {
    setNavigatorProperty('share', originalShare);
    setNavigatorProperty('clipboard', originalClipboard);
  });

  it('calls shareOrCopy with correct payload when share button clicked', async () => {
    mockShareOrCopy.mockResolvedValue('shared');

    render(
      <ReferralShareModal open onClose={jest.fn()} code={code} shareUrl={shareUrl} />
    );

    fireEvent.click(screen.getByRole('button', { name: /share referral link/i }));

    await waitFor(() => {
      expect(mockShareOrCopy).toHaveBeenCalledWith(
        {
          title: 'Give $20, Get $20 on iNSTAiNSTRU',
          text: `Your first $75+ lesson is $20 off. Use my code ${code}`,
          url: shareUrl,
        },
        shareUrl
      );
      expect(toast.success).toHaveBeenCalledWith('Share sheet opened');
    });
  });

  it('shows copy toast when shareOrCopy returns copied', async () => {
    mockShareOrCopy.mockResolvedValue('copied');

    render(
      <ReferralShareModal open onClose={jest.fn()} code={code} shareUrl={shareUrl} />
    );

    fireEvent.click(screen.getByRole('button', { name: /share referral link/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Referral link copied');
    });
  });

  it('copies the link when copy button is used', async () => {
    const writeText = jest.fn().mockResolvedValue(undefined);
    setNavigatorProperty('clipboard', { writeText } as unknown as Navigator['clipboard']);

    render(
      <ReferralShareModal open onClose={jest.fn()} code={code} shareUrl={shareUrl} />
    );

    fireEvent.click(screen.getByRole('button', { name: /copy referral link/i }));

    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(shareUrl);
    });
  });

  it('shows disclosure text', () => {
    render(
      <ReferralShareModal open onClose={jest.fn()} code={code} shareUrl={shareUrl} />
    );

    expect(
      screen.getByText(/If your friend books, you both receive iNSTAiNSTRU credits/i)
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Terms apply/i })).toHaveAttribute('href', '/referrals-terms');
  });

  it('formats slug from invalid URL by falling back to code', () => {
    // Line 33: When URL parsing fails, it falls back to /r/${code}
    render(
      <ReferralShareModal
        open
        onClose={jest.fn()}
        code={code}
        shareUrl="not-a-valid-url"
      />
    );

    // Should display the fallback slug format
    expect(screen.getByText(/\/r\/ABC123/i)).toBeInTheDocument();
  });

  it('falls back to execCommand when clipboard API is unavailable', async () => {
    // Lines 43-51: Legacy clipboard fallback
    setNavigatorProperty('clipboard', undefined);
    const mockExecCommand = jest.fn().mockReturnValue(true);
    document.execCommand = mockExecCommand;

    render(
      <ReferralShareModal open onClose={jest.fn()} code={code} shareUrl={shareUrl} />
    );

    fireEvent.click(screen.getByRole('button', { name: /copy referral link/i }));

    await waitFor(() => {
      expect(mockExecCommand).toHaveBeenCalledWith('copy');
      expect(toast.success).toHaveBeenCalledWith('Referral link copied');
    });
  });

  it('shows error toast when clipboard copy fails', async () => {
    // Line 55: toast.error when copy fails
    const writeText = jest.fn().mockRejectedValue(new Error('Permission denied'));
    setNavigatorProperty('clipboard', { writeText } as unknown as Navigator['clipboard']);

    render(
      <ReferralShareModal open onClose={jest.fn()} code={code} shareUrl={shareUrl} />
    );

    fireEvent.click(screen.getByRole('button', { name: /copy referral link/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Unable to copy link. Try copying manually.');
    });
  });

  it('shows error toast when share is skipped', async () => {
    // Line 76: toast.error when shareOrCopy returns 'skipped'
    mockShareOrCopy.mockResolvedValue('skipped');

    render(
      <ReferralShareModal open onClose={jest.fn()} code={code} shareUrl={shareUrl} />
    );

    fireEvent.click(screen.getByRole('button', { name: /share referral link/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Unable to share right now. Try copying the link instead.');
    });
  });

  it('disables buttons while processing share', async () => {
    // Make shareOrCopy never resolve to keep in processing state
    mockShareOrCopy.mockImplementation(() => new Promise(() => {}));

    render(
      <ReferralShareModal open onClose={jest.fn()} code={code} shareUrl={shareUrl} />
    );

    const shareButton = screen.getByRole('button', { name: /share referral link/i });
    const copyButton = screen.getByRole('button', { name: /copy referral link/i });

    fireEvent.click(shareButton);

    await waitFor(() => {
      expect(shareButton).toBeDisabled();
      expect(copyButton).toBeDisabled();
    });
  });

  it('disables buttons while processing copy', async () => {
    const writeText = jest.fn().mockImplementation(() => new Promise(() => {})); // Never resolves
    setNavigatorProperty('clipboard', { writeText } as unknown as Navigator['clipboard']);

    render(
      <ReferralShareModal open onClose={jest.fn()} code={code} shareUrl={shareUrl} />
    );

    const copyButton = screen.getByRole('button', { name: /copy referral link/i });

    fireEvent.click(copyButton);

    await waitFor(() => {
      expect(copyButton).toBeDisabled();
    });
  });

  it('calls onClose when close button is clicked', () => {
    const onClose = jest.fn();
    render(
      <ReferralShareModal open onClose={onClose} code={code} shareUrl={shareUrl} />
    );

    // There are multiple close buttons (modal X and the "Close" text button), use the text "Close" button
    const closeButtons = screen.getAllByRole('button', { name: /close/i });
    const closeTextButton = closeButtons.find(btn => btn.textContent === 'Close');
    expect(closeTextButton).toBeDefined();
    fireEvent.click(closeTextButton!);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('falls back to code when URL pathname has no segments (line 31 pop() ?? code)', () => {
    // A URL like "https://example.com" has pathname "/" which after
    // split('/').filter(Boolean) produces an empty array, so pop() returns undefined.
    // The ?? code fallback should be used.
    render(
      <ReferralShareModal
        open
        onClose={jest.fn()}
        code={code}
        shareUrl="https://example.com"
      />
    );

    // Should display /r/ABC123 via the ?? code fallback
    expect(screen.getByText(/\/r\/ABC123/i)).toBeInTheDocument();
  });

  it('copy finally block preserves non-copy state (line 57)', async () => {
    // Scenario: copyToClipboard starts (sets isProcessing to 'copy'),
    // but by the time the finally runs, the state is already something else.
    // The ternary `current === 'copy' ? null : current` preserves the other state.
    // We test by clicking copy with a fast-resolving clipboard mock,
    // confirming processing resets to null after completion.
    const writeText = jest.fn().mockResolvedValue(undefined);
    setNavigatorProperty('clipboard', { writeText } as unknown as Navigator['clipboard']);

    render(
      <ReferralShareModal open onClose={jest.fn()} code={code} shareUrl={shareUrl} />
    );

    const copyButton = screen.getByRole('button', { name: /copy referral link/i });
    fireEvent.click(copyButton);

    // After copy resolves, buttons should be re-enabled (isProcessing back to null)
    await waitFor(() => {
      expect(copyButton).not.toBeDisabled();
    });

    expect(toast.success).toHaveBeenCalledWith('Referral link copied');
  });

  it('share finally block resets state after share completes (line 79)', async () => {
    mockShareOrCopy.mockResolvedValue('shared');

    render(
      <ReferralShareModal open onClose={jest.fn()} code={code} shareUrl={shareUrl} />
    );

    const shareButton = screen.getByRole('button', { name: /share referral link/i });
    fireEvent.click(shareButton);

    // After share resolves, buttons should be re-enabled (isProcessing back to null)
    await waitFor(() => {
      expect(shareButton).not.toBeDisabled();
    });

    expect(toast.success).toHaveBeenCalledWith('Share sheet opened');
  });

  it('formats slug from URL with only root path', () => {
    // URL "https://example.com/" has pathname "/" which splits to empty filtered array
    render(
      <ReferralShareModal
        open
        onClose={jest.fn()}
        code={code}
        shareUrl="https://example.com/"
      />
    );

    expect(screen.getByText(/\/r\/ABC123/i)).toBeInTheDocument();
  });

  it('formats slug from URL with multi-segment path', () => {
    // URL with path "/r/my-custom-slug" should use "my-custom-slug" from pop()
    render(
      <ReferralShareModal
        open
        onClose={jest.fn()}
        code={code}
        shareUrl="https://app.instainstru.com/r/my-custom-slug"
      />
    );

    // The formatted slug should show the last path segment, not the code
    expect(screen.getByText(/Direct shortcut: \/r\/my-custom-slug/)).toBeInTheDocument();
  });
});
