'use client';

import { Check, Star } from 'lucide-react';

import { useCommissionStatus } from '@/hooks/queries/useCommissionStatus';
import type { TierInfo } from '@/src/api/services/instructors';

const FOUNDING_DESCRIPTION =
  "You have locked in our lowest rate—permanently. Whatever the floor is, you're on it.";
const FOUNDING_COMMITMENT_LABEL = 'Availability commitment to maintain your rate';
const FOUNDING_COMMITMENT_DETAIL =
  '10 hours per week · 3+ days · 8am–8pm · measured monthly (40 hrs/month)';

function formatPercent(value: number): string {
  return Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1);
}

function formatRangeLabel(tier: TierInfo): string {
  if (tier.max_lessons == null) {
    return `${tier.min_lessons}+ lessons`;
  }
  return `${tier.min_lessons}–${tier.max_lessons} lessons`;
}

function resolveCurrentTier(
  tierName: string,
  tiers: TierInfo[]
): { display_name: string; commission_pct: number } {
  const match = tiers.find((tier) => tier.name === tierName);
  if (match) {
    return match;
  }
  return {
    display_name: tierName.charAt(0).toUpperCase() + tierName.slice(1),
    commission_pct: 0,
  };
}

function LadderCircle({
  label,
  isCurrent,
  isLocked,
}: {
  label: string;
  isCurrent: boolean;
  isLocked: boolean;
}) {
  if (isCurrent) {
    return (
      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#8B7CF6] text-white shadow-[0_8px_18px_rgba(139,124,246,0.2)]">
        <Check className="h-4 w-4" aria-hidden="true" />
      </div>
    );
  }

  return (
    <div
      className={`flex h-9 w-9 items-center justify-center rounded-full border text-sm font-medium ${
        isLocked
          ? 'border-gray-200 bg-white text-gray-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-500'
          : 'border-[#D8CFEE] bg-[#FAF7FF] text-gray-700 dark:border-[#5D4C92] dark:bg-[#231A38] dark:text-gray-200'
      }`}
    >
      {label}
    </div>
  );
}

export default function CommissionTierCard() {
  const { data, isLoading, error } = useCommissionStatus(true);

  if (isLoading || error || !data) {
    return null;
  }

  const tiers = Array.isArray(data.tiers) ? data.tiers : [];
  const currentTier = resolveCurrentTier(data.tier_name, tiers);
  const currentRateLabel = formatPercent(data.commission_rate_pct);
  const nextTier = tiers.find((tier) => tier.name === data.next_tier_name) ?? null;
  const progressValue =
    data.next_tier_threshold != null
      ? Math.min(data.completed_lessons_30d, data.next_tier_threshold)
      : 0;
  const progressPercent =
    data.next_tier_threshold && data.next_tier_threshold > 0
      ? Math.max(0, Math.min(100, (progressValue / data.next_tier_threshold) * 100))
      : 0;

  if (!data.is_founding && tiers.length === 0) {
    return null;
  }

  if (data.is_founding) {
    return (
      <section className="mb-8 rounded-[24px] border border-gray-200 bg-white p-5 text-gray-900 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-2.5">
            <div className="flex items-center gap-3">
              <Star className="h-5 w-5 text-[#6E59CF]" aria-hidden="true" />
              <h2 className="text-[1.7rem] font-semibold leading-none tracking-[-0.02em]">
                Founding Instructor
              </h2>
            </div>
            <p className="max-w-3xl text-[1.05rem] leading-7 text-gray-700 dark:text-gray-300">
              {FOUNDING_DESCRIPTION}
            </p>
          </div>
          <div className="inline-flex w-fit items-center rounded-full bg-[#F2ECFF] px-4 py-1.5 text-[1.2rem] font-semibold text-[#4C3FA0] dark:bg-[#2E2350] dark:text-[#E5DDFF]">
            {currentRateLabel}% · locked
          </div>
        </div>
        <div className="my-5 h-px bg-gray-200 dark:bg-gray-700" />
        <div className="space-y-1.5">
          <p className="text-base text-gray-500 dark:text-gray-400">{FOUNDING_COMMITMENT_LABEL}</p>
          <p className="text-[1.02rem] font-semibold leading-7 text-gray-900 dark:text-gray-100">
            {FOUNDING_COMMITMENT_DETAIL}
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="mb-8 rounded-[24px] border border-gray-200 bg-white p-5 text-gray-900 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 sm:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-[1.75rem] font-semibold leading-none tracking-[-0.02em]">
            {currentTier.display_name} tier · {currentRateLabel}%
          </h2>
          <p className="mt-1.5 text-[1.05rem] leading-7 text-gray-700 dark:text-gray-300">
            {data.next_tier_threshold != null
              ? `${data.completed_lessons_30d} of ${data.next_tier_threshold} lessons completed · in the last 30 days`
              : `${data.completed_lessons_30d} lessons completed · in the last 30 days`}
          </p>
        </div>
        <div
          className={`inline-flex w-fit items-center rounded-full px-4 py-1.5 text-[1.2rem] font-semibold ${
            data.tier_name === 'pro'
              ? 'bg-[#E7F7EE] text-[#207245] dark:bg-[#173625] dark:text-[#B8F0CE]'
              : 'bg-[#F2ECFF] text-[#4C3FA0] dark:bg-[#2E2350] dark:text-[#E5DDFF]'
          }`}
        >
          {currentRateLabel}%
        </div>
      </div>

      <div className="mt-5">
        {tiers.map((tier, index) => {
          const isCurrent = Boolean(tier.is_current);
          const isNextTier = nextTier?.name === tier.name;
          const isLocked = !isCurrent && !tier.is_unlocked;
          const isLastTier = index === tiers.length - 1;
          const showPartialProgress =
            isNextTier && data.next_tier_threshold != null && data.lessons_to_next_tier != null;
          const showFullProgress =
            tier.name !== 'entry' &&
            (isCurrent || Boolean(tier.is_unlocked)) &&
            !showPartialProgress;
          const showProgressBar = showPartialProgress || showFullProgress;
          const barValue = showFullProgress ? 100 : progressPercent;

          return (
            <div key={tier.name} className={isLastTier ? '' : 'pb-3'}>
              <div className="flex items-start gap-3">
                <div className="flex w-10 shrink-0 flex-col items-center">
                  <LadderCircle
                    label={String(index + 1)}
                    isCurrent={isCurrent}
                    isLocked={isLocked}
                  />
                  {!isLastTier ? (
                    <span className="mt-2 h-4 w-px bg-gray-200 dark:bg-gray-700" />
                  ) : null}
                </div>

                <div className="flex min-w-0 flex-1 items-start justify-between gap-3 pt-0.5">
                  <div className="min-w-0 flex-1">
                    <div
                      className={`text-[1.05rem] leading-6 ${
                        isLocked
                          ? 'text-gray-400 dark:text-gray-500'
                          : 'font-semibold text-gray-900 dark:text-gray-100'
                      }`}
                    >
                      {tier.display_name} · {formatPercent(tier.commission_pct)}%
                    </div>

                    {showProgressBar ? (
                      <div className="mt-1.5 max-w-[36rem]">
                        <div
                          aria-label={`${tier.display_name} progress`}
                          aria-valuemax={showFullProgress ? 100 : data.next_tier_threshold ?? 100}
                          aria-valuemin={0}
                          aria-valuenow={showFullProgress ? 100 : progressValue}
                          className="h-1.5 rounded-full bg-[#E6E1F8] dark:bg-[#312650]"
                          role="progressbar"
                        >
                          <div
                            className="h-full rounded-full bg-[#8B7CF6]"
                            style={{ width: `${barValue}%` }}
                          />
                        </div>
                        {showPartialProgress ? (
                          <p className="mt-1.5 text-sm font-medium text-[#7563D1] dark:text-[#B9AFFF]">
                            {data.completed_lessons_30d} of {data.next_tier_threshold} ·{' '}
                            {data.lessons_to_next_tier} more to unlock
                          </p>
                        ) : null}
                      </div>
                    ) : null}
                  </div>

                  <div
                    className={`shrink-0 pt-0.5 text-right text-base leading-6 ${
                      isLocked
                        ? 'text-gray-400 dark:text-gray-500'
                        : 'text-gray-600 dark:text-gray-300'
                    }`}
                  >
                    {formatRangeLabel(tier)}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
