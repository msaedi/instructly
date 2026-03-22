import type { LucideIcon } from 'lucide-react';

export type DashboardPanel = 'dashboard' | 'profile' | 'bookings' | 'messages' | 'earnings' | 'referrals' | 'reviews' | 'availability' | 'account';
export type DashboardNavKey = DashboardPanel;

type MobileGroup = 'primary' | 'secondary';

type DashboardNavBase = {
  key: DashboardNavKey;
  label: string;
  mobileGroup: MobileGroup;
  icon?: LucideIcon;
};

export type DashboardNavItem = DashboardNavBase & {
  key: DashboardPanel;
  kind: 'panel';
};

export const DASHBOARD_PANEL_KEYS = new Set<DashboardPanel>([
  'dashboard',
  'profile',
  'bookings',
  'messages',
  'earnings',
  'referrals',
  'reviews',
  'availability',
  'account',
]);

export const INSTRUCTOR_DASHBOARD_NAV_ITEMS: DashboardNavItem[] = [
  { key: 'dashboard', label: 'Dashboard', kind: 'panel', mobileGroup: 'primary' },
  { key: 'bookings', label: 'Bookings', kind: 'panel', mobileGroup: 'primary' },
  { key: 'messages', label: 'Messages', kind: 'panel', mobileGroup: 'primary' },
  { key: 'availability', label: 'Availability', kind: 'panel', mobileGroup: 'primary' },
  { key: 'earnings', label: 'Earnings', kind: 'panel', mobileGroup: 'secondary' },
  { key: 'referrals', label: 'Referrals', kind: 'panel', mobileGroup: 'secondary' },
  { key: 'reviews', label: 'Reviews', kind: 'panel', mobileGroup: 'secondary' },
  { key: 'profile', label: 'Instructor Profile', kind: 'panel', mobileGroup: 'secondary' },
  { key: 'account', label: 'Account', kind: 'panel', mobileGroup: 'secondary' },
];

export const MOBILE_NAV_PRIMARY_ITEMS = INSTRUCTOR_DASHBOARD_NAV_ITEMS.filter(
  (item) => item.mobileGroup === 'primary'
);

export const MOBILE_NAV_SECONDARY_ITEMS = INSTRUCTOR_DASHBOARD_NAV_ITEMS.filter(
  (item) => item.mobileGroup === 'secondary'
);

export const isDashboardPanel = (value: string | null): value is DashboardPanel => {
  return value !== null && DASHBOARD_PANEL_KEYS.has(value as DashboardPanel);
};
