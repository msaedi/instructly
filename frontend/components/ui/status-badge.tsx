'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { Check, X, Clock, AlertCircle } from 'lucide-react';

export type StatusBadgeVariant = 'success' | 'cancelled' | 'pending' | 'warning' | 'default';

export interface StatusBadgeProps {
  variant: StatusBadgeVariant;
  label: string;
  showIcon?: boolean;
  className?: string;
}

const variantStyles: Record<StatusBadgeVariant, string> = {
  success:
    'bg-green-50 text-green-700 border-green-200 dark:bg-green-950 dark:text-green-300 dark:border-green-800',
  cancelled:
    'bg-gray-50 text-gray-700 border-gray-200 dark:bg-gray-950 dark:text-gray-300 dark:border-gray-800',
  pending:
    'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800',
  warning:
    'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800',
  default:
    'bg-gray-50 text-gray-700 border-gray-200 dark:bg-gray-950 dark:text-gray-300 dark:border-gray-800',
};

const iconMap: Record<StatusBadgeVariant, React.ElementType> = {
  success: Check,
  cancelled: X,
  pending: Clock,
  warning: AlertCircle,
  default: Clock,
};

export function StatusBadge({ variant, label, showIcon = true, className }: StatusBadgeProps) {
  const Icon = iconMap[variant];

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors',
        variantStyles[variant],
        className
      )}
    >
      {showIcon && <Icon className="h-3 w-3" />}
      {label}
    </span>
  );
}
