import type { AnchorHTMLAttributes } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import { AuthShell } from '../AuthShell';

jest.mock('next/link', () => {
  const MockLink = ({
    children,
    href,
    ...props
  }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  );
  MockLink.displayName = 'MockLink';
  return {
    __esModule: true,
    default: MockLink,
  };
});

jest.mock('@/app/config/brand', () => ({
  BRAND: { name: 'iNSTAiNSTRU' },
}));

describe('AuthShell', () => {
  it('renders the brand logo as a home link', () => {
    render(<AuthShell>Form content</AuthShell>);

    const logo = screen.getByRole('link', { name: 'iNSTAiNSTRU' });
    expect(logo).toHaveAttribute('href', '/');
    expect(screen.getByText('Form content')).toBeInTheDocument();
  });

  it('renders title, subtitle, custom classes, and logo click handlers', () => {
    const handleLogoClick = jest.fn();

    const { container } = render(
      <AuthShell
        title="Reset your password"
        subtitle="Choose a new password."
        logoHref="/welcome"
        logoLabel="Custom Logo"
        onLogoClick={handleLogoClick}
        className="shell-extra"
        containerClassName="container-extra"
        cardClassName="card-extra"
        headerClassName="header-extra"
        contentClassName="content-extra"
      >
        <button type="button">Continue</button>
      </AuthShell>
    );

    expect(container.firstElementChild).toHaveClass('shell-extra');
    expect(container.querySelector('.container-extra')).toBeInTheDocument();
    expect(container.querySelector('.card-extra')).toBeInTheDocument();
    expect(container.querySelector('.header-extra')).toBeInTheDocument();
    expect(container.querySelector('.content-extra')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Reset your password' })).toBeInTheDocument();
    expect(screen.getByText('Choose a new password.')).toBeInTheDocument();

    const logo = screen.getByRole('link', { name: 'Custom Logo' });
    expect(logo).toHaveAttribute('href', '/welcome');
    fireEvent.click(logo);
    expect(handleLogoClick).toHaveBeenCalledTimes(1);
  });
});
