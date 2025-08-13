'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Search, Server, Database, Code } from 'lucide-react';

export function AnalyticsNav() {
  const pathname = usePathname();

  const navItems = [
    {
      name: 'Search Analytics',
      href: '/admin/analytics/search',
      icon: Search,
      active: pathname === '/admin/analytics/search',
    },
    {
      name: 'Redis Monitoring',
      href: '/admin/analytics/redis',
      icon: Server,
      active: pathname === '/admin/analytics/redis',
    },
    {
      name: 'Database Health',
      href: '/admin/analytics/database',
      icon: Database,
      active: pathname === '/admin/analytics/database',
    },
    {
      name: 'Codebase Metrics',
      href: '/admin/analytics/codebase',
      icon: Code,
      active: pathname === '/admin/analytics/codebase',
    },
  ];

  return (
    <nav className="inline-flex items-center gap-1 p-1.5 rounded-full bg-white/40 dark:bg-gray-900/40 backdrop-blur ring-1 ring-gray-200/70 dark:ring-gray-700/60 shadow-sm">
      {navItems.map((item) => {
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={item.active ? 'page' : undefined}
            className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 ${
              item.active
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
