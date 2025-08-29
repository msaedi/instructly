'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Search, Server, Database, Code, FlaskConical, Wrench } from 'lucide-react';

export function AnalyticsNav() {
  const pathname = usePathname();

  const currentGroup = (() => {
    if (pathname.startsWith('/admin/analytics')) return 'analytics';
    if (pathname.startsWith('/admin/ops')) return 'ops';
    if (pathname.startsWith('/admin/engineering')) return 'engineering';
    if (pathname.startsWith('/admin/beta')) return 'beta';
    return 'analytics';
  })();

  const groups: Record<string, Array<{ name: string; href: string; icon: any }>> = {
    analytics: [
      { name: 'Search', href: '/admin/analytics/search', icon: Search },
      { name: 'Candidates', href: '/admin/analytics/candidates', icon: Search },
    ],
    ops: [
      { name: 'Redis', href: '/admin/ops/redis', icon: Server },
      { name: 'Database', href: '/admin/ops/database', icon: Database },
    ],
    engineering: [
      { name: 'Codebase', href: '/admin/engineering/codebase', icon: Code },
    ],
    beta: [
      { name: 'Invites', href: '/admin/beta/invites', icon: FlaskConical },
      { name: 'UI Preview', href: '/admin/beta/ui-preview', icon: Wrench },
    ],
  };

  const items = groups[currentGroup];

  return (
    <nav className="inline-flex items-center gap-1 p-1.5 rounded-full bg-white/40 dark:bg-gray-900/40 backdrop-blur ring-1 ring-gray-200/70 dark:ring-gray-700/60 shadow-sm">
      {items.map((item) => {
        const Icon = item.icon as any;
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? 'page' : undefined}
            className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 ${
              active
                ? 'bg-gradient-to-b from-indigo-600 to-indigo-500 text-white shadow-sm'
                : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50/60 dark:hover:bg-gray-800/60'
            }`}
          >
            <Icon className="h-4 w-4" />
            {item.name}
          </Link>
        );
      })}
    </nav>
  );
}
