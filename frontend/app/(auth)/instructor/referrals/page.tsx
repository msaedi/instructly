'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft,
  Check,
  Copy,
  Gift,
  Share2,
  UserRoundPlus,
  Users,
  Wallet,
} from 'lucide-react';
import { toast } from 'sonner';

import UserProfileDropdown from '@/components/UserProfileDropdown';
import { SectionHeroCard } from '@/components/dashboard/SectionHeroCard';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import InviteByEmail from '@/features/referrals/InviteByEmail';
import { shareOrCopy } from '@/features/shared/referrals/share';
import {
  formatCents,
  formatReferralDisplayName,
  formatReferralRewardDate,
  getEmptyRewardMessage,
  getReferralRewardTypeLabel,
  type InstructorReferralReward,
  type ReferralRewardTab,
  useInstructorReferralDashboard,
} from '@/hooks/queries/useInstructorReferrals';
import { copyToClipboard } from '@/lib/copy';
import { getTextWidthTabButtonClasses, getTextWidthTabLabelClasses } from '@/lib/textWidthTabs';
import { cn } from '@/lib/utils';

import { useEmbedded } from '../_embedded/EmbeddedContext';

const REWARD_TABS: ReferralRewardTab[] = ['unlocked', 'pending', 'redeemed'];

const HOW_IT_WORKS_STEPS = [
  'Share your unique referral link with students or fellow instructors.',
  'They sign up and join iNSTAiNSTRU.',
  'When they complete their first lesson, you earn your reward.',
];

function InsetDivider() {
  return (
    <div className="px-6 sm:px-8" aria-hidden="true">
      <div className="border-t border-gray-200 dark:border-gray-700" />
    </div>
  );
}

function RewardOfferCard({
  title,
  amount,
}: {
  title: string;
  amount: string;
}) {
  return (
    <Card className="insta-surface-card border-gray-200/80 shadow-none">
      <CardContent className="flex h-full items-start justify-between gap-4 p-6">
        <div className="space-y-2">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{title}</h3>
          <p className="max-w-xs text-sm leading-6 text-gray-600 dark:text-gray-400">
            Paid via Stripe when they complete their first lesson.
          </p>
        </div>
        <Badge variant="success" className="shrink-0 px-3 py-1 text-sm font-semibold">
          {amount} cash
        </Badge>
      </CardContent>
    </Card>
  );
}

function StatTile({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: typeof Users;
}) {
  return (
    <Card className="insta-surface-card border-gray-200/80 shadow-none">
      <CardContent className="flex items-start justify-between gap-4 p-6">
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-gray-500 dark:text-gray-400">
            {label}
          </p>
          <p className="text-3xl font-semibold text-gray-900 dark:text-gray-100">{value}</p>
        </div>
        <div className="flex h-11 w-11 items-center justify-center rounded-full bg-gray-100 text-[#7E22CE] dark:bg-gray-800">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </div>
      </CardContent>
    </Card>
  );
}

function formatPayoutStatus(status: string | null): string | null {
  switch (status) {
    case 'paid':
      return 'Transferred';
    case 'failed':
      return 'Needs attention';
    case 'pending':
      return 'Transfer pending';
    default:
      return null;
  }
}

function RewardRow({ reward }: { reward: InstructorReferralReward }) {
  const payoutStatus = formatPayoutStatus(reward.payoutStatus);

  return (
    <li className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900/60">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {formatReferralDisplayName(reward.refereeFirstName, reward.refereeLastInitial)}
            </p>
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
              {getReferralRewardTypeLabel(reward.referralType)}
            </span>
          </div>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {formatReferralRewardDate(reward.date)}
          </p>
          {reward.failureReason ? (
            <p className="text-sm text-red-600 dark:text-red-400">{reward.failureReason}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:justify-end">
          {payoutStatus ? (
            <Badge
              variant={reward.payoutStatus === 'failed' ? 'destructive' : 'secondary'}
              className="px-2.5 py-1 text-[11px] font-semibold"
            >
              {payoutStatus}
            </Badge>
          ) : null}
          <Badge variant="outline" className="border-gray-200 px-2.5 py-1 text-sm font-semibold dark:border-gray-700">
            {formatCents(reward.amountCents)}
          </Badge>
        </div>
      </div>
    </li>
  );
}

function RewardsSection({
  activeTab,
  onTabChange,
  rewards,
}: {
  activeTab: ReferralRewardTab;
  onTabChange: (tab: ReferralRewardTab) => void;
  rewards: InstructorReferralReward[];
}) {
  return (
    <Card className="insta-surface-card border-gray-200/80 shadow-none">
      <div className="px-6 py-6 sm:px-8">
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Your rewards</h2>
          <div
            role="tablist"
            aria-label="Referral reward tabs"
            className="flex flex-wrap gap-5 border-b border-gray-200 pb-2 dark:border-gray-700"
          >
            {REWARD_TABS.map((tab) => (
              <button
                key={tab}
                type="button"
                role="tab"
                aria-selected={activeTab === tab}
                className={cn('text-sm font-medium transition-colors', getTextWidthTabButtonClasses(activeTab === tab))}
                onClick={() => onTabChange(tab)}
              >
                <span className={getTextWidthTabLabelClasses(activeTab === tab)}>
                  {tab.charAt(0).toUpperCase() + tab.slice(1)}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
      <InsetDivider />
      <div className="px-6 py-5 sm:px-8">
        {rewards.length ? (
          <ul className="space-y-3">
            {rewards.map((reward) => (
              <RewardRow key={reward.id} reward={reward} />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-600 dark:text-gray-400">{getEmptyRewardMessage(activeTab)}</p>
        )}
      </div>
    </Card>
  );
}

function HowItWorksSection() {
  return (
    <Card className="insta-surface-card border-gray-200/80 shadow-none">
      <CardContent className="space-y-5 p-6 sm:p-8">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">How it works</h2>
        <ol className="space-y-4">
          {HOW_IT_WORKS_STEPS.map((step, index) => (
            <li key={step} className="flex items-start gap-4">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-100 text-sm font-semibold text-[#7E22CE] dark:bg-gray-800">
                {index + 1}
              </span>
              <p className="pt-1 text-sm leading-6 text-gray-700 dark:text-gray-300">{step}</p>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

function LoadingState() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="h-36 animate-pulse rounded-xl bg-gray-200 dark:bg-gray-800" />
        <div className="h-36 animate-pulse rounded-xl bg-gray-200 dark:bg-gray-800" />
      </div>
      <div className="h-56 animate-pulse rounded-xl bg-gray-200 dark:bg-gray-800" />
      <div className="grid gap-4 md:grid-cols-3">
        <div className="h-32 animate-pulse rounded-xl bg-gray-200 dark:bg-gray-800" />
        <div className="h-32 animate-pulse rounded-xl bg-gray-200 dark:bg-gray-800" />
        <div className="h-32 animate-pulse rounded-xl bg-gray-200 dark:bg-gray-800" />
      </div>
      <div className="h-64 animate-pulse rounded-xl bg-gray-200 dark:bg-gray-800" />
      <div className="h-56 animate-pulse rounded-xl bg-gray-200 dark:bg-gray-800" />
    </div>
  );
}

export default function InstructorReferralsPage() {
  const embedded = useEmbedded();
  const { data: dashboard, isLoading, isError } = useInstructorReferralDashboard();
  const [activeTab, setActiveTab] = useState<ReferralRewardTab>('unlocked');
  const [copied, setCopied] = useState(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const referralLink = dashboard?.referralLink ?? null;

  const activeRewards = useMemo(
    () => dashboard?.rewards[activeTab] ?? [],
    [activeTab, dashboard]
  );

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

  const handleCopy = async () => {
    if (!referralLink) {
      return;
    }

    const success = await copyToClipboard(referralLink);
    if (success) {
      triggerCopied();
      toast.success('Referral link copied');
      return;
    }

    toast.error('Unable to copy referral link right now.');
  };

  const handleShare = async () => {
    if (!referralLink) {
      return;
    }

    const outcome = await shareOrCopy(
      {
        title: 'Join iNSTAiNSTRU',
        text: 'Join iNSTAiNSTRU and complete your first lesson to unlock your referral reward.',
        url: referralLink,
      },
      referralLink
    );

    if (outcome === 'shared') {
      toast.success('Share sheet opened');
      return;
    }

    if (outcome === 'copied') {
      triggerCopied();
      toast.success('Referral link copied');
      return;
    }

    toast.error('Unable to share right now.');
  };

  return (
    <div className="min-h-screen insta-dashboard-page">
      {!embedded && (
        <header className="relative px-4 py-4 sm:px-6 insta-dashboard-header">
          <div className="flex max-w-full items-center justify-between">
            <Link href="/instructor/dashboard" className="inline-block">
              <h1 className="pl-0 text-3xl font-bold text-[#7E22CE] transition-colors hover:text-purple-900 dark:hover:text-purple-300 sm:pl-4">
                iNSTAiNSTRU
              </h1>
            </Link>
            <div className="pr-0 sm:pr-4">
              <UserProfileDropdown />
            </div>
          </div>
          <div className="pointer-events-none absolute inset-x-0 top-1/2 hidden -translate-y-1/2 sm:block">
            <div className="pointer-events-auto container mx-auto max-w-6xl px-8 lg:px-32">
              <Link href="/instructor/dashboard" className="inline-flex items-center gap-1 text-[#7E22CE]">
                <ArrowLeft className="h-4 w-4" />
                <span>Back to dashboard</span>
              </Link>
            </div>
          </div>
        </header>
      )}

      <div className={embedded ? 'max-w-none px-0 py-0' : 'container mx-auto max-w-6xl px-8 py-8 lg:px-32'}>
        {!embedded && (
          <div className="mb-2 sm:hidden">
            <Link
              href="/instructor/dashboard"
              aria-label="Back to dashboard"
              className="inline-flex items-center gap-1 text-[#7E22CE]"
            >
              <ArrowLeft className="h-5 w-5" />
              <span className="sr-only">Back to dashboard</span>
            </Link>
          </div>
        )}

        <SectionHeroCard
          id={embedded ? 'referrals-first-card' : undefined}
          icon={Gift}
          title="Referrals"
          subtitle="Share iNSTAiNSTRU with students and instructors, then track every reward in one place."
        />

        {isLoading ? (
          <LoadingState />
        ) : isError || !dashboard ? (
          <Card className="border-red-200 bg-red-50 shadow-none dark:border-red-900/60 dark:bg-red-950/30">
            <CardContent className="p-6">
              <p className="text-sm text-red-700 dark:text-red-300">
                Failed to load referrals right now. Please try again in a moment.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2">
              <RewardOfferCard
                title="Refer an instructor"
                amount={formatCents(dashboard.instructorAmountCents)}
              />
              <RewardOfferCard
                title="Refer a student"
                amount={formatCents(dashboard.studentAmountCents)}
              />
            </div>

            <Card className="insta-surface-card border-gray-200/80 shadow-none">
              <div className="space-y-6 px-6 py-6 sm:px-8">
                <div className="space-y-3">
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                    Your referral link
                  </h2>
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                    <Input
                      aria-label="Your referral link"
                      value={dashboard.referralLink}
                      readOnly
                      className="h-11 flex-1 border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-900"
                    />
                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        aria-label="Copy referral link"
                        onClick={handleCopy}
                      >
                        {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        aria-label="Share referral link"
                        onClick={handleShare}
                      >
                        <Share2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </div>

                <InsetDivider />

                <InviteByEmail
                  shareUrl={dashboard.referralLink}
                  label="Invite by email"
                  helperText="Up to 10 at a time. Separate with commas or spaces."
                  buttonText="Send Invites"
                />
              </div>
            </Card>

            <div className="grid gap-4 md:grid-cols-3">
              <StatTile label="Total referred" value={String(dashboard.totalReferred)} icon={Users} />
              <StatTile label="Pending payouts" value={String(dashboard.pendingPayouts)} icon={Wallet} />
              <StatTile label="Total earned" value={formatCents(dashboard.totalEarnedCents)} icon={UserRoundPlus} />
            </div>

            <RewardsSection
              activeTab={activeTab}
              onTabChange={setActiveTab}
              rewards={activeRewards}
            />

            <HowItWorksSection />
          </div>
        )}
      </div>
    </div>
  );
}
