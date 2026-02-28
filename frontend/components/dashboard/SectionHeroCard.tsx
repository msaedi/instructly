'use client';

import { type LucideIcon } from 'lucide-react';
import { forwardRef, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

type SectionHeroCardProps = {
  icon: LucideIcon;
  title: string;
  titleNode?: ReactNode;
  subtitle: string;
  actions?: ReactNode;
  className?: string;
  id?: string | undefined;
  headingAs?: 'h1' | 'h2' | 'h3';
  titleClassName?: string;
  subtitleClassName?: string;
};

export const SectionHeroCard = forwardRef<HTMLDivElement, SectionHeroCardProps>(
  (
    {
      icon: Icon,
      title,
      titleNode,
      subtitle,
      actions,
      className,
      id,
      headingAs = 'h2',
      titleClassName,
      subtitleClassName,
    },
    ref
  ) => {
    const HeadingTag = headingAs;

    return (
      <div
        id={id}
        ref={ref}
        className={cn('insta-surface-card p-6 sm:p-8 mb-6', className)}
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center text-[#7E22CE]">
              <Icon className="w-6 h-6" aria-hidden="true" />
            </div>
            <div className="space-y-1 min-w-0">
              <HeadingTag className={cn('text-2xl sm:text-3xl font-semibold text-gray-900 dark:text-gray-100', titleClassName)}>
                {titleNode ?? title}
              </HeadingTag>
              <p className={cn('text-sm sm:text-base text-gray-600 dark:text-gray-400', subtitleClassName)}>{subtitle}</p>
            </div>
          </div>
          {actions ? <div className="flex items-center gap-3">{actions}</div> : null}
        </div>
      </div>
    );
  }
);

SectionHeroCard.displayName = 'SectionHeroCard';
