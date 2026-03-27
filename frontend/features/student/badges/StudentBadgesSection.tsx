'use client';

import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Award, CheckCircle2, Loader2, Lock, Sparkles } from 'lucide-react';
import { Badge as StatusBadge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { useStudentBadges } from './useStudentBadges';
import type { StudentBadgeItem } from '@/types/badges';
import { groupBadges, type BadgeGroup, type GroupedBadges } from './groupBadges';

const MAX_INLINE_PER_GROUP = 3;

function useIsDarkModeClass() {
  const [isDarkMode, setIsDarkMode] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    const mediaQuery =
      typeof window.matchMedia === 'function'
        ? window.matchMedia('(prefers-color-scheme: dark)')
        : null;
    const syncTheme = () => {
      setIsDarkMode(root.classList.contains('dark') || mediaQuery?.matches === true);
    };

    syncTheme();

    const observer = new MutationObserver(syncTheme);
    observer.observe(root, { attributes: true, attributeFilter: ['class'] });

    if (!mediaQuery) {
      return () => {
        observer.disconnect();
      };
    }

    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', syncTheme);
      return () => {
        observer.disconnect();
        mediaQuery.removeEventListener('change', syncTheme);
      };
    }

    mediaQuery.addListener(syncTheme);
    return () => {
      observer.disconnect();
      mediaQuery.removeListener(syncTheme);
    };
  }, []);

  return isDarkMode;
}

function getBadgeTileStyle(group: BadgeGroup, earned: boolean, isDarkMode: boolean): CSSProperties {
  if (isDarkMode) {
    if (earned) {
      return {
        borderColor: 'rgba(192, 132, 252, 0.58)',
        backgroundColor: 'rgba(88, 28, 135, 0.22)',
      };
    }
    if (group === 'progress') {
      return {
        borderColor: 'rgba(251, 191, 36, 0.58)',
        backgroundColor: 'rgba(120, 53, 15, 0.24)',
      };
    }
    return {
      borderColor: 'rgba(148, 163, 184, 0.48)',
      backgroundColor: 'rgba(30, 41, 59, 0.42)',
    };
  }

  if (earned) {
    return {
      borderColor: 'rgba(216, 180, 254, 0.92)',
      backgroundColor: 'rgba(245, 236, 255, 0.95)',
    };
  }
  if (group === 'progress') {
    return {
      borderColor: 'rgba(252, 211, 77, 0.9)',
      backgroundColor: 'rgba(255, 247, 214, 0.94)',
    };
  }
  return {
    borderColor: 'rgba(209, 213, 219, 0.92)',
    backgroundColor: 'rgba(255, 255, 255, 0.9)',
  };
}

function getBadgeIconStyle(group: BadgeGroup, earned: boolean, isDarkMode: boolean): CSSProperties {
  if (isDarkMode) {
    if (earned) {
      return {
        backgroundColor: 'rgba(126, 34, 206, 0.35)',
        color: '#f3e8ff',
      };
    }
    if (group === 'progress') {
      return {
        backgroundColor: 'rgba(245, 158, 11, 0.35)',
        color: '#fef3c7',
      };
    }
    return {
      backgroundColor: 'rgba(51, 65, 85, 0.85)',
      color: '#e2e8f0',
    };
  }

  if (earned) {
    return {
      backgroundColor: '#f3e8ff',
      color: '#7e22ce',
    };
  }
  if (group === 'progress') {
    return {
      backgroundColor: '#fef3c7',
      color: '#b45309',
    };
  }
  return {
    backgroundColor: '#f3f4f6',
    color: '#4b5563',
  };
}

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
  const isDarkMode = useIsDarkModeClass();

  const renderSkeletons = () => (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4" aria-live="polite">
      {Array.from({ length: 6 }).map((_, index) => (
        <div
          key={index}
          className="rounded-xl border p-4"
          style={getBadgeTileStyle('locked', false, isDarkMode)}
        >
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
        className="text-xs font-semibold text-red-700 underline hover:text-red-900 dark:hover:text-red-300"
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
          <h3 id={headingId} className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Achievements & Badges
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400">Track your learning milestones in real time.</p>
        </div>
        <button
          type="button"
          onClick={() => onModalChange(true)}
          className="text-sm font-medium text-(--color-brand-dark) hover:text-[#5b1898] transition-colors"
        >
          Explore
        </button>
      </div>

      {isLoading && renderSkeletons()}
      {isError && renderError()}

      {!isLoading && !isError && (
        <>
          {emptyState && (
            <div className="insta-student-badge-empty rounded-xl border border-dashed p-4 text-sm">
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
                isDarkMode={isDarkMode}
              />
            )}

            {inlineProgress.length > 0 && (
              <BadgeGroup
                title="In Progress"
                description="Keep going! You're getting close on these badges."
                badges={inlineProgress}
                group="progress"
                isDarkMode={isDarkMode}
              />
            )}

            {inlineLocked.length > 0 && (
              <BadgeGroup
                title="Locked"
                description="Preview upcoming badges and what it takes to earn them."
                badges={inlineLocked}
                group="locked"
                isDarkMode={isDarkMode}
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
        isDarkMode={isDarkMode}
      />
    </section>
  );
}

function BadgeGroup({
  title,
  description,
  badges,
  group,
  isDarkMode,
}: {
  title: string;
  description: string;
  badges: StudentBadgeItem[];
  group: BadgeGroup;
  isDarkMode: boolean;
}) {
  if (badges.length === 0) return null;

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        {group === 'locked' ? (
          <Lock className="h-4 w-4 text-gray-500 dark:text-gray-400" aria-hidden="true" />
        ) : (
          <CheckCircle2
            className={cn('h-4 w-4', group === 'earned' ? 'text-green-500' : 'text-yellow-500')}
            aria-hidden="true"
          />
        )}
        <h4 className="insta-student-badge-group-title text-sm font-semibold">{title}</h4>
      </div>
      <p className="insta-student-badge-group-description text-xs mb-3">{description}</p>

      <div role="list" className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
        {badges.map((badge) => (
          <BadgeTile key={badge.slug} badge={badge} group={group} isDarkMode={isDarkMode} />
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

function BadgeTile({
  badge,
  group,
  isDarkMode,
}: {
  badge: StudentBadgeItem;
  group: BadgeGroup;
  isDarkMode: boolean;
}) {
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
      className="rounded-xl border p-4 transition-shadow focus-within:ring-2 focus-within:ring-purple-500"
      style={getBadgeTileStyle(group, badge.earned, isDarkMode)}
    >
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-full" style={getBadgeIconStyle(group, badge.earned, isDarkMode)} aria-hidden="true">
          {group === 'locked' ? <Lock className="h-4 w-4" /> : <Award className="h-4 w-4" />}
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h5 className="font-semibold" style={{ color: isDarkMode ? '#f3f4f6' : '#111827' }}>{badge.name}</h5>
            {badge.status === 'pending' && (
              <StatusBadge variant="secondary" className="text-xs">
                Verifying
              </StatusBadge>
            )}
          </div>
          {badge.earned && badge.confirmed_at && (
            <p className="text-xs" style={{ color: isDarkMode ? '#d1d5db' : '#4b5563' }}>
              Confirmed {new Date(badge.confirmed_at).toLocaleDateString()}
            </p>
          )}
          {!badge.earned && badge.description && (
            <p className="text-xs mt-1" style={{ color: isDarkMode ? '#d1d5db' : '#4b5563' }}>{badge.description}</p>
          )}
        </div>
      </div>

      {hasProgress && progressPercent !== null && (
        <div className="mt-3" aria-label={`Progress ${progressPercent}%`}>
          <div className="flex items-center justify-between text-xs mb-1" style={{ color: isDarkMode ? '#d1d5db' : '#4b5563' }}>
            <span>
            {progress?.current ?? 0} / {progress?.goal ?? 0}
            </span>
            <span>{progressPercent}%</span>
          </div>
          <div
            className="h-2 rounded-full"
            style={{ backgroundColor: isDarkMode ? 'rgba(51, 65, 85, 0.78)' : 'rgba(255, 255, 255, 0.7)' }}
          >
            <div
              className="h-2 rounded-full bg-gradient-to-r from-(--color-brand-dark) to-[#A855F7]"
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
  isDarkMode,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  grouped: GroupedBadges;
  isLoading: boolean;
  isDarkMode: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/30 backdrop-blur-sm z-40" />
        <Dialog.Content className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="insta-dialog-panel pointer-events-auto w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-2xl ring-1 ring-gray-200 dark:ring-gray-700/80">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700/80">
              <div>
                <Dialog.Title className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  Your Badge Journey
                </Dialog.Title>
                <Dialog.Description className="text-sm text-gray-600 dark:text-gray-400">
                  Explore earned milestones, in-progress goals, and upcoming badges.
                </Dialog.Description>
              </div>
              <Dialog.Close
                className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400"
                aria-label="Close badge details"
              >
                <Sparkles className="h-4 w-4" />
              </Dialog.Close>
            </div>

            <div className="p-6 space-y-8">
              {isLoading ? (
                <div className="flex items-center justify-center py-10 text-gray-500 dark:text-gray-400">
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
                    isDarkMode={isDarkMode}
                  />
                  <BadgeGroup
                    title="In Progress"
                    description="Almost there—keep the streak alive to unlock these."
                    badges={grouped.progress}
                    group="progress"
                    isDarkMode={isDarkMode}
                  />
                  <BadgeGroup
                    title="Locked"
                    description="Preview requirements for future badges."
                    badges={grouped.locked}
                    group="locked"
                    isDarkMode={isDarkMode}
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
