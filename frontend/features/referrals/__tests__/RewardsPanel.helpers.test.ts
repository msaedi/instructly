import { toast } from 'sonner';
import { shareOrCopy } from '@/features/shared/referrals/share';
import { copyReferralLink, shareReferralLink } from '../RewardsPanel.helpers';

jest.mock('@/features/shared/referrals/share', () => ({
  shareOrCopy: jest.fn(),
}));

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

const summary = {
  code: 'REF123',
  share_url: 'https://example.com/ref',
  pending: [],
  unlocked: [],
  redeemed: [],
};

describe('RewardsPanel helpers', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('no-ops copy and share actions when the referral summary is missing', async () => {
    const clipboardWrite = jest.fn();
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: clipboardWrite },
    });

    await copyReferralLink(null, 'https://example.com/ref');
    await shareReferralLink(null, 'https://example.com/ref');

    expect(clipboardWrite).not.toHaveBeenCalled();
    expect(shareOrCopy).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('copies via clipboard when available and falls back to execCommand errors cleanly', async () => {
    const writeText = jest.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });

    await copyReferralLink(summary, summary.share_url);
    expect(writeText).toHaveBeenCalledWith(summary.share_url);
    expect(toast.success).toHaveBeenCalledWith('Referral link copied');

    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: undefined,
    });
    const execCommand = jest.fn(() => {
      throw new Error('copy failed');
    });
    document.execCommand = execCommand;

    await copyReferralLink(summary, summary.share_url);
    expect(execCommand).toHaveBeenCalledWith('copy');
    expect(toast.error).toHaveBeenCalledWith('Unable to copy link. Try again.');
  });

  it('reports shared, copied, and failed share outcomes', async () => {
    (shareOrCopy as jest.Mock).mockResolvedValueOnce('shared');
    await shareReferralLink(summary, summary.share_url);
    expect(toast.success).toHaveBeenCalledWith('Share sheet opened');

    (shareOrCopy as jest.Mock).mockResolvedValueOnce('copied');
    await shareReferralLink(summary, summary.share_url);
    expect(toast.success).toHaveBeenCalledWith('Referral link copied');

    (shareOrCopy as jest.Mock).mockResolvedValueOnce('unsupported');
    await shareReferralLink(summary, summary.share_url);
    expect(toast.error).toHaveBeenCalledWith(
      'Unable to share right now. Try copying the link instead.',
    );
  });
});
