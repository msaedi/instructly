import { cn } from '@/lib/utils';

type DashboardTabOption<T extends string> = {
  value: T;
  label: string;
};

type DashboardTabStripProps<T extends string> = {
  ariaLabel: string;
  tabs: readonly DashboardTabOption<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
  tabClassName?: string;
};

export function DashboardTabStrip<T extends string>({
  ariaLabel,
  tabs,
  value,
  onChange,
  className,
  tabClassName,
}: DashboardTabStripProps<T>) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={cn('flex w-full border-b border-gray-200 dark:border-gray-700', className)}
    >
      {tabs.map((tab) => {
        const isActive = value === tab.value;

        return (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={isActive}
            className={cn(
              '-mb-px flex-1 border-b-2 px-3 py-3 text-xs font-medium whitespace-nowrap transition-colors sm:px-4 sm:text-sm',
              isActive
                ? 'border-(--color-brand-dark) text-(--color-brand-dark)'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200',
              tabClassName
            )}
            onClick={() => onChange(tab.value)}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

export type { DashboardTabOption };
