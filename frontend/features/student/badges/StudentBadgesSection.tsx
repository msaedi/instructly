'use client';

import { useMemo, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Award, CheckCircle2, Loader2, Lock, Sparkles } from 'lucide-react';
import { Badge as StatusBadge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { useStudentBadges } from './useStudentBadges';
import type { StudentBadgeItem } from '@/types/badges';
import { groupBadges, type BadgeGroup, type GroupedBadges } from './groupBadges';

const MAX_INLINE_PER_GROUP = 3;

export function StudentBadgesPanel({
  badges,
  isLoading,
  isError,
  errorMessage,
  onRetry,
  modalOpen,
  onModalChange,
}: {
  badges: StudentBadgeItem[];
  isLoading: boolean;
  isError: boolean;
  errorMessage?: string;
  onRetry: () => void;
  modalOpen: boolean;
  onModalChange: (open: boolean) => void;
}) {
  const headingId = 'student-badges-heading';
  const grouped = useMemo(() => groupBadges(badges), [badges]);
  const totalEarned = grouped.earned.length;

  const renderSkeletons = () => (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4" aria-live="polite">
      {Array.from({ length: 6 }).map((_, index) => (
        <div key={index} className="rounded-xl border border-gray-200 p-4">
          <Skeleton className="h-5 w-1/2 mb-3" />
          <Skeleton className="h-4 w-3/4 mb-1" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ))}
    </div>
  );

  const renderError = () => (
    <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 flex items-center justify-between gap-4">
      <div className="flex items-center gap-2">
        <span role="img" aria-hidden="true">
          ⚠️
        </span>
        <p>{errorMessage ?? 'Unable to load badges right now.'}</p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="text-xs font-semibold text-red-700 underline hover:text-red-900"
      >
        Retry
      </button>
    </div>
  );

  const inlineEarned = grouped.earned.slice(0, MAX_INLINE_PER_GROUP);
  const inlineProgress = grouped.progress.slice(0, MAX_INLINE_PER_GROUP);
  const inlineLocked = grouped.locked.slice(0, MAX_INLINE_PER_GROUP);

  const emptyState =
    !isLoading &&
    !isError &&
    grouped.earned.length === 0 &&
    grouped.progress.length === 0 &&
    grouped.locked.length > 0;

  return (
    <section aria-labelledby={headingId}>
      <div className="flex items-center justify-between mb-2">
        <div>
          <h3 id={headingId} className="text-lg font-semibold text-gray-900">
            Achievements & Badges
          </h3>
          <p className="text-sm text-gray-600">Track your learning milestones in real time.</p>
        </div>
        <button
          type="button"
          onClick={() => onModalChange(true)}
          className="text-sm font-medium text-[#7E22CE] hover:text-[#5b1898] transition-colors"
        >
          Explore
        </button>
      </div>

      {isLoading && renderSkeletons()}
      {isError && renderError()}

      {!isLoading && !isError && (
        <>
          {emptyState && (
            <div className="rounded-xl border border-dashed border-purple-200 bg-purple-50 p-4 text-sm text-purple-900">
              Start your first lesson to earn the <span className="font-semibold">Welcome Aboard</span> badge!
            </div>
          )}

          <div className="space-y-6">
            {inlineEarned.length > 0 && (
              <BadgeGroup
                title={`Earned (${totalEarned})`}
                description="Unlocked badges appear here. Pending ones show a verification tag."
                badges={inlineEarned}
                group="earned"
              />
            )}

            {inlineProgress.length > 0 && (
              <BadgeGroup
                title="In Progress"
                description="Keep going! You're getting close on these badges."
                badges={inlineProgress}
                group="progress"
              />
            )}

            {inlineLocked.length > 0 && (
              <BadgeGroup
                title="Locked"
                description="Preview upcoming badges and what it takes to earn them."
                badges={inlineLocked}
                group="locked"
              />
            )}
          </div>
        </>
      )}

      <BadgesDialog
        open={modalOpen}
        onOpenChange={onModalChange}
        grouped={grouped}
        isLoading={isLoading}
      />
    </section>
  );
}

function BadgeGroup({
  title,
  description,
  badges,
  group,
}: {
  title: string;
  description: string;
  badges: StudentBadgeItem[];
  group: BadgeGroup;
}) {
  if (badges.length === 0) return null;

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        {group === 'locked' ? (
          <Lock className="h-4 w-4 text-gray-500" aria-hidden="true" />
        ) : (
          <CheckCircle2
            className={cn('h-4 w-4', group === 'earned' ? 'text-green-500' : 'text-yellow-500')}
            aria-hidden="true"
          />
        )}
        <h4 className="text-sm font-semibold text-gray-900">{title}</h4>
      </div>
      <p className="text-xs text-gray-500 mb-3">{description}</p>

      <div role="list" className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
        {badges.map((badge) => (
          <BadgeTile key={badge.slug} badge={badge} group={group} />
        ))}
      </div>
    </div>
  );
}

type BadgeProgress = {
  goal: number;
  current: number;
  percent: number;
};

const isBadgeProgress = (value: unknown): value is BadgeProgress => {
  if (!value || typeof value !== 'object') return false;
  const progress = value as Record<string, unknown>;
  return (
    typeof progress['goal'] === 'number' &&
    typeof progress['current'] === 'number' &&
    typeof progress['percent'] === 'number'
  );
};

function BadgeTile({ badge, group }: { badge: StudentBadgeItem; group: BadgeGroup }) {
  const progress = isBadgeProgress(badge.progress) ? badge.progress : null;
  const progressPercent =
    progress && progress.goal > 0
      ? Math.max(0, Math.min(100, Math.round(progress.percent)))
      : null;
  const hasProgress = progressPercent !== null;

  const ariaLabelParts = [badge.name];
  if (badge.earned && badge.status === 'pending') {
    ariaLabelParts.push('pending verification');
  } else if (badge.earned) {
    ariaLabelParts.push('earned');
  } else if (progressPercent !== null) {
    ariaLabelParts.push(`${progressPercent}% complete`);
  } else {
    ariaLabelParts.push('locked');
  }

  return (
    <article
      role="listitem"
      aria-label={ariaLabelParts.join(', ')}
      className={cn(
        'rounded-xl border p-4 transition-shadow focus-within:ring-2 focus-within:ring-purple-500',
        badge.earned
          ? 'border-purple-200 bg-purple-50'
          : group === 'progress'
            ? 'border-amber-200 bg-amber-50'
            : 'border-gray-200 bg-white'
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            'p-2 rounded-full',
            badge.earned
              ? 'bg-purple-100 text-purple-700'
              : group === 'progress'
                ? 'bg-amber-100 text-amber-700'
                : 'bg-gray-100 text-gray-600'
          )}
          aria-hidden="true"
        >
          {group === 'locked' ? <Lock className="h-4 w-4" /> : <Award className="h-4 w-4" />}
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h5 className="font-semibold text-gray-900">{badge.name}</h5>
            {badge.status === 'pending' && (
              <StatusBadge variant="secondary" className="text-xs">
                Verifying
              </StatusBadge>
            )}
          </div>
          {badge.earned && badge.confirmed_at && (
            <p className="text-xs text-gray-500">
              Confirmed {new Date(badge.confirmed_at).toLocaleDateString()}
            </p>
          )}
          {!badge.earned && badge.description && (
            <p className="text-xs text-gray-600 mt-1">{badge.description}</p>
          )}
        </div>
      </div>

      {hasProgress && progressPercent !== null && (
        <div className="mt-3" aria-label={`Progress ${progressPercent}%`}>
          <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
            <span>
            {progress?.current ?? 0} / {progress?.goal ?? 0}
            </span>
            <span>{progressPercent}%</span>
          </div>
          <div className="h-2 rounded-full bg-white/60">
            <div
              className="h-2 rounded-full bg-gradient-to-r from-[#7E22CE] to-[#A855F7]"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      )}
    </article>
  );
}

function BadgesDialog({
  open,
  onOpenChange,
  grouped,
  isLoading,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  grouped: GroupedBadges;
  isLoading: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/30 backdrop-blur-sm z-40" />
        <Dialog.Content className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="pointer-events-auto w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-2xl bg-white shadow-2xl ring-1 ring-gray-200">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <div>
                <Dialog.Title className="text-lg font-semibold text-gray-900">
                  Your Badge Journey
                </Dialog.Title>
                <Dialog.Description className="text-sm text-gray-600">
                  Explore earned milestones, in-progress goals, and upcoming badges.
                </Dialog.Description>
              </div>
              <Dialog.Close
                className="p-2 rounded-full hover:bg-gray-100 text-gray-500"
                aria-label="Close badge details"
              >
                <Sparkles className="h-4 w-4" />
              </Dialog.Close>
            </div>

            <div className="p-6 space-y-8">
              {isLoading ? (
                <div className="flex items-center justify-center py-10 text-gray-500">
                  <Loader2 className="h-5 w-5 animate-spin mr-2" aria-hidden="true" />
                  Loading badges…
                </div>
              ) : (
                <>
                  <BadgeGroup
                    title={`Earned (${grouped.earned.length})`}
                    description="Completed badges stay here forever—nice work!"
                    badges={grouped.earned}
                    group="earned"
                  />
                  <BadgeGroup
                    title="In Progress"
                    description="Almost there—keep the streak alive to unlock these."
                    badges={grouped.progress}
                    group="progress"
                  />
                  <BadgeGroup
                    title="Locked"
                    description="Preview requirements for future badges."
                    badges={grouped.locked}
                    group="locked"
                  />
                </>
              )}
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function StudentBadgesSection() {
  const { data, isLoading, isError, error, refetch } = useStudentBadges();
  const [isModalOpen, setModalOpen] = useState(false);

  return (
    <StudentBadgesPanel
      badges={data ?? []}
      isLoading={isLoading}
      isError={isError}
      {...(error?.message ? { errorMessage: error.message } : {})}
      onRetry={() => void refetch()}
      modalOpen={isModalOpen}
      onModalChange={setModalOpen}
    />
  );
}
