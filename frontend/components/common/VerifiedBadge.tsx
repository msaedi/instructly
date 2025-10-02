'use client';

import * as Tooltip from '@radix-ui/react-tooltip';
import { ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils';

function formatCompletedDate(dateISO?: string | null): string | undefined {
  if (!dateISO) return undefined;
  const parsed = new Date(dateISO);
  if (Number.isNaN(parsed.getTime())) return undefined;
  try {
    return new Intl.DateTimeFormat('en-US', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(parsed);
  } catch {
    return parsed.toLocaleDateString('en-US', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
  }
}

export interface VerifiedBadgeProps {
  dateISO?: string | null;
  className?: string;
}

export function VerifiedBadge({ dateISO, className }: VerifiedBadgeProps) {
  const formattedDate = formatCompletedDate(dateISO);
  const tooltipText = formattedDate
    ? `Background check cleared on ${formattedDate}`
    : 'Background check cleared';

  const badge = (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md bg-emerald-600/10 px-2 py-0.5 text-xs font-medium text-emerald-700',
        className
      )}
    >
      <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
      Verified
    </span>
  );

  return (
    <Tooltip.Provider delayDuration={150} skipDelayDuration={75}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>{badge}</Tooltip.Trigger>
        <Tooltip.Content
          side="top"
          sideOffset={6}
          className="rounded-md bg-gray-900 px-2 py-1 text-xs text-white shadow pointer-events-none select-none"
        >
          {tooltipText}
          <Tooltip.Arrow className="fill-gray-900" />
        </Tooltip.Content>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}

export default VerifiedBadge;
