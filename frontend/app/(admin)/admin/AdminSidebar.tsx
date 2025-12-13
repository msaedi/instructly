'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect } from 'react';
import { Search, Server, Code, FlaskConical, Gift, ShieldCheck, SlidersHorizontal, Award, Sparkles } from 'lucide-react';

import { cn } from '@/lib/utils';
import { useBGCCounts } from './bgc-review/hooks';
import { useBGCWebhookStats } from './bgc-webhooks/hooks';

function ReviewBadge({ className }: { className?: string }) {
  const { data, refetch } = useBGCCounts();
  const count = data?.review ?? 0;

  useEffect(() => {
    const handleRefresh = () => {
      void refetch();
    };

    window.addEventListener('bgc-review-refresh', handleRefresh);
    return () => {
      window.removeEventListener('bgc-review-refresh', handleRefresh);
    };
  }, [refetch]);

  if (!count) return null;

  return (
    <span
      className={cn(
        'inline-flex items-center justify-center rounded-full bg-purple-600 px-2 py-0.5 text-xs font-semibold text-white shadow-sm',
        className,
      )}
    >
      {count}
    </span>
  );
}

function WebhookErrorBadge({ className }: { className?: string }) {
  const { data, refetch } = useBGCWebhookStats();
  const count = data?.error_count_24h ?? 0;

  useEffect(() => {
    const handleRefresh = () => {
      void refetch();
    };
    window.addEventListener('bgc-webhooks-refresh', handleRefresh);
    return () => {
      window.removeEventListener('bgc-webhooks-refresh', handleRefresh);
    };
  }, [refetch]);

  if (!count) return null;

  return (
    <span
      className={cn(
        'inline-flex items-center justify-center rounded-full bg-rose-600 px-2 py-0.5 text-xs font-semibold text-white shadow-sm',
        className,
      )}
    >
      {count}
    </span>
  );
}

function AdminSidebar() {
  const pathname = usePathname();

  const categories = [
    {
      key: 'analytics',
      label: 'Analytics',
      href: '/admin/analytics/search',
      icon: Search,
      items: [
        { name: 'Search', href: '/admin/analytics/search' },
        { name: 'Candidates', href: '/admin/analytics/candidates' },
      ],
    },
    {
      key: 'ops',
      label: 'Ops',
      href: '/admin/ops/redis',
      icon: Server,
      items: [
        { name: 'Redis', href: '/admin/ops/redis' },
        { name: 'Database', href: '/admin/ops/database' },
        { name: 'Auth Blocks', href: '/admin/ops/auth-blocks' },
      ],
    },
    {
      key: 'engineering',
      label: 'Engineering',
      href: '/admin/engineering/codebase',
      icon: Code,
      items: [
        { name: 'Codebase', href: '/admin/engineering/codebase' },
      ],
    },
    {
      key: 'nl-search',
      label: 'NL Search',
      href: '/admin/nl-search',
      icon: Sparkles,
      items: [
        { name: 'Testing', href: '/admin/nl-search' },
      ],
    },
    {
      key: 'bgc',
      label: 'Background Checks',
      href: '/admin/bgc-review',
      icon: ShieldCheck,
      items: [
        { name: 'Review Queue', href: '/admin/bgc-review' },
        { name: 'Webhook Logs', href: '/admin/bgc-webhooks' },
      ],
    },
    {
      key: 'badges',
      label: 'Badges',
      href: '/admin/badges/pending',
      icon: Award,
      items: [{ name: 'Reviews', href: '/admin/badges/pending' }],
    },
    {
      key: 'referrals',
      label: 'Referrals',
      href: '/admin/referrals',
      icon: Gift,
      items: [
        { name: 'Dashboard', href: '/admin/referrals' },
      ],
    },
    {
      key: 'beta',
      label: 'Beta',
      href: '/admin/beta/invites',
      icon: FlaskConical,
      items: [
        { name: 'Invites', href: '/admin/beta/invites' },
        { name: 'Settings', href: '/admin/beta/settings' },
        { name: 'Metrics', href: '/admin/beta/metrics' },
        { name: 'UI Preview', href: '/admin/beta/ui-preview' },
      ],
    },
    {
      key: 'settings',
      label: 'Settings',
      href: '/admin/settings/pricing',
      icon: SlidersHorizontal,
      items: [
        { name: 'Pricing', href: '/admin/settings/pricing' },
      ],
    },
  ] as const;

  return (
    <nav className="bg-white/60 dark:bg-gray-900/40 backdrop-blur rounded-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60 p-4 w-full">
      <ul className="space-y-1">
        {categories.map((cat) => {
          const Icon = cat.icon;
          const active = pathname.startsWith(`/admin/${cat.key}`);
          return (
          <li key={cat.key}>
            <Link
              href={cat.href}
              className={`flex items-center justify-between gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                active
                  ? 'bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50/70 dark:hover:bg-gray-800/40'
              }`}
              aria-current={active ? 'page' : undefined}
            >
              <span className="flex items-center gap-3">
                <Icon className="h-4 w-4" />
                {cat.label}
              </span>
              {cat.key === 'bgc' ? <ReviewBadge /> : null}
            </Link>
            {active && (
              <ul className="mt-1 ml-8 space-y-1">
                {cat.items.map((sub) => {
                  const subActive = pathname === sub.href;
                  return (
                    <li key={sub.href}>
                      <Link
                        href={sub.href}
                        className={`flex items-center justify-between gap-2 px-2 py-1.5 rounded-md text-sm ${
                          subActive
                            ? 'text-indigo-700 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-900/10'
                            : 'text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 hover:bg-gray-50/60 dark:hover:bg-gray-800/40'
                        }`}
                        aria-current={subActive ? 'page' : undefined}
                      >
                          <span>{sub.name}</span>
                          {sub.href === '/admin/bgc-review' ? <ReviewBadge /> : null}
                          {sub.href === '/admin/bgc-webhooks' ? <WebhookErrorBadge /> : null}
                      </Link>
                    </li>
                  );
                })}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export default AdminSidebar;
