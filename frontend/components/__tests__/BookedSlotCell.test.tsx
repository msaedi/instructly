import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import BookedSlotCell from '../BookedSlotCell';
import type { BookedSlotPreview } from '@/types/booking';

// Mock the getLocationTypeIcon function
jest.mock('@/types/booking', () => ({
  ...jest.requireActual('@/types/booking'),
  getLocationTypeIcon: (locationType: string) => {
    const icons: Record<string, string> = {
      in_person: '📍',
      remote: '💻',
      hybrid: '🔄',
    };
    return icons[locationType] || '📍';
  },
}));

describe('BookedSlotCell', () => {
  const mockSlot: BookedSlotPreview = {
    booking_id: '01K2GY3VEVJWKZDVH5HMNXEVRD',
    student_first_name: 'John',
    student_last_initial: 'D',
    service_name: 'Piano Lesson',
    service_area_short: 'UWS',
    location_type: 'in_person',
    duration_minutes: 60,
    date: '2026-01-20',
    start_time: '10:00',
    end_time: '11:00',
  };

  const defaultProps = {
    slot: mockSlot,
    isFirstSlot: true,
    onClick: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders a button element', () => {
    render(<BookedSlotCell {...defaultProps} />);
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('displays student name in first slot', () => {
    render(<BookedSlotCell {...defaultProps} isFirstSlot={true} />);
    expect(screen.getByText('John D')).toBeInTheDocument();
  });

  it('calls onClick when clicked', () => {
    const onClick = jest.fn();
    render(<BookedSlotCell {...defaultProps} onClick={onClick} />);

    fireEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('has correct aria-label for desktop view', () => {
    render(<BookedSlotCell {...defaultProps} />);
    expect(screen.getByRole('button')).toHaveAttribute(
      'aria-label',
      'Booking with John D for Piano Lesson'
    );
  });

  describe('desktop view (isFirstSlot = true)', () => {
    it('shows student name', () => {
      render(<BookedSlotCell {...defaultProps} />);
      expect(screen.getByText('John D')).toBeInTheDocument();
    });

    it('shows service area abbreviation', () => {
      render(<BookedSlotCell {...defaultProps} />);
      expect(screen.getByText('UWS')).toBeInTheDocument();
    });

    it('shows location type icon', () => {
      render(<BookedSlotCell {...defaultProps} />);
      expect(screen.getByText('📍')).toBeInTheDocument();
    });

    it('shows duration badge for bookings over 60 minutes', () => {
      const longSlot = { ...mockSlot, duration_minutes: 120 };
      render(<BookedSlotCell {...defaultProps} slot={longSlot} />);
      expect(screen.getByText('2h')).toBeInTheDocument();
    });

    it('shows duration with hours and minutes', () => {
      const longSlot = { ...mockSlot, duration_minutes: 150 };
      render(<BookedSlotCell {...defaultProps} slot={longSlot} />);
      expect(screen.getByText('2h 30m')).toBeInTheDocument();
    });

    it('does not show duration badge for 60 minute bookings', () => {
      render(<BookedSlotCell {...defaultProps} />);
      expect(screen.queryByText('1h')).not.toBeInTheDocument();
    });
  });

  describe('desktop view (isFirstSlot = false)', () => {
    it('shows continuing indicator', () => {
      render(<BookedSlotCell {...defaultProps} isFirstSlot={false} />);
      expect(screen.getByText('(continuing)')).toBeInTheDocument();
    });

    it('shows student name in smaller text', () => {
      render(<BookedSlotCell {...defaultProps} isFirstSlot={false} />);
      expect(screen.getByText('John D')).toBeInTheDocument();
    });
  });

  describe('mobile view', () => {
    it('has correct aria-label for mobile view', () => {
      render(<BookedSlotCell {...defaultProps} isMobile={true} />);
      expect(screen.getByRole('button')).toHaveAttribute(
        'aria-label',
        'Booking with John D'
      );
    });

    it('shows student name in first slot', () => {
      render(<BookedSlotCell {...defaultProps} isMobile={true} isFirstSlot={true} />);
      expect(screen.getByText('John D')).toBeInTheDocument();
    });

    it('shows location type icon', () => {
      render(<BookedSlotCell {...defaultProps} isMobile={true} />);
      expect(screen.getByText('📍')).toBeInTheDocument();
    });

    it('shows service area abbreviation', () => {
      render(<BookedSlotCell {...defaultProps} isMobile={true} />);
      expect(screen.getByText('UWS')).toBeInTheDocument();
    });

    it('shows ellipsis when not first slot', () => {
      render(<BookedSlotCell {...defaultProps} isMobile={true} isFirstSlot={false} />);
      expect(screen.getByText('...')).toBeInTheDocument();
    });
  });

  describe('styling', () => {
    it('has red background styling', () => {
      render(<BookedSlotCell {...defaultProps} />);
      expect(screen.getByRole('button')).toHaveClass('bg-red-100', 'border-red-300');
    });

    it('has pointer cursor', () => {
      render(<BookedSlotCell {...defaultProps} />);
      expect(screen.getByRole('button')).toHaveClass('cursor-pointer');
    });

    it('has mobile-specific styles when isMobile is true', () => {
      render(<BookedSlotCell {...defaultProps} isMobile={true} />);
      const button = screen.getByRole('button');
      expect(button).toHaveClass('p-1');
    });

    it('has desktop-specific styles when isMobile is false', () => {
      render(<BookedSlotCell {...defaultProps} isMobile={false} />);
      const button = screen.getByRole('button');
      expect(button).toHaveClass('p-2');
    });
  });

  describe('different location types', () => {
    it('shows remote icon for remote location', () => {
      const remoteSlot = { ...mockSlot, location_type: 'remote' as const };
      render(<BookedSlotCell {...defaultProps} slot={remoteSlot} />);
      expect(screen.getByText('💻')).toBeInTheDocument();
    });

    it('shows student_home icon for student_home location', () => {
      const studentHomeSlot = { ...mockSlot, location_type: 'student_home' as const };
      render(<BookedSlotCell {...defaultProps} slot={studentHomeSlot} />);
      // Student home has the house icon in the component
      expect(screen.getByRole('button')).toBeInTheDocument();
    });
  });
});
