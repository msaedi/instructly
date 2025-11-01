// frontend/components/calendar/Slot.tsx

import { forwardRef } from 'react';
import * as Tooltip from '@radix-ui/react-tooltip';
import clsx from 'clsx';

export interface SlotProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  isSelected: boolean;
  isConflict?: boolean;
  isPast?: boolean;
  isDragging?: boolean;
  isMobile?: boolean;
  conflictMessage?: string;
  label: string;
}

function SlotImpl(
  {
    isSelected,
    isConflict = false,
    isPast = false,
    isDragging = false,
    isMobile = false,
    conflictMessage,
    label,
    className,
    disabled,
    ...props
  }: SlotProps,
  ref: React.Ref<HTMLButtonElement>
) {
  const computedDisabled = Boolean(disabled || isConflict);
  const pointerClass = computedDisabled ? 'cursor-not-allowed' : 'cursor-pointer';
  const bgClass = isSelected ? 'bg-[#EDE3FA]' : isPast ? 'bg-gray-50 opacity-70' : 'bg-white';
  const button = (
    <button
      ref={ref}
      type="button"
      className={clsx(
        'relative w-full border-l border-b border-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-0 focus-visible:ring-[#7E22CE] transition-colors',
        isMobile ? 'min-h-[44px]' : 'min-h-[32px]',
        bgClass,
        pointerClass,
        isDragging && 'ring-2 ring-[#D4B5F0] ring-inset',
        className
      )}
      aria-pressed={isSelected}
      aria-label={label}
      aria-disabled={computedDisabled || undefined}
      disabled={computedDisabled}
      {...props}
    >
      {isConflict && (
        <span className="pointer-events-none absolute inset-0 bg-[repeating-linear-gradient(45deg,rgba(156,163,175,0.35),rgba(156,163,175,0.35)_6px,rgba(156,163,175,0.2)_6px,rgba(156,163,175,0.2)_12px)]" />
      )}
    </button>
  );

  if (!isConflict || !conflictMessage) {
    return button;
  }

  return (
    <Tooltip.Provider delayDuration={200}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>{button}</Tooltip.Trigger>
        <Tooltip.Content
          side="top"
          align="center"
          className="max-w-xs rounded-md bg-gray-900 px-3 py-2 text-xs text-white shadow-lg"
        >
          {conflictMessage}
          <Tooltip.Arrow className="fill-gray-900" />
        </Tooltip.Content>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}

export const Slot = forwardRef<HTMLButtonElement, SlotProps>(SlotImpl);

Slot.displayName = 'Slot';
