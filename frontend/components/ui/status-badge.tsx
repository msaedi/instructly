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
  success: 'insta-status-badge--success',
  cancelled: 'insta-status-badge--cancelled',
  pending: 'insta-status-badge--pending',
  warning: 'insta-status-badge--warning',
  default: 'insta-status-badge--default',
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
        'insta-status-badge',
        variantStyles[variant],
        className
      )}
    >
      {showIcon && <Icon className="h-3 w-3" />}
      {label}
    </span>
  );
}
