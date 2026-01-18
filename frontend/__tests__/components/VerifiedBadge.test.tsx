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

  it('uses fallback toLocaleDateString when Intl.DateTimeFormat throws', () => {
    const originalDateTimeFormat = Intl.DateTimeFormat;
    const mockToLocaleDateString = jest.fn().mockReturnValue('01/15/2025');

    // Mock Intl.DateTimeFormat to throw
    (Intl as { DateTimeFormat: unknown }).DateTimeFormat = jest.fn().mockImplementation(() => {
      throw new Error('Intl not supported');
    });

    // Mock Date.prototype.toLocaleDateString
    const originalToLocaleDateString = Date.prototype.toLocaleDateString;
    Date.prototype.toLocaleDateString = mockToLocaleDateString;

    try {
      render(<VerifiedBadge dateISO="2025-01-15T12:34:56Z" />);
      expect(screen.getByText('Verified')).toBeInTheDocument();
      expect(mockToLocaleDateString).toHaveBeenCalledWith('en-US', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      });
    } finally {
      // Restore mocks
      (Intl as { DateTimeFormat: unknown }).DateTimeFormat = originalDateTimeFormat;
      Date.prototype.toLocaleDateString = originalToLocaleDateString;
    }
  });

  it('renders without date when dateISO is null', () => {
    render(<VerifiedBadge dateISO={null} />);
    expect(screen.getByText('Verified')).toBeInTheDocument();
  });

  it('renders without date when dateISO is undefined', () => {
    render(<VerifiedBadge />);
    expect(screen.getByText('Verified')).toBeInTheDocument();
  });
});
