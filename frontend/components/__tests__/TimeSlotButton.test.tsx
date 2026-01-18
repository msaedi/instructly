import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import TimeSlotButton from '../TimeSlotButton';

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

describe('TimeSlotButton', () => {
  const defaultProps = {
    hour: 10,
    isAvailable: false,
    isBooked: false,
    isPast: false,
    onClick: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders a button element', () => {
    render(<TimeSlotButton {...defaultProps} />);
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('renders correct aria-label for unavailable slot', () => {
    render(<TimeSlotButton {...defaultProps} isAvailable={false} />);
    expect(screen.getByRole('button')).toHaveAttribute(
      'aria-label',
      'Time slot 10:00 - unavailable'
    );
  });

  it('renders correct aria-label for available slot', () => {
    render(<TimeSlotButton {...defaultProps} isAvailable={true} />);
    expect(screen.getByRole('button')).toHaveAttribute(
      'aria-label',
      'Time slot 10:00 - available'
    );
  });

  it('renders correct aria-label for booked slot', () => {
    render(<TimeSlotButton {...defaultProps} isBooked={true} />);
    expect(screen.getByRole('button')).toHaveAttribute('aria-label', 'Time slot 10:00 - booked');
  });

  it('renders correct aria-label for past slot', () => {
    render(<TimeSlotButton {...defaultProps} isPast={true} />);
    expect(screen.getByRole('button')).toHaveAttribute('aria-label', 'Time slot 10:00 - past');
  });

  it('shows checkmark when available and not booked', () => {
    render(<TimeSlotButton {...defaultProps} isAvailable={true} isBooked={false} />);
    expect(screen.getByRole('button')).toHaveTextContent('✓');
  });

  it('does not show checkmark when unavailable', () => {
    render(<TimeSlotButton {...defaultProps} isAvailable={false} />);
    expect(screen.getByRole('button')).not.toHaveTextContent('✓');
  });

  it('does not show checkmark when booked', () => {
    render(<TimeSlotButton {...defaultProps} isAvailable={true} isBooked={true} />);
    expect(screen.getByRole('button')).not.toHaveTextContent('✓');
  });

  it('calls onClick when clicked', () => {
    const onClick = jest.fn();
    render(<TimeSlotButton {...defaultProps} onClick={onClick} />);

    fireEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('is disabled when booked', () => {
    render(<TimeSlotButton {...defaultProps} isBooked={true} />);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('is disabled when past', () => {
    render(<TimeSlotButton {...defaultProps} isPast={true} />);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('is disabled when disabled prop is true', () => {
    render(<TimeSlotButton {...defaultProps} disabled={true} />);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('is enabled when not booked, not past, and not disabled', () => {
    render(<TimeSlotButton {...defaultProps} isBooked={false} isPast={false} disabled={false} />);
    expect(screen.getByRole('button')).not.toBeDisabled();
  });

  describe('visual states', () => {
    it('applies red background when booked', () => {
      render(<TimeSlotButton {...defaultProps} isBooked={true} />);
      expect(screen.getByRole('button')).toHaveClass('bg-red-400');
    });

    it('applies light green background when past and available', () => {
      render(<TimeSlotButton {...defaultProps} isPast={true} isAvailable={true} />);
      expect(screen.getByRole('button')).toHaveClass('bg-green-300');
    });

    it('applies light gray background when past and unavailable', () => {
      render(<TimeSlotButton {...defaultProps} isPast={true} isAvailable={false} />);
      expect(screen.getByRole('button')).toHaveClass('bg-gray-100');
    });

    it('applies green background when available and not past', () => {
      render(<TimeSlotButton {...defaultProps} isAvailable={true} isPast={false} />);
      expect(screen.getByRole('button')).toHaveClass('bg-green-500');
    });

    it('applies gray background when unavailable and not past', () => {
      render(<TimeSlotButton {...defaultProps} isAvailable={false} isPast={false} />);
      expect(screen.getByRole('button')).toHaveClass('bg-gray-200');
    });
  });

  describe('title/tooltip', () => {
    it('shows booking tooltip when booked', () => {
      render(<TimeSlotButton {...defaultProps} isBooked={true} />);
      expect(screen.getByRole('button')).toHaveAttribute(
        'title',
        'This slot has a booking - cannot modify'
      );
    });

    it('shows past tooltip when past', () => {
      render(<TimeSlotButton {...defaultProps} isPast={true} />);
      expect(screen.getByRole('button')).toHaveAttribute('title', 'Past time slot - view only');
    });

    it('shows no tooltip when neither booked nor past', () => {
      render(<TimeSlotButton {...defaultProps} isBooked={false} isPast={false} />);
      expect(screen.getByRole('button')).toHaveAttribute('title', '');
    });
  });

  describe('mobile mode', () => {
    it('shows formatted time in mobile mode', () => {
      render(<TimeSlotButton {...defaultProps} isMobile={true} hour={10} />);
      expect(screen.getByRole('button')).toHaveTextContent('10:00');
    });

    it('shows checkmark with time when available in mobile mode', () => {
      render(<TimeSlotButton {...defaultProps} isMobile={true} isAvailable={true} />);
      expect(screen.getByRole('button')).toHaveTextContent('✓');
    });

    it('formats hour 0 as 12:00', () => {
      render(<TimeSlotButton {...defaultProps} isMobile={true} hour={0} />);
      expect(screen.getByRole('button')).toHaveTextContent('12:00');
    });

    it('formats hour 12 as 12:00', () => {
      render(<TimeSlotButton {...defaultProps} isMobile={true} hour={12} />);
      expect(screen.getByRole('button')).toHaveTextContent('12:00');
    });

    it('formats hour 15 as 3:00', () => {
      render(<TimeSlotButton {...defaultProps} isMobile={true} hour={15} />);
      expect(screen.getByRole('button')).toHaveTextContent('3:00');
    });

    it('shows shorter booking tooltip in mobile mode', () => {
      render(<TimeSlotButton {...defaultProps} isMobile={true} isBooked={true} />);
      expect(screen.getByRole('button')).toHaveAttribute('title', 'This slot has a booking');
    });
  });

  describe('cursor styles', () => {
    it('shows not-allowed cursor when booked', () => {
      render(<TimeSlotButton {...defaultProps} isBooked={true} />);
      expect(screen.getByRole('button')).toHaveClass('cursor-not-allowed');
    });

    it('shows not-allowed cursor when past', () => {
      render(<TimeSlotButton {...defaultProps} isPast={true} />);
      expect(screen.getByRole('button')).toHaveClass('cursor-not-allowed');
    });

    it('shows pointer cursor when interactive', () => {
      render(<TimeSlotButton {...defaultProps} isBooked={false} isPast={false} />);
      expect(screen.getByRole('button')).toHaveClass('cursor-pointer');
    });
  });
});
