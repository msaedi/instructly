import { render, screen } from '@testing-library/react';
import { BGCBadge } from '../BGCBadge';

describe('BGCBadge', () => {
  it('renders verified badge when live', () => {
    render(<BGCBadge isLive bgcStatus="verified" />);

    expect(screen.getByText(/background verified/i)).toBeInTheDocument();
  });

  it('renders pending badge when status is pending', () => {
    render(<BGCBadge isLive={false} bgcStatus="pending" />);

    expect(screen.getByText(/background check pending/i)).toBeInTheDocument();
  });

  it('returns null when not live and status is not pending', () => {
    const { container } = render(<BGCBadge isLive={false} bgcStatus="approved" />);

    expect(container.firstChild).toBeNull();
  });

  it('passes className through', () => {
    render(<BGCBadge isLive bgcStatus="verified" className="custom-class" />);

    expect(screen.getByText(/background verified/i)).toHaveClass('custom-class');
  });

  it('normalizes status casing and whitespace', () => {
    render(<BGCBadge isLive={false} bgcStatus="  PENDING  " />);

    expect(screen.getByText(/background check pending/i)).toBeInTheDocument();
  });
});
