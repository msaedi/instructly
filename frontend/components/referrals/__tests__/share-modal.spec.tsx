import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ReferralShareModal from '../ReferralShareModal';

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

const { toast } = jest.requireMock('sonner') as {
  toast: {
    success: jest.Mock;
    error: jest.Mock;
  };
};

function setNavigatorProperty<K extends keyof Navigator>(key: K, value: Navigator[K] | undefined) {
  Object.defineProperty(window.navigator, key, {
    configurable: true,
    value: value as Navigator[K],
  });
}

describe('ReferralShareModal', () => {
  const shareUrl = 'https://app.theta.com/r/abc123';
  const code = 'ABC123';
  const originalShare = navigator.share;
  const originalClipboard = navigator.clipboard;

  beforeEach(() => {
    toast.success.mockClear();
    toast.error.mockClear();
    setNavigatorProperty('share', originalShare);
    setNavigatorProperty('clipboard', originalClipboard);
  });

  afterAll(() => {
    setNavigatorProperty('share', originalShare);
    setNavigatorProperty('clipboard', originalClipboard);
  });

  it('calls navigator.share when available', async () => {
    const shareMock = jest.fn().mockResolvedValue(undefined);
    setNavigatorProperty('share', shareMock);

    render(
      <ReferralShareModal open onClose={jest.fn()} code={code} shareUrl={shareUrl} />
    );

    fireEvent.click(screen.getByRole('button', { name: /share referral link/i }));

    await waitFor(() => {
      expect(shareMock).toHaveBeenCalledWith({
        title: 'Give $20, Get $20 on Theta',
        text: `Your first $75+ lesson is $20 off. Use my code ${code}`,
        url: shareUrl,
      });
    });
  });

  it('falls back to copy when web share is unavailable', async () => {
    setNavigatorProperty('share', undefined);
    const writeText = jest.fn().mockResolvedValue(undefined);
    setNavigatorProperty('clipboard', { writeText } as unknown as Navigator['clipboard']);

    render(
      <ReferralShareModal open onClose={jest.fn()} code={code} shareUrl={shareUrl} />
    );

    fireEvent.click(screen.getByRole('button', { name: /share referral link/i }));

    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(shareUrl);
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
      screen.getByText(/If your friend books, you both receive Theta credits/i)
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Terms apply/i })).toHaveAttribute('href', '/legal/referrals-terms');
  });
});
