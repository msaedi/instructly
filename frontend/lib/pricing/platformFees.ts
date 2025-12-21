import type { PlatformFees } from '@/lib/api/config';

export type PlatformFeeContext = {
  fees: PlatformFees;
  isFoundingInstructor?: boolean | null;
  currentTierPct?: number | null;
};

const normalizePct = (pct: number): number => (pct > 1 ? pct / 100 : pct);

export function resolvePlatformFeeRate({
  fees,
  isFoundingInstructor,
  currentTierPct,
}: PlatformFeeContext): number {
  if (isFoundingInstructor) {
    return fees.founding_instructor;
  }

  if (typeof currentTierPct === 'number' && Number.isFinite(currentTierPct)) {
    return normalizePct(currentTierPct);
  }

  return fees.tier_1;
}

export function formatPlatformFeeLabel(rate: number): string {
  const percent = rate * 100;
  return percent % 1 === 0 ? `${percent.toFixed(0)}%` : `${percent.toFixed(1)}%`;
}

export function resolveTakeHomePct(rate: number): number {
  return 1 - rate;
}
