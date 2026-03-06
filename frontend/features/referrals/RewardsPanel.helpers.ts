import { toast } from 'sonner';
import { shareOrCopy } from '@/features/shared/referrals/share';
import type { ReferralSummary } from '@/features/shared/referrals/api';

const CREDIT_DISPLAY = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 0,
}).format(20);

export const copyReferralLink = async (
  summary: ReferralSummary | null,
  shareUrl: string,
): Promise<void> => {
  if (!summary) {
    return;
  }
  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      await navigator.clipboard.writeText(shareUrl);
    } else {
      const textarea = document.createElement('textarea');
      textarea.value = shareUrl;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'absolute';
      textarea.style.left = '-9999px';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }
    toast.success('Referral link copied');
  } catch {
    toast.error('Unable to copy link. Try again.');
  }
};

export const shareReferralLink = async (
  summary: ReferralSummary | null,
  shareUrl: string,
): Promise<void> => {
  if (!summary) {
    return;
  }
  const payload: ShareData = {
    title: 'Give $20, Get $20 on iNSTAiNSTRU',
    text: `Book your first $75+ lesson and get ${CREDIT_DISPLAY} off. Use my code ${summary.code}`,
    url: shareUrl,
  };
  const outcome = await shareOrCopy(payload, shareUrl);

  if (outcome === 'shared') {
    toast.success('Share sheet opened');
  } else if (outcome === 'copied') {
    toast.success('Referral link copied');
  } else {
    toast.error('Unable to share right now. Try copying the link instead.');
  }
};
