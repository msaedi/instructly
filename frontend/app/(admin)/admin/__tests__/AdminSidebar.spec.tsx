import { render, screen } from '@testing-library/react';
import AdminSidebar from '../AdminSidebar';
import { usePathname } from 'next/navigation';

jest.mock('@/app/(admin)/admin/bgc-review/hooks', () => ({
  useBGCCounts: () => ({ data: { review: 0 }, refetch: jest.fn() }),
}));

jest.mock('next/navigation', () => ({
  usePathname: jest.fn(),
}));

describe('AdminSidebar', () => {
  beforeEach(() => {
    (usePathname as unknown as jest.Mock).mockReturnValue('/admin/analytics/search');
  });

  it('renders the Badges group with Reviews link', () => {
    const view = render(<AdminSidebar />);
    expect(screen.getByRole('link', { name: /Badges/i })).toBeInTheDocument();
    (usePathname as unknown as jest.Mock).mockReturnValue('/admin/badges/pending');
    view.rerender(<AdminSidebar />);
    expect(screen.getByRole('link', { name: /Reviews/i })).toHaveAttribute(
      'href',
      '/admin/badges/pending',
    );
  });

  it('marks Reviews as active on the badges pending route', () => {
    (usePathname as unknown as jest.Mock).mockReturnValue('/admin/badges/pending');
    render(<AdminSidebar />);
    expect(screen.getByRole('link', { name: /Badges/i })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: /Reviews/i })).toHaveAttribute('aria-current', 'page');
  });
});
