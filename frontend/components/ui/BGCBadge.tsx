import { Clock, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils';

interface BGCBadgeProps {
  isLive: boolean;
  bgcStatus?: string | null;
  className?: string;
}

export function BGCBadge({ isLive, bgcStatus, className }: BGCBadgeProps) {
  const normalizedStatus =
    typeof bgcStatus === 'string' ? bgcStatus.trim().toLowerCase() : '';
  const isVerified =
    isLive ||
    normalizedStatus === 'passed' ||
    normalizedStatus === 'clear' ||
    normalizedStatus === 'verified';

  if (isVerified) {
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs font-medium',
          'bg-green-100 text-green-800 border-green-200',
          className
        )}
      >
        <ShieldCheck className="h-3 w-3" aria-hidden="true" />
        Background Verified
      </span>
    );
  }

  if (normalizedStatus === 'pending') {
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs font-medium',
          'bg-yellow-100 text-yellow-800 border-yellow-200',
          className
        )}
      >
        <Clock className="h-3 w-3" aria-hidden="true" />
        Background Check Pending
      </span>
    );
  }

  return null;
}
