import { Star } from 'lucide-react';
import { cn } from '@/lib/utils';

type FoundingBadgeSize = 'sm' | 'md' | 'lg';

interface FoundingBadgeProps {
  size?: FoundingBadgeSize;
  className?: string;
}

const sizeClasses: Record<FoundingBadgeSize, string> = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-3 py-1 text-sm',
  lg: 'px-4 py-1.5 text-base',
};

const iconClasses: Record<FoundingBadgeSize, string> = {
  sm: 'h-3 w-3 mr-1',
  md: 'h-4 w-4 mr-1.5',
  lg: 'h-5 w-5 mr-2',
};

export function FoundingBadge({ size = 'md', className }: FoundingBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border font-medium',
        'bg-gradient-to-r from-slate-100 to-slate-300 text-slate-700 border-slate-300',
        sizeClasses[size],
        className
      )}
    >
      <Star className={cn(iconClasses[size], 'fill-current')} aria-hidden="true" />
      Founding Instructor
    </span>
  );
}
