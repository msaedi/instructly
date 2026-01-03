import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

import { InstructorReferralPopup } from '@/components/instructor/InstructorReferralPopup';

jest.mock('@/hooks/queries/useInstructorReferrals', () => ({
  useReferralPopupData: jest.fn(),
  formatCents: (cents: number) => `$${(cents / 100).toFixed(0)}`,
}));

jest.mock('@/lib/copy', () => ({
  copyToClipboard: jest.fn(),
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
});
