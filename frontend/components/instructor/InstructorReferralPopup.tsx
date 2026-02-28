'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { Check, Copy, Gift, Share2, Users, X } from 'lucide-react';

import { shareOrCopy } from '@/features/shared/referrals/share';
import { getClientStorageFlag, setClientStorageItem } from '@/lib/clientStorage';
import { copyToClipboard } from '@/lib/copy';
import { formatCents, useReferralPopupData } from '@/hooks/queries/useInstructorReferrals';

const POPUP_DISMISSED_KEY = 'instructor_referral_popup_dismissed';

interface InstructorReferralPopupProps {
  isLive: boolean;
}

export function InstructorReferralPopup({ isLive }: InstructorReferralPopupProps) {
  const [isVisible, setIsVisible] = useState(false);
  const [copied, setCopied] = useState(false);
  const showTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const dismissed = isLive ? getClientStorageFlag(POPUP_DISMISSED_KEY) : true;
  const shouldFetch = isLive && !dismissed;

  const { data: popupData } = useReferralPopupData(shouldFetch);

  useEffect(() => {
    if (!popupData || !shouldFetch) return;
    if (showTimerRef.current) {
      clearTimeout(showTimerRef.current);
    }
    showTimerRef.current = setTimeout(() => {
      setIsVisible(true);
    }, 1500);

    return () => {
      if (showTimerRef.current) {
        clearTimeout(showTimerRef.current);
      }
    };
  }, [popupData, shouldFetch]);

  useEffect(() => {
    return () => {
      if (copyTimerRef.current) {
        clearTimeout(copyTimerRef.current);
      }
    };
  }, []);

  const triggerCopied = () => {
    setCopied(true);
    if (copyTimerRef.current) {
      clearTimeout(copyTimerRef.current);
    }
    copyTimerRef.current = setTimeout(() => setCopied(false), 2000);
  };

  const handleDismiss = () => {
    setIsVisible(false);
    setClientStorageItem(POPUP_DISMISSED_KEY, 'true');
  };

  const handleCopyLink = async () => {
    if (!popupData?.referralLink) return;
    const ok = await copyToClipboard(popupData.referralLink);
    if (ok) {
      triggerCopied();
    }
  };

  const handleShare = async () => {
    if (!popupData?.referralLink) return;
    const payload: ShareData = {
      title: 'Join me on iNSTAiNSTRU',
      text: 'Sign up as an instructor on iNSTAiNSTRU and start teaching students in NYC.',
      url: popupData.referralLink,
    };
    const outcome = await shareOrCopy(payload, popupData.referralLink);
    if (outcome === 'shared') {
      handleDismiss();
      return;
    }
    if (outcome === 'copied') {
      triggerCopied();
    }
  };

  if (!isLive || !isVisible || !popupData) {
    return null;
  }

  const bonusAmount = formatCents(popupData.bonusAmountCents);
  const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function';
  return (
    <>
      <div
        className="fixed inset-0 bg-black/50 z-40 animate-fade-in"
        onClick={handleDismiss}
        data-testid="referral-popup-backdrop"
        aria-hidden="true"
      />

      <div
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        role="dialog"
        aria-modal="true"
        aria-labelledby="referral-popup-title"
      >
        <div
          className="bg-white rounded-2xl shadow-xl max-w-md w-full overflow-hidden animate-fade-in"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="bg-gradient-to-br from-[#7E22CE] to-[#5B17A6] p-6 text-white relative">
            <button
              type="button"
              onClick={handleDismiss}
              className="absolute top-4 right-4 p-1 rounded-full hover:bg-white/20 transition-colors"
              aria-label="Close"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>

            <div className="flex items-center gap-3 mb-3">
              <div className="p-2 bg-white/20 rounded-lg">
                <Gift className="h-6 w-6" aria-hidden="true" />
              </div>
              <h2 id="referral-popup-title" className="text-xl font-bold">
                Earn {bonusAmount} Per Referral
              </h2>
            </div>

            <p className="text-purple-100">
              {popupData.isFoundingPhase ? (
                <>
                  As a founding instructor, you can earn{' '}
                  <span className="font-semibold text-white">{bonusAmount}</span> for each instructor who completes
                  their first lesson.
                </>
              ) : (
                <>
                  Earn <span className="font-semibold text-white">{bonusAmount}</span> for each instructor who
                  completes their first lesson.
                </>
              )}
            </p>
          </div>

          {popupData.isFoundingPhase && (
            <div className="bg-amber-50 border-b border-amber-100 px-6 py-3">
              <p className="text-amber-800 text-sm font-medium flex items-center gap-2">
                <Users className="h-4 w-4" aria-hidden="true" />
                Only {popupData.foundingSpotsRemaining} founding spots left at {bonusAmount}.
              </p>
            </div>
          )}

          <div className="p-6">
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">Your referral link</label>
              <div className="flex items-center gap-2">
                <div className="flex-1 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2.5 font-mono text-sm text-gray-600 truncate">
                  {popupData.referralLink}
                </div>
                <button
                  type="button"
                  onClick={handleCopyLink}
                  className="flex-shrink-0 p-2.5 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                  aria-label={copied ? 'Copied' : 'Copy link'}
                >
                  {copied ? (
                    <Check className="h-5 w-5 text-green-600" aria-hidden="true" />
                  ) : (
                    <Copy className="h-5 w-5 text-gray-600" aria-hidden="true" />
                  )}
                </button>
              </div>
            </div>

            <div className="space-y-3">
              {canShare && (
                <button
                  type="button"
                  onClick={handleShare}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-[#7E22CE] hover:bg-[#6b1fb8] text-white font-semibold rounded-lg transition-colors"
                >
                  <Share2 className="h-5 w-5" aria-hidden="true" />
                  Share your link
                </button>
              )}

              <button
                type="button"
                onClick={handleCopyLink}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 border border-gray-200 text-gray-700 font-semibold rounded-lg transition-colors hover:bg-gray-50"
              >
                {copied ? (
                  <>
                    <Check className="h-5 w-5" aria-hidden="true" />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-5 w-5" aria-hidden="true" />
                    Copy link
                  </>
                )}
              </button>

              <button
                type="button"
                onClick={handleDismiss}
                className="w-full px-4 py-2 text-sm text-gray-500 hover:text-gray-700 transition-colors"
              >
                Maybe Later
              </button>
            </div>

            <p className="text-center text-sm text-gray-500 mt-4">
              <Link
                href="/instructor/dashboard?panel=referrals"
                className="text-[#7E22CE] font-semibold"
                onClick={handleDismiss}
              >
                View all referrals
              </Link>
            </p>
          </div>
        </div>
      </div>
    </>
  );
}

export default InstructorReferralPopup;
