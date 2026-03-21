import {
  INSTRUCTOR_DASHBOARD_NAV_ITEMS,
  MOBILE_NAV_PRIMARY_ITEMS,
  MOBILE_NAV_SECONDARY_ITEMS,
} from '../instructorDashboardNav';

describe('instructorDashboardNav', () => {
  it('keeps the approved dashboard nav order', () => {
    expect(INSTRUCTOR_DASHBOARD_NAV_ITEMS.map((item) => item.label)).toEqual([
      'Dashboard',
      'Bookings',
      'Messages',
      'Availability',
      'Earnings',
      'Referrals',
      'Reviews',
      'Instructor Profile',
      'Account',
    ]);
  });

  it('treats Messages as a route item in mobile primary nav', () => {
    const messagesItem = MOBILE_NAV_PRIMARY_ITEMS.find((item) => item.key === 'messages');

    expect(messagesItem).toMatchObject({
      kind: 'route',
      href: '/instructor/messages',
      label: 'Messages',
    });
    expect(MOBILE_NAV_SECONDARY_ITEMS.map((item) => item.key)).not.toContain('messages');
  });
});
