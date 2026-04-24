'use client';

import { Check, Star } from 'lucide-react';

import { useCommissionStatus } from '@/hooks/queries/useCommissionStatus';
import type { TierInfo } from '@/src/api/services/instructors';

const FOUNDING_DESCRIPTION =
  "You have locked in our lowest rate—permanently. Whatever the floor is, you're on it.";
const FOUNDING_COMMITMENT_LABEL = 'Availability commitment to maintain your rate';
const FOUNDING_COMMITMENT_DETAIL =
  '10 hours per week · 3+ days · 8am–8pm · measured monthly (40 hrs/month)';

type TierTimelineState = 'active' | 'met' | 'unmet';

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

function getTierTimelineState(tier: TierInfo): TierTimelineState {
  if (Boolean(tier.is_current)) {
    return 'active';
  }

  if (Boolean(tier.is_unlocked)) {
    return 'met';
  }

  return 'unmet';
}

function getTierDotCount(tier: TierInfo): number {
  if (tier.name === 'entry') {
    return 4;
  }

  if (tier.name === 'growth') {
    return 6;
  }

  if (tier.name === 'pro') {
    return 1;
  }

  if (tier.max_lessons == null) {
    return 1;
  }

  return Math.max(tier.max_lessons - tier.min_lessons + 1, 1);
}

function getFilledDotCount(tier: TierInfo, completedLessons: number): number {
  const state = getTierTimelineState(tier);
  const dotCount = getTierDotCount(tier);

  if (state === 'met') {
    return dotCount;
  }

  if (state === 'unmet') {
    return 0;
  }

  if (tier.max_lessons == null) {
    return completedLessons >= tier.min_lessons ? 1 : 0;
  }

  return Math.max(0, Math.min(dotCount, completedLessons - tier.min_lessons + 1));
}

function getFilledTrackPercent(dotCount: number, filledDots: number): number {
  if (filledDots <= 0 || dotCount <= 1) {
    return 0;
  }

  return Math.max(0, Math.min(100, ((filledDots - 1) / (dotCount - 1)) * 100));
}

function formatCompletedLessonsLabel(completedLessons: number, activityWindowDays: number): string {
  const lessonLabel = completedLessons === 1 ? 'lesson' : 'lessons';
  return `${completedLessons} ${lessonLabel} completed · in the last ${activityWindowDays} days`;
}

function LadderCircle({
  label,
  state,
  testId,
}: {
  label: string;
  state: TierTimelineState;
  testId: string;
}) {
  if (state === 'active') {
    return (
      <div
        aria-current="step"
        className="flex h-9 w-9 items-center justify-center rounded-full border border-(--color-brand) bg-(--color-brand) text-white shadow-[0_8px_18px_rgba(126,34,206,0.18)]"
        data-tier-state="active"
        data-testid={testId}
      >
        <Check className="h-4 w-4" aria-hidden="true" />
      </div>
    );
  }

  return (
    <div
      className={`flex h-9 w-9 items-center justify-center rounded-full border text-sm font-semibold ${
        state === 'met'
          ? 'border-[#E9D5FF] bg-(--color-brand-lavender) text-(--color-brand-dark)'
          : 'border-[#D8B4FE] bg-transparent text-(--color-brand-dark)'
      }`}
      data-tier-state={state}
      data-testid={testId}
    >
      {label}
    </div>
  );
}

export default function CommissionTierCard() {
  const { data, isLoading, error } = useCommissionStatus({ enabled: true });

  if (isLoading || error || !data) {
    return null;
  }

  const tiers = Array.isArray(data.tiers) ? data.tiers : [];
  const currentTier = resolveCurrentTier(data.tier_name, tiers);
  const currentRateLabel = formatPercent(data.commission_rate_pct);
  const completedLessonsLabel = formatCompletedLessonsLabel(
    data.completed_lessons_30d,
    data.activity_window_days
  );

  if (!data.is_founding && tiers.length === 0) {
    return null;
  }

  if (data.is_founding) {
    return (
      <section className="mb-8 rounded-[24px] border border-gray-200 bg-white p-5 text-gray-900 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <Star className="h-5 w-5 text-(--color-brand)" aria-hidden="true" />
              <h2 className="text-sm font-semibold leading-tight sm:text-lg">
                Founding Instructor
              </h2>
            </div>
            <p className="max-w-3xl text-sm leading-6 text-gray-700 dark:text-gray-300">
              {FOUNDING_DESCRIPTION}
            </p>
          </div>
          <div
            className="inline-flex w-fit items-center rounded-full bg-(--color-brand-lavender) px-3 py-1 text-sm font-semibold text-(--color-brand-dark)"
            data-testid="commission-rate-pill"
          >
            {currentRateLabel}% · locked
          </div>
        </div>
        <div className="my-5 h-px bg-gray-200 dark:bg-gray-700" />
        <div className="space-y-1.5">
          <p className="text-base text-gray-500 dark:text-gray-400">{FOUNDING_COMMITMENT_LABEL}</p>
          <p className="text-sm font-semibold leading-6 text-gray-900 dark:text-gray-100">
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
          <h2 className="text-sm font-semibold leading-tight text-gray-900 dark:text-gray-100 sm:text-lg">
            {currentTier.display_name} tier · {currentRateLabel}%
          </h2>
          <p className="mt-1.5 text-sm leading-6 text-gray-700 dark:text-gray-300">
            {completedLessonsLabel}
          </p>
        </div>
        <div
          className="inline-flex w-fit items-center rounded-full bg-(--color-brand-lavender) px-3 py-1 text-sm font-semibold text-(--color-brand-dark)"
          data-testid="commission-rate-pill"
        >
          {currentRateLabel}%
        </div>
      </div>

      <div className="relative mt-6 space-y-5">
        {tiers.map((tier, index) => {
          const state = getTierTimelineState(tier);
          const dotCount = getTierDotCount(tier);
          const filledDots = getFilledDotCount(tier, data.completed_lessons_30d);
          const filledTrackPercent = getFilledTrackPercent(dotCount, filledDots);

          return (
            <div
              key={tier.name}
              className="relative grid grid-cols-[2.5rem_minmax(0,1fr)] grid-rows-[1.5rem_2.25rem] gap-x-3 gap-y-2"
              data-testid={`commission-tier-row-${tier.name}`}
              data-tier-state={state}
            >
              {index < tiers.length - 1 ? (
                <span
                  className="pointer-events-none absolute left-5 top-[3.125rem] bottom-[-1.25rem] w-px -translate-x-1/2 bg-(--color-brand-lavender)"
                  data-testid={`commission-tier-connector-${tier.name}`}
                />
              ) : null}

              <div className="col-start-1 row-start-2 flex items-center justify-center">
                <LadderCircle
                  label={String(index + 1)}
                  state={state}
                  testId={`commission-tier-step-${tier.name}`}
                />
              </div>

              <div className="col-start-2 row-start-1 flex h-6 min-w-0 items-start justify-between gap-3">
                <div
                  className={`min-w-0 text-sm font-semibold leading-6 ${
                    state === 'unmet'
                      ? 'text-gray-700 dark:text-gray-300'
                      : 'text-gray-900 dark:text-gray-100'
                  }`}
                >
                  {tier.display_name} · {formatPercent(tier.commission_pct)}%
                </div>
                <div className="shrink-0 text-sm leading-6 text-gray-500 dark:text-gray-400">
                  {formatRangeLabel(tier)}
                </div>
              </div>

              <div className="col-start-2 row-start-2 flex items-center">
                <div
                  aria-label={`${tier.display_name} milestones`}
                  className="relative h-5 w-full"
                  data-dot-count={dotCount}
                  data-filled-dots={filledDots}
                  data-testid={`commission-tier-track-${tier.name}`}
                >
                  <div className="absolute left-1.5 right-1.5 top-1/2 h-px -translate-y-1/2">
                    <span className="absolute inset-0 bg-(--color-brand-lavender)" />
                    {filledDots > 0 ? (
                      <span
                        className="absolute left-0 top-0 h-full bg-(--color-brand-dark)"
                        data-testid={`commission-tier-fill-${tier.name}`}
                        style={{ width: dotCount > 1 ? `${filledTrackPercent}%` : '0%' }}
                      />
                    ) : null}
                  </div>

                  <div className="absolute inset-x-0 top-1/2 flex -translate-y-1/2 items-center justify-between">
                    {Array.from({ length: dotCount }, (_, dotIndex) => {
                      const filled = dotIndex < filledDots;

                      return (
                        <span
                          key={`${tier.name}-dot-${dotIndex + 1}`}
                          className={`h-3 w-3 rounded-full border ${
                            filled
                              ? 'border-(--color-brand-dark) bg-(--color-brand-dark)'
                              : 'border-(--color-brand-lavender) bg-transparent'
                          }`}
                          data-dot-state={filled ? 'filled' : 'unfilled'}
                          data-testid={`commission-tier-dot-${tier.name}-${dotIndex + 1}`}
                        />
                      );
                    })}
                  </div>

                  <span className="sr-only">
                    {filledDots} of {dotCount} milestones completed for {tier.display_name}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
