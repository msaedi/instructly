import { render, screen } from '@testing-library/react';
import { BookingStatusBadge } from '../BookingStatusBadge';

describe('BookingStatusBadge', () => {
  it('falls back to Pending when status is null', () => {
    render(<BookingStatusBadge status={null} />);

    const badge = screen.getByText('Pending');
    expect(badge).toHaveClass('bg-gray-100', 'text-gray-700');
  });

  it('humanizes unknown statuses with the default badge styling', () => {
    render(<BookingStatusBadge status="WEIRD_STATUS" />);

    const badge = screen.getByText('Weird Status');
    expect(badge).toHaveClass('bg-gray-100', 'text-gray-700');
  });

  it('renders the standardized completed badge styling', () => {
    render(<BookingStatusBadge status="COMPLETED" />);

    const badge = screen.getByText('Completed');
    expect(badge).toHaveClass('bg-blue-50', 'text-blue-700');
  });
});
