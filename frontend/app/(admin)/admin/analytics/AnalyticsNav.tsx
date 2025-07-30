'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Search, Server, Database } from 'lucide-react';

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
  ];

  return (
    <nav className="flex space-x-1 p-1 bg-gray-100 dark:bg-gray-800 rounded-lg">
      {navItems.map((item) => {
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              item.active
                ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
                : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/50'
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
