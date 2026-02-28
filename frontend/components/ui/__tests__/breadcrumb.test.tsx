import { render, screen } from '@testing-library/react';
import { Breadcrumb } from '../breadcrumb';

describe('Breadcrumb', () => {
  it('renders nav with items', () => {
    render(<Breadcrumb items={[{ label: 'Home', href: '/' }, { label: 'Profile' }]} />);

    expect(screen.getByLabelText('Breadcrumb')).toBeInTheDocument();
    expect(screen.getByText('Home')).toBeInTheDocument();
    expect(screen.getByText('Profile')).toBeInTheDocument();
  });

  it('renders links for non-last items', () => {
    render(<Breadcrumb items={[{ label: 'Home', href: '/' }, { label: 'Profile' }]} />);

    expect(screen.getByRole('link', { name: 'Home' })).toBeInTheDocument();
  });

  it('renders last item as text', () => {
    render(<Breadcrumb items={[{ label: 'Home', href: '/' }, { label: 'Profile' }]} />);

    const profile = screen.getByText('Profile');
    expect(profile.tagName.toLowerCase()).toBe('span');
  });

  it('renders chevrons between items', () => {
    const { container } = render(
      <Breadcrumb
        items={[
          { label: 'Home', href: '/' },
          { label: 'Settings', href: '/settings' },
          { label: 'Profile' },
        ]}
      />
    );

    expect(container.querySelectorAll('svg').length).toBe(2);
    expect(container.querySelectorAll('svg[aria-hidden="true"][focusable="false"]').length).toBe(2);
  });

  it('applies custom className', () => {
    const { container } = render(<Breadcrumb items={[{ label: 'Home', href: '/' }]} className="custom" />);

    expect(container.querySelector('nav')).toHaveClass('custom');
  });
});
