'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, Check, Clock, Copy, DollarSign, ExternalLink, Gift, Users } from 'lucide-react';
import { toast } from 'sonner';

import UserProfileDropdown from '@/components/UserProfileDropdown';
import { shareOrCopy } from '@/features/shared/referrals/share';
import {
  formatCents,
  getPayoutStatusDisplay,
  useInstructorReferralStats,
  useReferredInstructors,
} from '@/hooks/queries/useInstructorReferrals';

import { useEmbedded } from '../_embedded/EmbeddedContext';

const badgeStyles: Record<'gray' | 'yellow' | 'blue' | 'green' | 'red', string> = {
  gray: 'bg-gray-100 text-gray-700',
  yellow: 'bg-yellow-100 text-yellow-700',
  blue: 'bg-blue-100 text-blue-700',
  green: 'bg-green-100 text-green-700',
  red: 'bg-red-100 text-red-700',
};

const formatDate = (value: Date | null) => {
  if (!value) return '—';
  return value.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
};

async function copyToClipboard(text: string) {
  if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'absolute';
  textarea.style.left = '-9999px';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  document.body.removeChild(textarea);
}

export default function InstructorReferralsPage() {
  const embedded = useEmbedded();
  const { data: stats, isLoading: statsLoading, error: statsError } = useInstructorReferralStats();
  const {
    data: referredData,
    isLoading: referredLoading,
    error: referredError,
  } = useReferredInstructors({ limit: 50 });
  const [copied, setCopied] = useState(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const triggerCopied = useCallback(() => {
    setCopied(true);
    if (copyTimerRef.current) {
      clearTimeout(copyTimerRef.current);
    }
    copyTimerRef.current = setTimeout(() => setCopied(false), 2000);
  }, []);

  useEffect(() => {
    return () => {
      if (copyTimerRef.current) {
        clearTimeout(copyTimerRef.current);
      }
    };
  }, []);

  const handleCopyLink = async () => {
    if (!stats?.referralLink) return;
    try {
      await copyToClipboard(stats.referralLink);
      triggerCopied();
      toast.success('Referral link copied');
    } catch {
      toast.error('Unable to copy link. Try again.');
    }
  };

  const handleShare = async () => {
    if (!stats?.referralLink) return;
    const payload: ShareData = {
      title: 'Teach on iNSTAiNSTRU',
      text: 'Join iNSTAiNSTRU as an instructor and earn more students in NYC.',
      url: stats.referralLink,
    };
    const outcome = await shareOrCopy(payload, stats.referralLink);
    if (outcome === 'shared') {
      toast.success('Share sheet opened');
    } else if (outcome === 'copied') {
      triggerCopied();
      toast.success('Referral link copied');
    } else {
      toast.error('Unable to share right now.');
    }
  };

  if (statsLoading) {
    return (
      <div className="min-h-screen">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="animate-pulse space-y-6">
            <div className="h-8 bg-gray-200 rounded w-1/3" />
            <div className="h-28 bg-gray-200 rounded" />
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="h-24 bg-gray-200 rounded" />
              <div className="h-24 bg-gray-200 rounded" />
              <div className="h-24 bg-gray-200 rounded" />
            </div>
            <div className="h-64 bg-gray-200 rounded" />
          </div>
        </div>
      </div>
    );
  }

  if (statsError || !stats) {
    return (
      <div className="min-h-screen">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-800">Failed to load referral data. Please try again later.</p>
          </div>
        </div>
      </div>
    );
  }

  const referredCount = referredData?.totalCount ?? 0;
  const referredItems = referredData?.instructors ?? [];

  const foundingMessage = stats.isFoundingPhase ? (
    <div className="bg-gradient-to-r from-purple-50 to-white border border-purple-200 rounded-xl p-4">
      <div className="flex items-start gap-3">
        <Gift className="h-5 w-5 text-[#7E22CE] mt-0.5" />
        <div>
          <h3 className="font-semibold text-[#4B1178]">Founding Phase Bonus</h3>
          <p className="text-sm text-purple-900 mt-1">
            Earn <span className="font-semibold">{formatCents(stats.currentBonusCents)}</span> per referral while
            founding spots remain. Only{' '}
            <span className="font-semibold">{stats.foundingSpotsRemaining}</span> left.
          </p>
        </div>
      </div>
    </div>
  ) : null;

  return (
    <div className="min-h-screen">
      {!embedded && (
        <header className="relative bg-white backdrop-blur-sm border-b border-gray-200 px-4 sm:px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <Link href="/instructor/dashboard" className="inline-block">
              <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-0 sm:pl-4">
                iNSTAiNSTRU
              </h1>
            </Link>
            <div className="pr-0 sm:pr-4">
              <UserProfileDropdown />
            </div>
          </div>
          <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 hidden sm:block">
            <div className="container mx-auto px-8 lg:px-32 max-w-6xl pointer-events-none">
              <Link
                href="/instructor/dashboard"
                className="inline-flex items-center gap-1 text-[#7E22CE] pointer-events-auto"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>Back to dashboard</span>
              </Link>
            </div>
          </div>
        </header>
      )}

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        <div>
          <h2 className="text-2xl font-semibold text-gray-900">Refer Instructors</h2>
          <p className="text-gray-600 mt-1">
            Earn {formatCents(stats.currentBonusCents)} for each instructor you refer who completes their first lesson.
          </p>
        </div>

        {foundingMessage}

        <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <h3 className="text-sm uppercase tracking-wide text-gray-500">Your referral link</h3>
              <p className="mt-2 text-sm font-semibold text-gray-900 break-all">{stats.referralLink}</p>
              <p className="mt-1 text-xs text-gray-500">Code: {stats.referralCode}</p>
            </div>
            <div className="flex flex-col sm:flex-row gap-2">
              <button
                type="button"
                onClick={handleCopyLink}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#7E22CE] px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-[#6b1fb8]"
              >
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                {copied ? 'Copied' : 'Copy link'}
              </button>
              <button
                type="button"
                onClick={handleShare}
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-semibold text-gray-700 shadow-sm transition hover:bg-gray-50 sm:hidden"
              >
                <ExternalLink className="h-4 w-4" />
                Share
              </button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-purple-100 rounded-lg">
                <Users className="h-5 w-5 text-[#7E22CE]" />
              </div>
              <div>
                <p className="text-sm text-gray-500">Total referred</p>
                <p className="text-2xl font-semibold text-gray-900">{stats.totalReferred}</p>
              </div>
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-yellow-100 rounded-lg">
                <Clock className="h-5 w-5 text-yellow-600" />
              </div>
              <div>
                <p className="text-sm text-gray-500">Pending payouts</p>
                <p className="text-2xl font-semibold text-gray-900">{stats.pendingPayouts}</p>
                <p className="text-xs text-gray-500">{stats.completedPayouts} paid out</p>
              </div>
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-green-100 rounded-lg">
                <DollarSign className="h-5 w-5 text-green-600" />
              </div>
              <div>
                <p className="text-sm text-gray-500">Total earned</p>
                <p className="text-2xl font-semibold text-gray-900">{formatCents(stats.totalEarnedCents)}</p>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl shadow-sm">
          <div className="p-4 border-b border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900">Referred instructors</h3>
            <p className="text-sm text-gray-500 mt-1">{referredCount} total referrals</p>
          </div>

          {referredLoading ? (
            <div className="p-4 space-y-3">
              {[1, 2, 3].map((item) => (
                <div key={item} className="animate-pulse flex items-center gap-4">
                  <div className="h-10 w-10 bg-gray-200 rounded-full" />
                  <div className="flex-1 space-y-2">
                    <div className="h-4 bg-gray-200 rounded w-1/3" />
                    <div className="h-3 bg-gray-200 rounded w-1/4" />
                  </div>
                </div>
              ))}
            </div>
          ) : referredError ? (
            <div className="p-4 text-sm text-red-600">Unable to load referrals. Please try again.</div>
          ) : referredItems.length === 0 ? (
            <div className="p-8 text-center">
              <Users className="h-10 w-10 text-gray-300 mx-auto mb-3" />
              <p className="text-gray-600">No referrals yet</p>
              <p className="text-sm text-gray-400 mt-1">Share your link to start earning.</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {referredItems.map((instructor) => {
                const status = getPayoutStatusDisplay(instructor.payoutStatus);
                const timelineText = instructor.firstLessonCompletedAt
                  ? `First lesson ${formatDate(instructor.firstLessonCompletedAt)}`
                  : instructor.isLive
                    ? `Live since ${formatDate(instructor.wentLiveAt)}`
                    : 'Not live yet';

                return (
                  <div key={instructor.id} className="p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 bg-purple-100 rounded-full flex items-center justify-center">
                        <span className="text-[#7E22CE] font-semibold">
                          {instructor.firstName[0]}
                          {instructor.lastInitial}
                        </span>
                      </div>
                      <div>
                        <p className="font-medium text-gray-900">
                          {instructor.firstName} {instructor.lastInitial}.
                        </p>
                        <p className="text-sm text-gray-500">Referred {formatDate(instructor.referredAt)}</p>
                        <p className="text-xs text-gray-400">{timelineText}</p>
                      </div>
                    </div>

                    <div className="flex items-center gap-3 justify-between sm:justify-end">
                      {instructor.payoutStatus === 'paid' && instructor.payoutAmountCents ? (
                        <span className="text-green-600 font-semibold">
                          +{formatCents(instructor.payoutAmountCents)}
                        </span>
                      ) : null}
                      <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${badgeStyles[status.color]}`}>
                        {status.label}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="bg-gray-50 border border-gray-200 rounded-xl p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">How it works</h3>
          <ol className="space-y-3 text-gray-700">
            <li className="flex items-start gap-3">
              <span className="flex-shrink-0 h-6 w-6 bg-[#7E22CE] text-white rounded-full flex items-center justify-center text-sm font-semibold">
                1
              </span>
              Share your unique referral link with other instructors.
            </li>
            <li className="flex items-start gap-3">
              <span className="flex-shrink-0 h-6 w-6 bg-[#7E22CE] text-white rounded-full flex items-center justify-center text-sm font-semibold">
                2
              </span>
              They sign up and go live on iNSTAiNSTRU.
            </li>
            <li className="flex items-start gap-3">
              <span className="flex-shrink-0 h-6 w-6 bg-[#7E22CE] text-white rounded-full flex items-center justify-center text-sm font-semibold">
                3
              </span>
              When they complete their first lesson, you earn {formatCents(stats.currentBonusCents)}.
            </li>
          </ol>
        </div>
      </div>
    </div>
  );
}
