import type { ReactNode } from 'react';
import Link from 'next/link';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import {
  INSTRUCTOR_DASHBOARD_NAV_ITEMS,
  type DashboardPanel,
} from '@/lib/instructorDashboardNav';
import { cn } from '@/lib/utils';

type InstructorDashboardShellProps = {
  activePanel: DashboardPanel;
  children: ReactNode;
  contentClassName?: string;
};

function getNavHref(item: (typeof INSTRUCTOR_DASHBOARD_NAV_ITEMS)[number]): string {
  if (item.kind === 'route') {
    return item.href;
  }

  if (item.key === 'dashboard') {
    return '/instructor/dashboard';
  }

  return `/instructor/dashboard?panel=${item.key}`;
}

export function InstructorDashboardShell({
  activePanel,
  children,
  contentClassName,
}: InstructorDashboardShellProps) {
  return (
    <div className="min-h-screen insta-dashboard-page" data-testid="instructor-dashboard-shell">
      <header className="insta-dashboard-header px-4 py-4 sm:px-6">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <Link href="/instructor/dashboard" className="inline-block">
            <span className="text-3xl font-bold text-[#7E22CE] transition-colors hover:text-purple-900 dark:hover:text-purple-300">
              iNSTAiNSTRU
            </span>
          </Link>
          <UserProfileDropdown />
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="grid grid-cols-12 gap-6">
          <aside
            className="col-span-12 hidden md:col-span-3 md:block"
            data-testid="instructor-dashboard-sidebar"
          >
            <div className="insta-surface-card p-4">
              <nav aria-label="Instructor dashboard navigation">
                <ul className="space-y-1">
                  {INSTRUCTOR_DASHBOARD_NAV_ITEMS.map((item) => {
                    const isActive = item.kind === 'panel' && item.key === activePanel;

                    return (
                      <li key={item.key}>
                        <Link
                          href={getNavHref(item)}
                          aria-current={isActive ? 'page' : undefined}
                          className={cn(
                            'block rounded-md px-3 py-2 text-left transition-transform transition-colors duration-150',
                            isActive
                              ? 'border border-purple-200 bg-purple-50 font-semibold text-[#7E22CE] dark:border-purple-700 dark:bg-purple-900/30 dark:text-purple-300'
                              : 'text-gray-800 hover:scale-[1.02] hover:bg-purple-50 hover:text-purple-900 dark:text-gray-200 dark:hover:bg-purple-900/20 dark:hover:text-purple-300'
                          )}
                        >
                          {item.label}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </nav>
            </div>
          </aside>

          <section className={cn('col-span-12 md:col-span-9', contentClassName)}>{children}</section>
        </div>
      </div>
    </div>
  );
}
