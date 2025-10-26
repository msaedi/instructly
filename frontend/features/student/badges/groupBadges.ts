import type { StudentBadgeItem } from '@/types/badges';

export type BadgeGroup = 'earned' | 'progress' | 'locked';

export type GroupedBadges = {
  earned: StudentBadgeItem[];
  progress: StudentBadgeItem[];
  locked: StudentBadgeItem[];
};

export function groupBadges(badges: StudentBadgeItem[]): GroupedBadges {
  const earned: StudentBadgeItem[] = [];
  const progress: StudentBadgeItem[] = [];
  const locked: StudentBadgeItem[] = [];

  badges.forEach((badge) => {
    if (badge.earned) {
      earned.push(badge);
      return;
    }
    if (badge.progress && typeof badge.progress.percent === 'number') {
      progress.push(badge);
      return;
    }
    locked.push(badge);
  });

  return { earned, progress, locked };
}
