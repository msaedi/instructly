'use client';

import { useCallback, useMemo, useState } from 'react';
import Link from 'next/link';
import { toast } from 'sonner';
import { Copy, Share2 } from 'lucide-react';
import Modal from '@/components/Modal';
import { shareOrCopy } from '@/features/shared/referrals/share';

interface ReferralShareModalProps {
  open: boolean;
  onClose: () => void;
  code: string;
  shareUrl: string;
}

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

const CREDIT_DISPLAY = currencyFormatter.format(20);

function ReferralShareModal({ open, onClose, code, shareUrl }: ReferralShareModalProps) {
  const [isProcessing, setIsProcessing] = useState<'share' | 'copy' | null>(null);

  const formattedSlug = useMemo(() => {
    try {
      const url = new URL(shareUrl);
      return `/r/${url.pathname.split('/').filter(Boolean).pop() ?? code}`;
    } catch {
      return `/r/${code}`;
    }
  }, [code, shareUrl]);

  const copyToClipboard = useCallback(async () => {
    setIsProcessing('copy');
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
      toast.error('Unable to copy link. Try copying manually.');
    } finally {
      setIsProcessing((current) => (current === 'copy' ? null : current));
    }
  }, [shareUrl]);

  const handleShare = useCallback(async () => {
    setIsProcessing('share');
    try {
      const payload: ShareData = {
        title: 'Give $20, Get $20 on Theta',
        text: `Your first $75+ lesson is ${CREDIT_DISPLAY} off. Use my code ${code}`,
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
    } finally {
      setIsProcessing((current) => (current === 'share' ? null : current));
    }
  }, [code, shareUrl]);

  return (
    <Modal
      isOpen={open}
      onClose={onClose}
      title="🎉 Loved your lesson? Give $20, Get $20"
      size="md"
    >
      <div className="space-y-6">
        <p className="text-sm text-gray-600">
          Invite a friend and you each earn {CREDIT_DISPLAY} in Theta credits when they book their first $75+ lesson within 30 days.
        </p>

        <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
          <p className="text-xs uppercase tracking-[0.08em] text-gray-500">Share your link</p>
          <p className="mt-1 font-semibold text-gray-900" aria-label="Referral link">
            {shareUrl}
          </p>
          <p className="mt-2 text-xs text-gray-500">Direct shortcut: {formattedSlug}</p>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row">
          <button
            type="button"
            onClick={handleShare}
            disabled={isProcessing !== null}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#7E22CE] px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-[#6b1fb8] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-80"
            aria-label="Share referral link"
          >
            <Share2 className="h-4 w-4" aria-hidden="true" />
            Share
          </button>

          <button
            type="button"
            onClick={copyToClipboard}
            disabled={isProcessing !== null}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-semibold text-gray-700 shadow-sm transition hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-80"
            aria-label="Copy referral link"
          >
            <Copy className="h-4 w-4" aria-hidden="true" />
            Copy
          </button>

          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-transparent bg-gray-100 px-4 py-2 text-sm font-semibold text-gray-700 transition hover:bg-gray-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE] focus-visible:ring-offset-2"
          >
            Close
          </button>
        </div>

        <p className="text-xs leading-5 text-gray-500">
          If your friend books, you both receive Theta credits.{' '}
          <Link href="/legal/referrals-terms" className="font-medium text-[#7E22CE] underline" onClick={onClose}>
            Terms apply
          </Link>
          .
        </p>
      </div>
    </Modal>
  );
}

export default ReferralShareModal;
