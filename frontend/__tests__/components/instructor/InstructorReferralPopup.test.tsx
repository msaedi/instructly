import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

import { InstructorReferralPopup } from '@/components/instructor/InstructorReferralPopup';

jest.mock('@/hooks/queries/useInstructorReferrals', () => ({
  useReferralPopupData: jest.fn(),
  formatCents: (cents: number) => `$${(cents / 100).toFixed(0)}`,
}));

jest.mock('@/lib/copy', () => ({
  copyToClipboard: jest.fn(),
}));

jest.mock('@/features/shared/referrals/share', () => ({
  shareOrCopy: jest.fn(),
}));

const mockPopupData = {
  isFoundingPhase: true,
  bonusAmountCents: 7500,
  foundingSpotsRemaining: 42,
  referralCode: 'TESTCODE',
  referralLink: 'https://instainstru.com/r/TESTCODE',
};

describe('InstructorReferralPopup', () => {
  const hooks = jest.requireMock('@/hooks/queries/useInstructorReferrals') as {
    useReferralPopupData: jest.Mock;
  };
  const copy = jest.requireMock('@/lib/copy') as { copyToClipboard: jest.Mock };
  const share = jest.requireMock('@/features/shared/referrals/share') as { shareOrCopy: jest.Mock };

  beforeEach(() => {
    jest.clearAllMocks();
    const storageState = new Map<string, string>();
    const localStorageMock = window.localStorage as Storage & {
      getItem: jest.Mock;
      setItem: jest.Mock;
      removeItem: jest.Mock;
      clear: jest.Mock;
    };

    localStorageMock.getItem.mockImplementation((key: string) => storageState.get(key) ?? null);
    localStorageMock.setItem.mockImplementation((key: string, value: string) => {
      storageState.set(key, value);
    });
    localStorageMock.removeItem.mockImplementation((key: string) => {
      storageState.delete(key);
    });
    localStorageMock.clear.mockImplementation(() => {
      storageState.clear();
    });

    localStorageMock.clear();
    jest.useFakeTimers();
    copy.copyToClipboard.mockResolvedValue(true);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('does not show when instructor is not live', () => {
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    render(<InstructorReferralPopup isLive={false} />);

    expect(hooks.useReferralPopupData).toHaveBeenCalledWith(false);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('does not show when already dismissed', () => {
    localStorage.setItem('instructor_referral_popup_dismissed', 'true');
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    render(<InstructorReferralPopup isLive={true} />);

    expect(hooks.useReferralPopupData).toHaveBeenCalledWith(false);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows popup for live instructor who has not dismissed', async () => {
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    expect(screen.getByText(/Earn \$75 Per Referral/i)).toBeInTheDocument();
  });

  it('shows founding phase urgency message', async () => {
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByText(/founding spots left/i)).toBeInTheDocument();
    });
  });

  it('does not show founding urgency when phase is over', async () => {
    hooks.useReferralPopupData.mockReturnValue({
      data: { ...mockPopupData, isFoundingPhase: false, bonusAmountCents: 5000 },
    });

    render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    expect(screen.queryByText(/founding spots left/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Earn \$50 Per Referral/i)).toBeInTheDocument();
  });

  it('dismisses and saves to localStorage on X click', async () => {
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText('Close'));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(localStorage.getItem('instructor_referral_popup_dismissed')).toBe('true');
  });

  it('dismisses on "Maybe Later" click', async () => {
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Maybe Later'));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(localStorage.getItem('instructor_referral_popup_dismissed')).toBe('true');
  });

  it('dismisses on backdrop click', async () => {
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    const backdrop = screen.getByTestId('referral-popup-backdrop');
    fireEvent.click(backdrop);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('copies link to clipboard on copy button click', async () => {
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText('Copy link'));

    await waitFor(() => {
      expect(copy.copyToClipboard).toHaveBeenCalledWith('https://instainstru.com/r/TESTCODE');
    });
  });

  it('displays referral link', async () => {
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByText('https://instainstru.com/r/TESTCODE')).toBeInTheDocument();
    });
  });

  // Lines 75-87: handleShare function - share via native share API
  it('shares via native share API and dismisses on success', async () => {
    share.shareOrCopy.mockResolvedValue('shared');
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    // Mock navigator.share as available
    Object.defineProperty(navigator, 'share', {
      value: jest.fn(),
      configurable: true,
    });

    render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Share your link'));

    await waitFor(() => {
      expect(share.shareOrCopy).toHaveBeenCalledWith(
        {
          title: 'Join me on iNSTAiNSTRU',
          text: 'Sign up as an instructor on iNSTAiNSTRU and start teaching students in NYC.',
          url: 'https://instainstru.com/r/TESTCODE',
        },
        'https://instainstru.com/r/TESTCODE'
      );
    });

    // Should dismiss after successful share
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  // Lines 86-87: handleShare falls back to copy when share is unavailable
  it('copies link when share returns copied outcome', async () => {
    share.shareOrCopy.mockResolvedValue('copied');
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    Object.defineProperty(navigator, 'share', {
      value: jest.fn(),
      configurable: true,
    });

    render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Share your link'));

    await waitFor(() => {
      expect(share.shareOrCopy).toHaveBeenCalled();
    });

    // Should show "Copied" state
    await waitFor(() => {
      expect(screen.getByLabelText('Copied')).toBeInTheDocument();
    });
  });

  // Line 32: clearTimeout for showTimerRef when popup data changes
  it('clears existing show timer when popup data changes', async () => {
    const clearTimeoutSpy = jest.spyOn(global, 'clearTimeout');
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    const { rerender } = render(<InstructorReferralPopup isLive={true} />);

    // First render sets a timer
    act(() => {
      jest.advanceTimersByTime(500); // Not enough to show popup yet
    });

    // Re-render with new data should clear the old timer
    hooks.useReferralPopupData.mockReturnValue({
      data: { ...mockPopupData, bonusAmountCents: 10000 },
    });

    rerender(<InstructorReferralPopup isLive={true} />);

    // The clearTimeout should have been called for the previous timer
    expect(clearTimeoutSpy).toHaveBeenCalled();

    clearTimeoutSpy.mockRestore();
  });

  // Line 56: clearTimeout for copyTimerRef when copy is triggered multiple times
  it('clears copy timer when copy is triggered multiple times', async () => {
    const clearTimeoutSpy = jest.spyOn(global, 'clearTimeout');
    copy.copyToClipboard.mockResolvedValue(true);
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    // Click copy first time
    fireEvent.click(screen.getByLabelText('Copy link'));

    await waitFor(() => {
      expect(screen.getByLabelText('Copied')).toBeInTheDocument();
    });

    // Click copy again (before the 2 second reset)
    fireEvent.click(screen.getByLabelText('Copied'));

    // The clearTimeout should be called for the previous copy timer
    expect(clearTimeoutSpy).toHaveBeenCalled();

    clearTimeoutSpy.mockRestore();
  });

  // Test that copy timer resets the copied state after 2 seconds
  it('resets copied state after 2 seconds', async () => {
    copy.copyToClipboard.mockResolvedValue(true);
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText('Copy link'));

    await waitFor(() => {
      expect(screen.getByLabelText('Copied')).toBeInTheDocument();
    });

    // Advance time by 2 seconds to trigger the reset
    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByLabelText('Copy link')).toBeInTheDocument();
    });
  });

  // Test handleCopyLink does nothing when referralLink is missing
  it('does nothing when referralLink is missing on copy', async () => {
    hooks.useReferralPopupData.mockReturnValue({
      data: { ...mockPopupData, referralLink: '' },
    });

    render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    // Click copy - it should do nothing since referralLink is empty
    fireEvent.click(screen.getByLabelText('Copy link'));

    // copyToClipboard should not be called since referralLink is empty
    expect(copy.copyToClipboard).not.toHaveBeenCalled();
  });

  // Test handleShare does nothing when referralLink is missing
  it('does nothing when referralLink is missing on share', async () => {
    share.shareOrCopy.mockResolvedValue('shared');
    hooks.useReferralPopupData.mockReturnValue({
      data: { ...mockPopupData, referralLink: '' },
    });

    // Mock navigator.share as available
    Object.defineProperty(navigator, 'share', {
      value: jest.fn(),
      configurable: true,
    });

    render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    // Click share - it should do nothing since referralLink is empty
    fireEvent.click(screen.getByText('Share your link'));

    // shareOrCopy should not be called since referralLink is empty
    expect(share.shareOrCopy).not.toHaveBeenCalled();
  });

  // Test copyToClipboard returns false
  it('does not show copied state when copyToClipboard fails', async () => {
    copy.copyToClipboard.mockResolvedValue(false);
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText('Copy link'));

    // Should remain as "Copy link" (not change to "Copied")
    await waitFor(() => {
      expect(screen.getByLabelText('Copy link')).toBeInTheDocument();
    });
  });

  // Test clicking on dialog content doesn't dismiss
  it('does not dismiss when clicking on dialog content', async () => {
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    // Click on the dialog content itself
    fireEvent.click(screen.getByText(/Earn \$75 Per Referral/i));

    // Dialog should still be visible
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  // Test "View all referrals" link
  it('renders link to view all referrals', async () => {
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    const link = screen.getByRole('link', { name: /view all referrals/i });
    expect(link).toHaveAttribute('href', '/instructor/dashboard?panel=referrals');
  });

  // Test cleanup on unmount
  it('clears timers on unmount', () => {
    const clearTimeoutSpy = jest.spyOn(global, 'clearTimeout');
    hooks.useReferralPopupData.mockReturnValue({ data: mockPopupData });

    const { unmount } = render(<InstructorReferralPopup isLive={true} />);

    act(() => {
      jest.advanceTimersByTime(1000); // Timer is set but popup not shown yet
    });

    unmount();

    // clearTimeout should be called during cleanup
    expect(clearTimeoutSpy).toHaveBeenCalled();

    clearTimeoutSpy.mockRestore();
  });
});
