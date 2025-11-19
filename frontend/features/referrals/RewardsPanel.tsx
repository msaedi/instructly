'use client';

import { memo, useCallback, useMemo, useState, useEffect } from 'react';
import { Gift, Share2, Copy, Clock, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';
// Use project-local SWR helper to avoid missing type dep on swr
import { toReferralSummary, type ReferralLedger, type ReferralSummary, type RewardOut } from '@/features/shared/referrals/api';
import {
  fetchReferralLedgerCached,
  getCachedReferralLedger,
  primeReferralLedgerCache,
  invalidateReferralLedgerCache,
} from '@/features/shared/referrals/cache';
import { shareOrCopy } from '@/features/shared/referrals/share';
import InviteByEmail from '@/features/referrals/InviteByEmail';

type TabKey = 'unlocked' | 'pending' | 'redeemed';

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0 });
const dateFormatter = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
const CREDIT_DISPLAY = usd.format(20);

function formatCents(amount: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount / 100);
}

function computeExpiryBadge(reward: RewardOut) {
  if (!reward.expire_ts) {
    return null;
  }
  const now = Date.now();
  const expire = new Date(reward.expire_ts).getTime();
  if (Number.isNaN(expire)) {
    return null;
  }
  const diffDays = Math.ceil((expire - now) / (1000 * 60 * 60 * 24));
  if (diffDays <= 0) {
    return { tone: 'danger', label: 'Expired' } as const;
  }
  if (diffDays <= 3) {
    return { tone: 'danger', label: `Expires in ${diffDays} day${diffDays === 1 ? '' : 's'}` } as const;
  }
  if (diffDays <= 14) {
    return { tone: 'warn', label: `Expires in ${diffDays} days` } as const;
  }
  return { tone: 'neutral', label: `Expires on ${dateFormatter.format(new Date(reward.expire_ts))}` } as const;
}

const emptyCopy: Record<TabKey, string> = {
  unlocked: 'You have no unlocked rewards yet. Share your link to start earning credits.',
  pending: 'No pending rewards yet. When a friend books, their status appears here.',
  redeemed: 'Redeemed rewards will show here once used at checkout.',
};

type RewardsPanelProps = {
  inviterName?: string;
  hideHeader?: boolean;
  compactShare?: boolean;
  hideShareIcon?: boolean;
  minimalTabs?: boolean;
  compactInvite?: boolean;
  compactTabs?: boolean;
  freezeCache?: boolean;
  initialLedger?: ReferralLedger | null;
  disableFetch?: boolean;
  externalError?: string | null;
};

function RewardsPanelComponent({
  inviterName,
  hideHeader = false,
  compactShare = false,
  hideShareIcon = false,
  minimalTabs = false,
  compactInvite = false,
  compactTabs = false,
  freezeCache = false,
  initialLedger = null,
  disableFetch = false,
  externalError = null,
}: RewardsPanelProps = {}) {
  const cacheSnapshot = initialLedger ?? getCachedReferralLedger();
  const [activeTab, setActiveTab] = useState<TabKey>('unlocked');
  const [isProcessing, setIsProcessing] = useState<'share' | 'copy' | null>(null);
  const [ledger, setLedger] = useState<ReferralLedger | null>(() => cacheSnapshot);
  const [isLoading, setIsLoading] = useState(() => !cacheSnapshot);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [hasLoaded, setHasLoaded] = useState(() => Boolean(cacheSnapshot));

  useEffect(() => {
    if (initialLedger) {
      setLedger(initialLedger);
      setHasLoaded(true);
      setIsLoading(false);
      setLoadError(null);
      return;
    }

    if (ledger) {
      if (!hasLoaded) {
        setHasLoaded(true);
      }
      return;
    }

    if (freezeCache && hasLoaded) {
      return;
    }

    if (disableFetch) {
      return;
    }

    let cancelled = false;
    const load = async () => {
      setIsLoading(true);
      setLoadError(null);
      try {
        const result = await fetchReferralLedgerCached();
        if (cancelled) return;
        setLedger(result);
        setHasLoaded(true);
        primeReferralLedgerCache(result);
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : 'Failed to load rewards';
        setLoadError(message);
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [ledger, freezeCache, hasLoaded, isLoading, initialLedger, disableFetch]);

  const handleRetryLoad = useCallback(() => {
    if (isLoading || (freezeCache && hasLoaded) || disableFetch) return;
    invalidateReferralLedgerCache();
    primeReferralLedgerCache(null);
    setLoadError(null);
    setHasLoaded(false);
    setLedger(null);
  }, [isLoading, freezeCache, hasLoaded, disableFetch]);

  const summary = useMemo<ReferralSummary | null>(() => {
    if (!ledger) {
      return null;
    }
    return toReferralSummary(ledger);
  }, [ledger]);

  const shareUrl = summary?.share_url ?? '';

  // formattedSlug previously shown under the link; no longer displayed

  const rewardsForTab = useMemo<RewardOut[]>(() => {
    if (!summary) {
      return [];
    }

    switch (activeTab) {
      case 'pending':
        return summary.pending;
      case 'redeemed':
        return summary.redeemed;
      case 'unlocked':
      default:
        return summary.unlocked;
    }
  }, [activeTab, summary]);

  const handleCopy = useCallback(async () => {
    if (!summary) return;
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
      toast.error('Unable to copy link. Try again.');
    } finally {
      setIsProcessing((state) => (state === 'copy' ? null : state));
    }
  }, [shareUrl, summary]);

  const handleShare = useCallback(async () => {
    if (!summary) return;
    setIsProcessing('share');
    try {
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
    } finally {
      setIsProcessing((state) => (state === 'share' ? null : state));
    }
  }, [shareUrl, summary]);

  return (
    <main className="space-y-8">
      {!hideHeader && (
        <header className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Your rewards</h1>
            <p className="mt-2 text-sm text-gray-600">
              Share your link and you both receive iNSTAiNSTRU credits when a friend books their first lesson.
            </p>
          </div>
        </header>
      )}

      <section className={`${compactShare ? '' : 'rounded-2xl border border-gray-200 bg-white p-6 shadow-sm'}`}>
        <div className={`flex flex-col gap-4 sm:flex-row sm:items-end sm:gap-4 ${compactShare ? 'p-0' : ''}`}>
          <div className={`flex items-start gap-3 ${hideShareIcon ? 'flex-1 min-w-0' : ''}`}>
            {!hideShareIcon && (
              <span className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-[#7E22CE]/10 text-[#7E22CE]">
                <Gift className="h-6 w-6" aria-hidden="true" />
              </span>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-700">Share your link</p>
              <input
                readOnly
                value={summary ? shareUrl : ''}
                placeholder="Loading…"
                className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-800"
                aria-label="Referral link"
              />
            </div>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row flex-shrink-0">
            <button
              type="button"
              onClick={handleShare}
              disabled={!summary || isProcessing !== null}
              className="inline-flex items-center justify-center gap-2 rounded-md bg-white border border-purple-200 text-[#7E22CE] px-4 py-2 text-sm font-semibold transition hover:bg-purple-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Share2 className="h-4 w-4" aria-hidden="true" />
              Share
            </button>
            <button
              type="button"
              onClick={handleCopy}
              disabled={!summary || isProcessing !== null}
              className="inline-flex items-center justify-center gap-2 rounded-md bg-[#7E22CE] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#6b1fb8] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Copy className="h-4 w-4" aria-hidden="true" />
              Copy
            </button>
          </div>
        </div>
      </section>

      {summary && (
        <section className={`${compactInvite ? '' : 'rounded-2xl border border-gray-200 bg-white p-6 shadow-sm'}`}>
          <InviteByEmail shareUrl={shareUrl} {...(inviterName ? { fromName: inviterName } : {})} />
        </section>
      )}

      <section className={`${compactTabs ? '' : 'rounded-2xl border border-gray-200 bg-white p-6 shadow-sm'}`}>
        <div className={`flex flex-wrap items-center ${minimalTabs ? 'gap-4' : 'gap-2'} border-b border-gray-200 ${minimalTabs ? 'pb-2' : 'pb-4'}`}>
          {(['unlocked', 'pending', 'redeemed'] as TabKey[]).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={
                minimalTabs
                  ? `px-0 py-0 text-sm font-medium transition ${activeTab === tab ? 'text-[#7E22CE]' : 'text-gray-600 hover:text-[#7E22CE]'}`
                  : `rounded-full px-4 py-2 text-sm font-medium transition ${
                      activeTab === tab ? 'bg-[#7E22CE] text-white shadow-sm' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`
              }
              aria-pressed={activeTab === tab}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>

        <div className="mt-5 space-y-4">
          {isLoading && !hasLoaded && (
            <div className="flex items-center gap-3 text-sm text-gray-500">
              <Clock className="h-4 w-4 animate-spin" aria-hidden="true" />
              Loading rewards…
            </div>
          )}

          {externalError && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{externalError}</div>
          )}

          {loadError && !isLoading && !externalError && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <span>{loadError}</span>
                <button
                  type="button"
                  onClick={handleRetryLoad}
                  className="inline-flex items-center justify-center rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2"
                >
                  Retry
                </button>
              </div>
            </div>
          )}

          {!isLoading && hasLoaded && !loadError && rewardsForTab.length === 0 && (
            <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-6 text-center text-sm text-gray-600">
              {emptyCopy[activeTab]}
            </div>
          )}

          {rewardsForTab.map((reward) => {
            const badge = computeExpiryBadge(reward);
            return (
              <article
                key={reward.id}
                className="flex flex-col gap-3 rounded-xl border border-gray-200 bg-white px-4 py-4 shadow-sm sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <p className="text-lg font-semibold text-gray-900">{formatCents(reward.amount_cents)}</p>
                  <p className="text-sm text-gray-600">
                    {reward.status === 'pending' && 'Pending — credits unlock after your friend completes their first lesson.'}
                    {reward.status === 'unlocked' && 'Unlocked — ready to apply at checkout.'}
                    {reward.status === 'redeemed' && 'Redeemed — already applied to a past booking.'}
                    {reward.status === 'void' && 'Expired or cancelled reward.'}
                  </p>
                  <p className="mt-2 text-xs text-gray-500">
                    Earned {dateFormatter.format(new Date(reward.created_at))}
                    {reward.unlock_ts && reward.status !== 'unlocked' && ` • Unlocks ${dateFormatter.format(new Date(reward.unlock_ts))}`}
                  </p>
                </div>
                <div className="flex flex-col items-start gap-2 sm:items-end">
                  {badge && (
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold ${
                        badge.tone === 'danger'
                          ? 'bg-red-100 text-red-700'
                          : badge.tone === 'warn'
                            ? 'bg-amber-100 text-amber-700'
                            : 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      <Clock className="h-3 w-3" aria-hidden="true" />
                      {badge.label}
                    </span>
                  )}
                  {reward.status === 'redeemed' && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-700">
                      <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                      Applied
                    </span>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      </section>

      {/* Footer terms removed per embedded design */}
    </main>
  );
}

export default memo(RewardsPanelComponent);
