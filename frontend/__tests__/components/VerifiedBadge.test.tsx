import { render, screen } from '@testing-library/react';
import { VerifiedBadge } from '@/components/common/VerifiedBadge';

describe('VerifiedBadge', () => {
  it('renders Verified label', () => {
    render(<VerifiedBadge dateISO="2025-01-15T12:34:56Z" />);

    expect(screen.getByText('Verified')).toBeInTheDocument();
  });

  it('matches snapshot', () => {
    const { container } = render(<VerifiedBadge dateISO="2024-10-01T00:00:00Z" />);
    expect(container.firstChild).toMatchSnapshot();
  });
});
