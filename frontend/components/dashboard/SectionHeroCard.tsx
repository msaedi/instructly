'use client';

import { type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

type SectionHeroCardProps = {
  icon: LucideIcon;
  title: string;
  subtitle: string;
  actions?: ReactNode;
  className?: string;
  id?: string | undefined;
};

export function SectionHeroCard({ icon: Icon, title, subtitle, actions, className, id }: SectionHeroCardProps) {
  return (
    <div
      id={id}
      className={cn('bg-white rounded-xl border border-gray-200 shadow-sm p-6 sm:p-8 mb-6 insta-surface-card', className)}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center text-[#7E22CE]">
            <Icon className="w-6 h-6" aria-hidden="true" />
          </div>
          <div className="space-y-1">
            <h2 className="text-2xl sm:text-3xl font-semibold text-gray-900">{title}</h2>
            <p className="text-sm sm:text-base text-gray-600">{subtitle}</p>
          </div>
        </div>
        {actions ? <div className="flex items-center gap-3">{actions}</div> : null}
      </div>
    </div>
  );
}
