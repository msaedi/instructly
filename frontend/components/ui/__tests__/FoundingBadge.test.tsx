import { render, screen } from '@testing-library/react';
import { FoundingBadge } from '../FoundingBadge';

describe('FoundingBadge', () => {
  it('renders default size styles when size is omitted', () => {
    render(<FoundingBadge />);

    const badge = screen.getByText('Founding Instructor');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('text-sm');
  });
});
