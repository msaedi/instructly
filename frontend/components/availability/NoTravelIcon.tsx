import clsx from 'clsx';
import { Car } from 'lucide-react';

interface NoTravelIconProps {
  className?: string;
  slashClassName?: string;
  'data-testid'?: string;
}

export default function NoTravelIcon({
  className,
  slashClassName,
  'data-testid': dataTestId,
}: NoTravelIconProps) {
  return (
    <span
      data-testid={dataTestId}
      className={clsx('relative inline-flex h-4 w-4 items-center justify-center', className)}
      aria-hidden="true"
    >
      <Car className="h-full w-full" />
      <svg
        data-testid={dataTestId ? `${dataTestId}-slash` : undefined}
        className={clsx(
          'pointer-events-none absolute inset-0 overflow-visible',
          slashClassName
        )}
        viewBox="0 0 16 16"
        aria-hidden="true"
      >
        <line
          x1="3"
          y1="13"
          x2="13"
          y2="3"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}
